"""管理员组织浏览边界，与公开目录及 Agent 的既有协议分离。"""
import json
from datetime import datetime, timezone
from sqlalchemy import func, or_, select

from app.persistence.models import ChangeLog, DatasetState, Department, Employee, EmployeeDepartment
from app.persistence.read_service import SqlReadService
from app.stores.domain import InvalidStoreChanges, StoreValidationError
from app.stores.service import StoreAdminService


class OrganizationService:
    def __init__(self, sessions, reads: SqlReadService):
        self.sessions, self.reads = sessions, reads

    def departments(self, *, parent_id='0', include_inactive=False, limit=100, cursor=None, dataset_epoch=None, data_version=None):
        filters = dict(parent_id=parent_id, include_inactive=include_inactive, limit=limit,
                       cursor=cursor, dataset_epoch=dataset_epoch, data_version=data_version)
        with self.sessions() as db, db.begin():
            state = self.reads._state(db)
            self.reads._check_version(state, filters)
            stmt = select(Department).where(Department.is_virtual_root.is_(False))
            stmt = stmt.where(or_(Department.parent_id == '0', Department.parent_id.is_(None)) if parent_id == '0' else Department.parent_id == parent_id)
            if not include_inactive:
                stmt = stmt.where(Department.status == 'active')
            last = self.reads._last_id(state, 'organization-departments', filters)
            if last:
                order, identifier = json.loads(last)
                stmt = stmt.where(or_(Department.sort_order > order, (Department.sort_order == order) & (Department.id > identifier)))
            rows = list(db.scalars(stmt.order_by(Department.sort_order, Department.id).limit(limit + 1)))
            page, next_id = self.reads._page(rows, limit, key=lambda row: json.dumps([row.sort_order, row.id]))
            return self._details(db, page, include_inactive), self.reads._meta(
                state, self.reads._next_cursor(state, 'organization-departments', filters, next_id))

    def search(self, *, keyword, include_inactive=False, dataset_epoch=None, data_version=None):
        with self.sessions() as db, db.begin():
            state = self.reads._state(db)
            self.reads._check_version(state, dict(dataset_epoch=dataset_epoch, data_version=data_version))
            stmt = select(Department).where(Department.name.contains(keyword.strip(), autoescape=True))
            if not include_inactive:
                stmt = stmt.where(Department.status == 'active')
            matches = list(db.scalars(stmt.order_by(Department.id))) if keyword.strip() else []
            keep = {row.id: row for row in matches}
            for row in matches:
                parent, visited = row.parent_id, {row.id}
                while parent and parent not in visited:
                    visited.add(parent)
                    ancestor = db.get(Department, parent)
                    if ancestor is None:
                        break
                    keep[parent] = ancestor
                    parent = ancestor.parent_id
            return self._details(db, list(keep.values()), include_inactive), {
                **self.reads._meta(state), 'matched_ids': [row.id for row in matches]}

    def employees(self, **filters):
        with self.sessions() as db, db.begin():
            state = self.reads._state(db)
            self.reads._check_version(state, filters)
            tree = select(Department.id).where(Department.id == filters['department_id']).cte('org_member_tree', recursive=True)
            if filters.get('include_descendants'):
                tree = tree.union_all(select(Department.id).join(tree, Department.parent_id == tree.c.id))
            relations = select(EmployeeDepartment.employee_id).join(Department, Department.id == EmployeeDepartment.department_id).where(
                EmployeeDepartment.active.is_(True), Department.status == 'active',
                EmployeeDepartment.department_id.in_(select(tree.c.id)))
            stmt = select(Employee).where(Employee.id.in_(relations), Employee.status == 'active')
            keyword = filters.get('keyword', '').strip()
            if keyword:
                stmt = stmt.where(or_(Employee.name.contains(keyword, autoescape=True),
                                      Employee.mobile == keyword, Employee.feishu_user_id == keyword))
            account_status = filters.get('account_status', 'all')
            if account_status == 'unknown':
                stmt = stmt.where(or_(*(getattr(Employee, key).is_(None) for key in (
                    'is_activated', 'is_frozen', 'is_unjoin', 'is_resigned', 'is_exited'))))
            elif account_status != 'all':
                column, expected = {'activated': (Employee.is_activated, True), 'unactivated': (Employee.is_activated, False),
                                    'frozen': (Employee.is_frozen, True), 'unjoin': (Employee.is_unjoin, True)}[account_status]
                stmt = stmt.where(column.is_(expected))
            total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
            last = self.reads._last_id(state, 'organization-employees', filters)
            if last:
                stmt = stmt.where(Employee.id > last)
            limit = filters.get('limit', 20)
            rows = list(db.scalars(stmt.order_by(Employee.id).limit(limit + 1)))
            page, next_id = self.reads._page(rows, limit)
            return [self.reads._employee(db, row) for row in page], {
                **self.reads._meta(state, self.reads._next_cursor(state, 'organization-employees', filters, next_id)),
                'total_count': total}

    def _details(self, db, rows, include_inactive=False):
        ids = [row.id for row in rows]
        children = select(Department.parent_id).where(Department.parent_id.in_(ids))
        if not include_inactive:
            children = children.where(Department.status == 'active')
        parents = set(db.scalars(children.distinct()))
        return [{**self.reads._department(db, row), 'sort_order': row.sort_order, 'has_children': row.id in parents} for row in rows]

    def order(self, *, department_id, parent_id, anchor_id, position, dataset_epoch, data_version, actor):
        with self.sessions.begin() as db:
            state = db.scalar(select(DatasetState).where(DatasetState.id == 1).with_for_update())
            if state is None or state.initialization_status != 'complete':
                raise RuntimeError('INITIALIZATION_INCOMPLETE')
            self.reads._check_version(state, dict(dataset_epoch=dataset_epoch, data_version=data_version))
            rows = list(db.scalars(select(Department).where(
                or_(Department.parent_id == '0', Department.parent_id.is_(None)) if parent_id == '0' else Department.parent_id == parent_id,
                Department.is_virtual_root.is_(False)
            ).order_by(Department.sort_order, Department.id).with_for_update()))
            ids = [row.id for row in rows]
            if department_id not in ids or anchor_id not in ids or department_id == anchor_id:
                raise ValueError('SIBLING_ORDER_REQUIRED')
            ordered = ids.copy()
            ordered.remove(department_id)
            ordered.insert(ordered.index(anchor_id) + (position == 'after'), department_id)
            if ordered != ids:
                by_id = {row.id: row for row in rows}
                for index, identifier in enumerate(ordered):
                    by_id[identifier].sort_order = index
                db.add(ChangeLog(object_type='department_order', object_id=parent_id, source='admin', actor=actor,
                                 before_data={'department_ids': ids}, after_data={'department_ids': ordered},
                                 committed_at=datetime.now(timezone.utc).replace(tzinfo=None)))
                state.data_version += 1
            return {'department_ids': ordered}, self.reads._meta(state)

    def save_stores(self, changes, *, dataset_epoch, data_version, actor):
        with self.sessions.begin() as db:
            service = StoreAdminService(self.sessions)
            state = service._lock_state(db, data_version, lock=True)
            if state.initialization_status != 'complete':
                raise RuntimeError('INITIALIZATION_INCOMPLETE')
            self.reads._check_version(state, dict(dataset_epoch=dataset_epoch, data_version=data_version))
            ids = [change.department_id for change in changes]
            if len(ids) != len(set(ids)):
                raise InvalidStoreChanges([StoreValidationError('', 'DUPLICATE_DEPARTMENT', '同一部门只能出现一次')])
            valid = set()
            for offset in range(0, len(ids), 500):
                valid.update(db.scalars(select(Department.id).where(
                    Department.id.in_(ids[offset:offset + 500]), Department.status == 'active',
                    Department.is_virtual_root.is_(False)).with_for_update()))
            if valid != set(ids):
                raise InvalidStoreChanges([StoreValidationError(identifier, 'DEPARTMENT_NOT_SELECTABLE', '批量目标必须为有效的实际部门') for identifier in set(ids) - valid])
            result = service.apply_in_session(db, changes, data_version, actor, datetime.now(timezone.utc).replace(tzinfo=None))
            return {'saved_count': len(ids), 'changed_count': result.changed_count}, {
                'dataset_epoch': result.dataset_epoch, 'data_version': result.data_version}

    def selection(self, *, selected_ids, dataset_epoch, data_version, toggle_id=None, include_details=False):
        with self.sessions() as db, db.begin():
            state = self.reads._state(db)
            self.reads._check_version(state, dict(dataset_epoch=dataset_epoch, data_version=data_version))
            rows = list(db.execute(select(Department.id, Department.parent_id, Department.status, Department.is_virtual_root)))
            parents = {row.id: row.parent_id for row in rows}
            valid = {row.id for row in rows if row.status == 'active' and not row.is_virtual_root}
            selected = set(selected_ids) & valid
            totals = {}
            for identifier in valid:
                parent, visited = parents.get(identifier), {identifier}
                while parent and parent not in visited:
                    visited.add(parent)
                    totals[parent] = totals.get(parent, 0) + 1
                    parent = parents.get(parent)
            if toggle_id is not None:
                if toggle_id == '0':
                    selected = set() if selected else valid.copy()
                elif toggle_id in valid:
                    branch = set()
                    for identifier in valid:
                        parent, visited = parents.get(identifier), {identifier}
                        while parent and parent not in visited:
                            if parent == toggle_id:
                                branch.add(identifier)
                                break
                            visited.add(parent)
                            parent = parents.get(parent)
                    chosen = selected & branch
                    if toggle_id not in selected and not chosen:
                        selected.add(toggle_id)
                    elif toggle_id in selected and not chosen and branch:
                        selected.update(branch)
                    elif toggle_id in selected:
                        selected.remove(toggle_id)
                    else:
                        selected.difference_update(branch)
                else:
                    raise ValueError('DEPARTMENT_NOT_SELECTABLE')
            # 以实际集合重新计数，部分下级永远不会被四态外观补回。
            counts = {}
            for identifier in selected:
                parent, visited = parents.get(identifier), {identifier}
                while parent and parent not in visited:
                    visited.add(parent)
                    counts[parent] = counts.get(parent, 0) + 1
                    parent = parents.get(parent)
            states = {identifier: {
                'self_selected': identifier in selected,
                'descendants': 'none' if not counts.get(identifier) else 'all' if counts[identifier] == totals.get(identifier) else 'partial',
            } for identifier in valid | {'0'}}
            states['0'] = {'self_selected': False, 'descendants': 'none' if not selected else 'all' if selected == valid else 'partial'}
            details = []
            if include_details:
                ids = sorted(selected)
                for offset in range(0, len(ids), 500):
                    details.extend(self._details(db, list(db.scalars(select(Department).where(Department.id.in_(ids[offset:offset + 500])).order_by(Department.id)))))
            return {'selected_ids': sorted(selected), 'count': len(selected), 'states': states,
                    'removed_ids': sorted(set(selected_ids) - valid), 'departments': details}, self.reads._meta(state)
