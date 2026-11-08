"""完整采集候选；分页异常向上抛出，绝不返回半轮结果。"""
from dataclasses import dataclass, field
from datetime import datetime,timezone
from urllib.parse import urlsplit


@dataclass
class Candidate:
    departments: dict = field(default_factory=dict)
    employees: dict = field(default_factory=dict)
    pending: list = field(default_factory=list)
    coverage_status: str = "unknown"
    full: bool = False
    collection_started_at: str | None = None
    initialization_proof: dict | None = None


def _custom_value(raw, field_id, allow_text=False):
    """读取飞书 custom_attrs 的单选值，保留未知选项而不静默清空。"""
    if not field_id:
        return None, None, False
    values = raw.get('custom_attrs') or raw.get('custom_fields') or []
    if isinstance(values, dict):
        values = [{'id': key, 'value': value} for key, value in values.items()]
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict) or str(item.get('id') or item.get('field_id')) != str(field_id):
            continue
        value = item.get('value')
        if allow_text and item.get('type') == 'TEXT':
            if not isinstance(value, dict) or 'text' not in value:
                raise RuntimeError('FEISHU_CUSTOM_TEXT_UNREADABLE')
            text = value['text']
            if text is not None and (not isinstance(text, str) or len(text) > 255):
                raise RuntimeError('FEISHU_CUSTOM_TEXT_VALUE_UNSUPPORTED')
            return None, text, True
        if isinstance(value, dict):
            return value.get('id') or value.get('option_id'), value.get('option_value') or value.get('name') or value.get('text'), True
        if isinstance(value, list):
            if len(value) > 1:
                raise RuntimeError('FEISHU_CUSTOM_ENUM_VALUE_UNSUPPORTED')
            value = value[0] if value else None
        if isinstance(value, dict):
            return value.get('id') or value.get('option_id'), value.get('name') or value.get('text'), True
        return (str(value) if value not in (None, '') else None), None, True
    return None, None, False


ACCOUNT_FLAGS = ('is_frozen', 'is_resigned', 'is_activated', 'is_exited', 'is_unjoin')


def optional_user_facts(raw):
    """保留原始字段的缺省、可读空值和不可读，不从 SDK 类型推定权限。"""
    status = raw.get('status') if isinstance(raw.get('status'), dict) else {}
    facts, readability = {}, {}
    for key in ACCOUNT_FLAGS:
        value = status.get(key)
        facts[key] = value if type(value) is bool else None
        readability[key] = 'not_collected' if key not in status else 'readable' if type(value) is bool else 'unreadable'
    mobile = raw.get('mobile')
    if 'mobile' not in raw:
        readability['mobile'] = 'not_collected'
    elif raw.get('mobile_visible') is False or (mobile is not None and (not isinstance(mobile, str) or len(mobile) > 128)):
        readability['mobile'] = 'unreadable'
    else:
        readability['mobile'] = 'readable'
    facts['mobile'] = mobile.strip() if isinstance(mobile, str) and readability['mobile'] == 'readable' else None
    email = raw.get('email')
    if 'email' not in raw:
        readability['email'] = 'not_collected'
    elif email is not None and (not isinstance(email, str) or len(email) > 254):
        readability['email'] = 'unreadable'
    else:
        readability['email'] = 'readable'
    facts['email'] = email.strip() if isinstance(email, str) and readability['email'] == 'readable' else None
    avatar = raw.get('avatar')
    avatar_url = None
    if isinstance(avatar, dict):
        for size in ('avatar_240', 'avatar_72', 'avatar_640', 'avatar_origin'):
            value = avatar.get(size)
            if isinstance(value, str) and 0 < len(value) <= 2048:
                try:
                    url = urlsplit(value)
                    if url.scheme == 'https' and url.hostname and not url.username and not url.password:
                        avatar_url = value
                        break
                except ValueError:
                    pass
    empty_avatar = avatar is None or (isinstance(avatar, dict) and all(value in (None, '') for value in avatar.values()))
    readability['avatar_url'] = 'not_collected' if 'avatar' not in raw else 'readable' if avatar_url or empty_avatar else 'unreadable'
    facts['avatar_url'] = avatar_url
    joined = raw.get('join_time')
    # 保留飞书原始 Unix 秒（包括 0），拒绝布尔、毫秒及超出日期范围的值。
    valid_joined = type(joined) is int and 0 <= joined <= 253402271999
    readability['join_time'] = 'not_collected' if 'join_time' not in raw else 'readable' if joined is None or valid_joined else 'unreadable'
    facts['join_time'] = joined if valid_joined else None
    facts['field_readability'] = readability
    return facts


def normalize_user(raw, custom_mappings=None, employee_type_options=None):
    status=raw.get('status')
    if not isinstance(status,dict) or not any(type(status.get(key)) is bool for key in ('is_resigned','is_exited')):
        raise RuntimeError('FEISHU_STATUS_UNREADABLE')
    inactive=status.get('is_resigned') is True or status.get('is_exited') is True
    relations_readable=isinstance(raw.get('department_ids'),list) and all(isinstance(d,str) and d for d in raw['department_ids'])
    if not relations_readable and not inactive:
        raise RuntimeError('FEISHU_MEMBERSHIP_UNREADABLE')
    identifier = raw["user_id"]
    if not isinstance(identifier,str) or not identifier: raise RuntimeError('FEISHU_ID_MISMATCH')
    departments = list(dict.fromkeys(raw['department_ids'])) if relations_readable else None
    primaries = {order["department_id"] for order in (raw.get("orders") or []) if isinstance(order,dict) and order.get("is_primary_dept") is True and order.get("department_id")} if relations_readable else set()
    primary = next(iter(primaries)) if len(primaries) == 1 else None
    inconsistent = len(primaries) > 1 or (primary is not None and primary not in departments)
    type_value = raw.get('employee_type')
    type_id = type_value.get('id') if isinstance(type_value, dict) else raw.get('employee_type_id')
    type_name = type_value.get('name') if isinstance(type_value, dict) else raw.get('employee_type_name')
    if type_id and employee_type_options and type_id not in employee_type_options:
        type_name, type_quality = type_name, 'unknown_option'
    else:
        type_quality = None
    mappings = custom_mappings or {}
    role_id, role_name, role_present = _custom_value(raw, mappings.get('permission_role'))
    store_id, store_name, store_present = _custom_value(raw, mappings.get('store_attribute'), allow_text=True)
    quality = 'pending_verification' if not relations_readable else 'inconsistent' if inconsistent else 'complete'
    if type_quality or (mappings.get('permission_role') and not role_present) or (mappings.get('store_attribute') and not store_present):
        quality = 'pending_verification'
    return {**optional_user_facts(raw), "id": identifier, "feishu_user_id": identifier, "open_id": raw.get("open_id"), "name": raw["name"], "employee_no": raw.get("employee_no"), "employee_type_id": type_id, "employee_type_name": type_name, "job_title": raw.get('job_title'), "leader_user_id": raw.get('leader_user_id'), "permission_role_id": role_id, "permission_role_name": role_name, "store_attribute_id": store_id, "store_attribute_name": store_name, "status": "inactive" if inactive else "active", "primary_department_id": primary if not inconsistent else None, "sync_quality": quality, "department_ids": departments}


def normalize_department(raw):
    if not isinstance(raw.get('status'),dict) or type(raw['status'].get('is_deleted')) is not bool:
        raise RuntimeError('FEISHU_STATUS_UNREADABLE')
    identifier = raw["open_department_id"]
    if not isinstance(identifier,str) or not identifier: raise RuntimeError('FEISHU_ID_MISMATCH')
    parent_readable=isinstance(raw.get('parent_department_id'),str) and bool(raw['parent_department_id'])
    inactive=raw['status']['is_deleted']
    if not parent_readable and not inactive: raise RuntimeError('FEISHU_PARENT_UNREADABLE')
    value={"id": identifier, "feishu_department_id": identifier, "parent_id": raw['parent_department_id'] if parent_readable else None, "name": raw["name"], "leader_user_id": raw.get('leader_user_id'), "status": "inactive" if inactive else "active", "sync_quality": "complete" if parent_readable else 'pending_verification', "is_virtual_root": False}
    if not parent_readable:value['parent_unreadable']=True
    return value


class Collector:
    def __init__(self, api, coverage_verified=False, progress=None, custom_mappings=None, employee_type_options=None):
        self.api, self.coverage_verified = api, coverage_verified
        self.custom_mappings = custom_mappings or {}
        self.employee_type_options = employee_type_options
        self.progress=progress

    def _progress(self,phase,result):
        if self.progress:
            self.progress(phase=phase,departments_processed=len(result.departments),employees_processed=len(result.employees),departments_total=None,employees_total=None)

    def _department(self,identifier):
        raw=self.api.detail('department',identifier)
        if raw.get('open_department_id')!=identifier:raise RuntimeError('FEISHU_ID_MISMATCH')
        return normalize_department(raw)

    def collect(self, root=None, previous_departments=(), previous_users=()):
        result = Candidate(full=root is None,collection_started_at=datetime.now(timezone.utc).isoformat())
        result.departments["0"] = {"id": "0", "feishu_department_id": "0", "parent_id": None, "name": "组织", "status": "active", "sync_quality": "complete", "is_virtual_root": True}
        users, roots, groups = set(), [], []
        self._progress('scopes',result)
        for page in self.api.pages("scopes"):
            roots.extend(page.get("department_ids", []))
            users.update(page.get("user_ids", []))
            groups.extend(page.get("group_ids", []))
        if root: users.clear()
        users.update(previous_users)
        queue = [root] if root else list(dict.fromkeys(["0", *roots]))
        visited = set()
        while queue:
            identifier = queue.pop()
            if identifier in visited:
                continue
            visited.add(identifier)
            if identifier != "0":
                result.departments[identifier] = self._department(identifier)
                if result.departments[identifier]['status']=='inactive':
                    self._progress('departments',result)
                    continue
            for page in self.api.pages("children", department_id=identifier):
                queue.extend(item["open_department_id"] for item in page.get("items", []))
            for page in self.api.pages("users", department_id=identifier):
                users.update(item["user_id"] for item in page.get("items", []))
            self._progress('departments',result)
        for identifier in set(previous_departments)-set(result.departments)-{'0'}:
            try:
                result.departments[identifier]=self._department(identifier)
            except RuntimeError:
                result.pending.append(('department',identifier))
        for identifier in sorted(users):
            self._user(result, identifier)
            self._progress('employees',result)
        self._ancestors(result)
        self._progress('collected',result)
        result.coverage_status = "complete" if self.coverage_verified and not groups and not result.pending and root is None else "incomplete" if groups or result.pending else "unknown"
        return result

    def _user(self, result, identifier):
        try:
            raw=self.api.detail('user',identifier)
            if raw.get('user_id')!=identifier: raise RuntimeError('FEISHU_ID_MISMATCH')
            result.employees[identifier] = normalize_user(raw, self.custom_mappings, self.employee_type_options)
        except RuntimeError:
            result.pending.append(("employee", identifier))

    def _ancestors(self, result):
        queue = [d["parent_id"] for d in result.departments.values() if d["parent_id"]]
        queue.extend(d for u in result.employees.values() for d in (u['department_ids'] or []))
        visited = set(result.departments)
        while queue:
            identifier = queue.pop()
            if identifier in visited:
                continue
            visited.add(identifier)
            if identifier == '0':
                result.departments['0'] = {'id':'0','feishu_department_id':'0','parent_id':None,'name':'组织','status':'active','sync_quality':'complete','is_virtual_root':True}
                continue
            try:
                department = self._department(identifier)
                result.departments[identifier] = department
                if department["parent_id"]:
                    queue.append(department["parent_id"])
            except RuntimeError:
                result.pending.append(("department", identifier))

    def event(self, event_type, identifier):
        result = Candidate()
        if ".user." in event_type:
            self._user(result, identifier)
        else:
            try:
                result.departments[identifier] = self._department(identifier)
            except RuntimeError:
                result.pending.append(("department", identifier))
        self._ancestors(result)
        return result
