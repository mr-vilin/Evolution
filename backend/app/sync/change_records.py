"""从已提交的组织同步审计事实生成面向管理员的对象变更记录。"""
from collections import defaultdict

from sqlalchemy import select

from app.persistence.models import ChangeLog, Department, Employee, EmployeeDepartment, LoginIdentity, SyncJob
from app.web import utc_datetime


SYNC_SOURCES = {'initialize', 'full', 'subtree', 'reconcile', 'event'}
TECHNICAL_FIELDS = {'id', 'sync_quality', 'field_readability', 'sort_order', 'last_sync_at'}
AUTOMATIC_ACTORS = {'schedule', 'listener:startup', 'listener:reconnected', 'system', 'startup', 'sync'}


def _executor(db, requested_by):
    if not requested_by or requested_by in AUTOMATIC_ACTORS or requested_by.startswith('system:'):
        return {'name': '系统', 'avatar_url': None, 'is_user': False}
    actor = requested_by.removeprefix('admin:')
    identity = db.get(LoginIdentity, actor)
    user_id = identity.user_id if identity else actor
    person = db.scalar(select(Employee).where(
        (Employee.id == user_id) | (Employee.feishu_user_id == user_id) | (Employee.open_id == actor)
    ).limit(1))
    return {'name': person.name if person else actor, 'avatar_url': person.avatar_url if person else None,
            'is_user': person is not None or requested_by.startswith('admin:')}


def executor_name(db, requested_by):
    return _executor(db, requested_by)['name']


def _merge_value(fields, key, before, after):
    if key in fields:
        fields[key] = (fields[key][0], after)
    else:
        fields[key] = (before, after)


def _relation_values(data):
    if 'relations' in data:
        return {str(item[0]): ('主部门' if item[1] else '所属部门') if item[2] else '归属已失效'
                for item in data['relations']}
    if 'department_id' in data:
        return {str(data['department_id']): ('主部门' if data.get('primary') else '所属部门') if data.get('active') else '归属已失效'}
    return {}


def _membership_snapshots(db, employee_ids):
    # Reverse the logged relation changes, using full snapshots whenever available.
    if not employee_ids:
        return {}
    current = defaultdict(dict)
    for relation in db.scalars(select(EmployeeDepartment).where(EmployeeDepartment.employee_id.in_(employee_ids))):
        current[relation.employee_id][relation.department_id] = (
            '主部门' if relation.is_primary else '所属部门') if relation.is_active else '归属已失效'
    snapshots = {}
    logs = db.scalars(select(ChangeLog).where(
        ChangeLog.object_type == 'membership', ChangeLog.source == 'feishu',
        ChangeLog.object_id.in_(employee_ids),
    ).order_by(ChangeLog.committed_at.desc(), ChangeLog.id.desc()))
    for log in logs:
        before, after = log.before_data or {}, log.after_data or {}
        old, new = _relation_values(before), _relation_values(after)
        latest = new if 'relations' in after else {**current[log.object_id], **new}
        previous = old if 'relations' in before else {**latest, **old}
        if 'relations' not in before:
            for identifier in new.keys() - old.keys():
                previous.pop(identifier, None)
        snapshots[log.id] = (previous, latest)
        current[log.object_id] = previous
    return snapshots


def _department_change(logs, snapshots, departments, fields):
    related = [snapshots[log.id] for log in logs if log.id in snapshots]
    primary_before, primary_after = fields.get('primary_department_id', (None, None))
    if not related and 'primary_department_id' not in fields:
        return None

    def display(relations, primary):
        items = {key: label for key, label in relations.items() if label != '归属已失效'}
        if primary and (not relations or primary in items):
            items[primary] = '主部门'
        ordered = sorted(items, key=lambda key: (items[key] != '主部门', departments.get(key, key), key))
        return [{'id': key, 'name': departments.get(key, key), 'primary': items[key] == '主部门'} for key in ordered]

    previous, latest = (related[0][0], related[-1][1]) if related else ({}, {})
    before, after = display(previous, primary_before), display(latest, primary_after)
    if before == after:
        return None
    return {'field': 'departments', 'label': '部门', 'before': before, 'after': after}


def _record(logs, object_type, jobs, names, departments, executors, snapshots):
    fields = {}
    created = False
    for log in logs:
        before, after = log.before_data or {}, log.after_data or {}
        if log.object_type == 'membership':
            old, new = _relation_values(before), _relation_values(after)
            for department_id in sorted(old.keys() | new.keys()):
                if old.get(department_id) != new.get(department_id):
                    _merge_value(fields, 'membership:' + department_id,
                                 old.get(department_id), new.get(department_id))
            continue
        created |= log.before_data is None
        for field in before.keys() | after.keys():
            if field not in TECHNICAL_FIELDS and before.get(field) != after.get(field):
                _merge_value(fields, field, before.get(field), after.get(field))

    differences = []
    for field, (before, after) in sorted(fields.items()):
        if before == after:
            continue
        item = {'field': field, 'before': before, 'after': after}
        if field.startswith('membership:'):
            department_id = field.split(':', 1)[1]
            item['label'] = '部门归属 · ' + departments.get(department_id, department_id)
        elif field in {'parent_id', 'primary_department_id'}:
            item.update(before=departments.get(before, before), after=departments.get(after, after))
        differences.append(item)
    if not differences and not created:
        return None

    last = logs[-1]
    before_status, after_status = fields.get('status', (None, None))
    if created:
        action = 'create'
    elif (before_status, after_status) == ('active', 'inactive'):
        action = 'deactivate'
    elif (before_status, after_status) == ('inactive', 'active'):
        action = 'reactivate'
    else:
        action = 'update'
    job = jobs.get(last.job_id)
    source = last.sync_source or (job.type if job else None)
    executor = executors.get(job.id) if job else {'name': '系统', 'avatar_url': None, 'is_user': False}
    actor_name = last.executor_name or executor['name']
    historical_name = next((log.object_name or (log.after_data or {}).get('name') or
                            (log.before_data or {}).get('name') for log in reversed(logs)
                            if log.object_name or (log.after_data or {}).get('name') or (log.before_data or {}).get('name')), None)
    return {
        'id': last.id, 'object_type': object_type, 'object_id': last.object_id,
        'object_name': historical_name or names.get(last.object_id) or last.object_id,
        'source': source if source in SYNC_SOURCES else None, 'action': action,
        'actor': actor_name,
        'actor_avatar_url': executor['avatar_url'] if actor_name == executor['name'] else None,
        'actor_is_user': executor['is_user'],
        'job_id': last.job_id, 'event_id': last.event_id,
        'committed_at': utc_datetime(last.committed_at), 'changes': differences,
        'department_change': _department_change(logs, snapshots, departments, fields) if object_type == 'employee' else None,
        'raw_records': [{'id': log.id, 'object_type': log.object_type, 'before': log.before_data, 'after': log.after_data} for log in logs],
    }


def organization_changes(db, *, object_type, object_id=None, keyword=None, source=None,
                         action=None, actor=None, committed_after=None, committed_before=None,
                         view='all', page=1, page_size=20):
    kinds = ('employee', 'membership') if object_type == 'employee' else ('department',)
    stmt = select(ChangeLog).where(ChangeLog.source == 'feishu', ChangeLog.object_type.in_(kinds))
    if object_id:
        stmt = stmt.where(ChangeLog.object_id == object_id)
    if committed_after:
        stmt = stmt.where(ChangeLog.committed_at >= committed_after)
    if committed_before:
        stmt = stmt.where(ChangeLog.committed_at <= committed_before)

    batches = defaultdict(list)
    for log in db.scalars(stmt.order_by(ChangeLog.committed_at, ChangeLog.id)):
        # 存量任务日志可按提交时间和任务关联；缺少事件标识时保留独立历史记录。
        publication = log.publication_id or ((log.job_id, log.committed_at) if log.job_id else log.id)
        batches[(publication, log.object_id)].append(log)

    model = Employee if object_type == 'employee' else Department
    object_ids = {key[1] for key in batches}
    snapshots = _membership_snapshots(db, object_ids) if object_type == 'employee' else {}
    names = dict(db.execute(select(model.id, model.name).where(model.id.in_(object_ids))).all()) if object_ids else {}
    departments = dict(db.execute(select(Department.id, Department.name)).all())
    job_ids = {log.job_id for logs in batches.values() for log in logs if log.job_id}
    jobs = {job.id: job for job in db.scalars(select(SyncJob).where(SyncJob.id.in_(job_ids)))} if job_ids else {}
    actor_names = {actor: _executor(db, actor) for actor in {job.requested_by for job in jobs.values()}}
    executors = {job.id: actor_names[job.requested_by] for job in jobs.values()}

    rows = []
    for logs in batches.values():
        record = _record(logs, object_type, jobs, names, departments, executors, snapshots)
        if not record:
            continue
        if (source and record['source'] != source) or (action and record['action'] != action):
            continue
        if actor and actor.casefold() not in record['actor'].casefold():
            continue
        if keyword and not any(keyword.casefold() in str(record[key]).casefold() for key in ('object_name', 'object_id')):
            continue
        rows.append(record)
    rows.sort(key=lambda row: (row['committed_at'], row['id']), reverse=True)

    if view == 'grouped':
        groups = {}
        for row in rows:
            group = groups.setdefault(row['object_id'], {
                'object_id': row['object_id'], 'object_name': row['object_name'], 'total': 0, 'records': [],
            })
            group['total'] += 1
            if len(group['records']) < 5:
                group['records'].append(row)
        rows = list(groups.values())
    start = (page - 1) * page_size
    return {'data': rows[start:start + page_size], 'meta': {'total': len(rows), 'page': page, 'page_size': page_size}}