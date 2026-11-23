"""初始化使用严格校验；缺失字段不能悄悄降为待核实事实。"""
from contextlib import contextmanager

from app.sync.collector import Collector, normalize_department, normalize_user


class InitializationFailure(RuntimeError):
    def __init__(self, code, message, issues=None):
        super().__init__(code)
        self.code, self.message, self.issues = code, message, issues or []


def invalid(kind, identifier, field, message):
    raise InitializationFailure('INITIALIZATION_DATA_INVALID', message, [
        {'object_type': kind, 'object_id': identifier, 'field': field, 'message': message},
    ])


def required_text(raw, key, kind, identifier):
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        invalid(kind, identifier, key, f'{key} 缺失或格式错误')
    if len(value) > (255 if key == 'name' else 191):
        invalid(kind, identifier, key, f'{key} 超出存储长度限制')
    return value


def optional_text(raw, key, kind, identifier, *, allow_missing=False):
    if key not in raw:
        if allow_missing:
            return
        invalid(kind, identifier, key, f'{key} 未返回，无法证明字段可读；请检查飞书字段权限')
    if raw[key] is not None and not isinstance(raw[key], str):
        invalid(kind, identifier, key, f'{key} 应为文本或合法空值')
    limit = 128 if key == 'employee_no' else 255 if key == 'job_title' else 191
    if isinstance(raw[key], str) and len(raw[key]) > limit:
        invalid(kind, identifier, key, f'{key} 超出存储长度限制')


def validate_department(raw, field_results=None):
    identifier = raw.get('open_department_id') if isinstance(raw.get('open_department_id'), str) else ''
    result_start = len(field_results) if field_results is not None else 0
    for key in ('open_department_id', 'name'):
        with field_check(field_results, identifier, key, 'department'):
            required_text(raw, key, 'department', identifier)
    with field_check(field_results, identifier, 'leader_user_id', 'department'):
        optional_text(raw, 'leader_user_id', 'department', identifier, allow_missing=True)
    with field_check(field_results, identifier, 'status', 'department'):
        if not isinstance(raw.get('status'), dict) or type(raw['status'].get('is_deleted')) is not bool:
            invalid('department', identifier, 'status', '部门状态不可读或格式错误')
    with field_check(field_results, identifier, 'parent_department_id', 'department'):
        if not isinstance(raw.get('parent_department_id'), str) or not raw['parent_department_id']:
            invalid('department', identifier, 'parent_department_id', '部门父级不可读')
    if field_results is not None and any(item['status'] != 'passed' for item in field_results[result_start:]):
        return None
    return normalize_department(raw)


def validate_definitions(definitions, mappings, keys=('permission_role', 'store_attribute')):
    by_id = {item.get('id'): item for item in definitions}
    for key in keys:
        identifier = mappings.get(key)
        definition = by_id.get(identifier)
        if key == 'store_attribute' and definition and definition.get('type') == 'TEXT':
            continue
        if not identifier or not definition or definition.get('type') != 'ENUMERATION':
            message = '门店属性必须映射到可读取的飞书文本或单选字段' if key == 'store_attribute' else '权限角色必须映射到可读取的飞书单选字段'
            raise InitializationFailure('INITIALIZATION_FIELD_MAPPING', message)
        options = definition.get('options', {}).get('options')
        if (not isinstance(options, list) or any(not isinstance(o, dict) or not isinstance(o.get('id'), str)
                or not o['id'] or len(o['id']) > 191 or not isinstance(o.get('value'), str)
                or not o['value'].strip() or len(o['value']) > 255 for o in options)
                or len({o['id'] for o in options}) != len(options)):
            raise InitializationFailure('INITIALIZATION_FIELD_MAPPING', f'{key} 的选项定义不可读')
    return {mappings[key]: by_id[mappings[key]] for key in keys}


USER_FIELD_TITLES = {
    'user_id': '人员标识', 'name': '姓名', 'employee_no': '工号', 'job_title': '职务',
    'leader_user_id': '直属上级', 'open_id': '登录标识',
    'department_ids': '所属部门', 'orders': '部门顺序与唯一主部门', 'status': '人员状态',
    'employee_type': '员工类型', 'permission_role': '权限角色', 'store_attribute': '门店属性',
    'mobile': '手机号', 'email': '邮箱', 'is_frozen': '账号暂停标志', 'is_resigned': '账号离职标志',
    'avatar_url': '头像', 'join_time': '入职日期',
    'is_activated': '账号激活标志', 'is_exited': '账号主动退出标志', 'is_unjoin': '账号未加入标志',
}
DEPARTMENT_FIELD_TITLES = {
    'open_department_id': '部门标识', 'name': '部门名称', 'leader_user_id': '部门负责人',
    'status': '部门状态', 'parent_department_id': '上级部门',
}


def field_requirements():
    """界面填写规则与校验结果分开返回，历史结果也能展示当前要求。"""
    definitions = [
        ('permission_role', '权限角色字段定义及选项', '必填配置', '须配置可读取的飞书单选字段及选项。'),
        ('store_attribute', '门店属性字段定义及选项', '必填配置', '须配置可读取的飞书文本或单选字段；单选字段须返回选项。'),
    ]
    departments = [
        ('open_department_id', '必填', '部门标识须返回且非空。'),
        ('name', '必填', '部门名称须返回且非空，最多 255 字符。'),
        ('leader_user_id', '非必填', '允许未配置、空值或接口省略；填写时须为有效人员标识。'),
        ('status', '必填', '接口须返回部门删除状态 is_deleted（布尔值）。'),
        ('parent_department_id', '必填', '须返回上级部门标识；顶级部门指向根部门 0。'),
    ]
    users = [
        ('user_id', '必填', '人员标识须返回且非空。'),
        ('name', '必填', '姓名须返回且非空，最多 255 字符。'),
        ('employee_no', '非必填', '允许未填写或空值，最多 128 字符；接口仍须返回此字段以确认可读。'),
        ('job_title', '非必填', '允许未填写或空值，最多 255 字符；接口仍须返回此字段以确认可读。'),
        ('leader_user_id', '非必填', '允许未配置、空值或接口省略；填写时须为有效人员标识且不能形成上级环。'),
        ('open_id', '非必填', '允许空值或接口省略；已返回的标识须有效且唯一。'),
        ('department_ids', '非必填', '允许无部门（空列表）；接口须明确返回部门列表，已填写的部门须有效。'),
        ('orders', '条件必填', '有部门时须返回部门顺序，并且恰有一个主部门；无部门时允许省略或空列表。'),
        ('status', '必填', '接口须返回离职状态 is_resigned 或 is_exited（布尔值）。'),
        ('employee_type', '非必填', '允许未填写或空值；接口仍须返回此字段，已填写值须在员工类型选项中。'),
        ('permission_role', '非必填', '字段定义须可读；允许未填写或接口省略，已返回值须为合法空值或已配置的单选项。'),
        ('store_attribute', '非必填', '字段定义须可读；允许未填写或接口省略，已返回文本最多 255 字符，或为已配置的单选项。'),
    ]
    users.extend((key, '可缺省', '保留飞书原始事实；缺失、不可读标为未知，不推断为否，也不据此宣称应用有字段读取权限。')
                 for key in ('mobile', 'email', 'avatar_url', 'join_time', 'is_frozen', 'is_resigned', 'is_activated', 'is_exited', 'is_unjoin'))
    result = [{'key': 'definition:' + key, 'object_type': 'definition', 'field': key,
               'title': title, 'requirement': requirement, 'rule': rule}
              for key, title, requirement, rule in definitions]
    for kind, entries, titles in [('department', departments, DEPARTMENT_FIELD_TITLES), ('user', users, USER_FIELD_TITLES)]:
        result.extend({'key': kind + ':' + key, 'object_type': kind, 'field': key,
                       'title': titles[key], 'requirement': requirement, 'rule': rule}
                      for key, requirement, rule in entries)
    return result


@contextmanager
def field_check(results, identifier, key, kind='user'):
    """预检收集各字段结果；全量同步仍在首个错误处终止。"""
    titles = USER_FIELD_TITLES if kind == 'user' else DEPARTMENT_FIELD_TITLES
    item = {'key': f'{kind}:{identifier}:{key}', 'object_id': identifier, 'object_type': kind, 'field': key,
            'title': titles[key], 'status': 'passed', 'message': '校验通过'}
    try:
        yield
    except InitializationFailure as exc:
        if results is None:
            raise
        item.update(status='failed', message=exc.message, issues=exc.issues)
    if results is not None:
        results.append(item)


def validate_user(raw, mappings, definitions, field_results=None):
    identifier = raw.get('user_id') if isinstance(raw.get('user_id'), str) else ''
    result_start = len(field_results) if field_results is not None else 0
    with field_check(field_results, identifier, 'user_id'):
        required_text(raw, 'user_id', 'employee', identifier)
    with field_check(field_results, identifier, 'name'):
        required_text(raw, 'name', 'employee', identifier)
    for key in ('employee_no', 'job_title'):
        with field_check(field_results, identifier, key):
            optional_text(raw, key, 'employee', identifier)
    with field_check(field_results, identifier, 'leader_user_id'):
        # 飞书会省略未配置的直属上级；不能用每个人员是否返回此键判断权限。
        optional_text(raw, 'leader_user_id', 'employee', identifier, allow_missing=True)
    with field_check(field_results, identifier, 'open_id'):
        if raw.get('open_id') is not None and (not isinstance(raw['open_id'], str) or not raw['open_id']):
            invalid('employee', identifier, 'open_id', 'open_id 格式错误')
        if isinstance(raw.get('open_id'), str) and len(raw['open_id']) > 191:
            invalid('employee', identifier, 'open_id', 'open_id 超出存储长度限制')
    departments = raw.get('department_ids')
    with field_check(field_results, identifier, 'department_ids'):
        if (not isinstance(departments, list) or any(not isinstance(d, str) or not d or len(d) > 191 for d in departments)
                or len(set(departments)) != len(departments)):
            invalid('employee', identifier, 'department_ids', '部门关系未返回或格式错误')
    orders = raw.get('orders')
    with field_check(field_results, identifier, 'orders'):
        if not isinstance(departments, list) or any(not isinstance(d, str) for d in departments):
            invalid('employee', identifier, 'orders', '所属部门格式错误，无法核验主部门')
        if orders is not None and (not isinstance(orders, list) or any(not isinstance(o, dict) for o in orders)):
            invalid('employee', identifier, 'orders', '主部门标记格式错误')
        if departments and (not isinstance(orders, list) or any(not isinstance(o, dict) for o in orders)):
            invalid('employee', identifier, 'orders', '有部门人员缺少可读取的主部门标记')
        if any(type(o.get('is_primary_dept')) is not bool or o.get('department_id') not in departments for o in (orders or [])):
            invalid('employee', identifier, 'orders', '部门顺序中的主部门标记或部门引用格式错误')
        primaries = [o.get('department_id') for o in (orders or []) if isinstance(o, dict) and o.get('is_primary_dept') is True]
        if (departments and (len(primaries) != 1 or primaries[0] not in departments)) or (not departments and primaries):
            invalid('employee', identifier, 'primary_department', '有部门人员必须有有效的唯一主部门；无部门人员不能具有主部门')
    with field_check(field_results, identifier, 'status'):
        status = raw.get('status')
        if isinstance(status, dict) and any(type(status[key]) is not bool for key in ('is_resigned', 'is_exited') if key in status):
            invalid('employee', identifier, 'status', '人员状态格式错误')
        if not isinstance(status, dict) or not any(type(status.get(k)) is bool for k in ('is_resigned', 'is_exited')):
            invalid('employee', identifier, 'status', '人员状态不可读或格式错误')
    type_id = None
    type_options = mappings.get('employee_type_options') or {}
    with field_check(field_results, identifier, 'employee_type'):
        if 'employee_type' not in raw:
            invalid('employee', identifier, 'employee_type', '员工类型未返回，无法证明字段可读')
        type_value = raw['employee_type']
        if type_value not in (None, '') and (type(type_value) not in (str, int)):
            invalid('employee', identifier, 'employee_type', '员工类型必须是枚举标识或合法空值')
        type_id = str(type_value) if type_value not in (None, '') else None
        if type_id and type_id not in type_options:
            invalid('employee', identifier, 'employee_type', '员工类型未在选项配置中定义')
    # 飞书会省略未填写的自定义字段，全部为空时连 custom_attrs 也省略。
    # 可读性由字段定义以及前面的受雇信息校验核验，不能逐人要求返回空字段。
    attrs = raw.get('custom_attrs', [])
    selected = {}
    for key in ('permission_role', 'store_attribute'):
        field_id = mappings[key]
        if field_results is not None and field_id not in definitions:
            field_results.append({'key': f'user:{identifier}:{key}', 'object_id': identifier, 'object_type': 'user', 'field': key,
                                  'title': USER_FIELD_TITLES[key], 'status': 'pending',
                                  'message': '字段定义校验未通过，尚未校验人员字段值'})
            continue
        with field_check(field_results, identifier, key):
            if field_id not in definitions:
                invalid('employee', identifier, key, '自定义字段定义不可读，请检查字段映射与飞书 API 调用设置')
            if not isinstance(attrs, list) or any(not isinstance(a, dict) for a in attrs):
                invalid('employee', identifier, 'custom_attrs', '自定义字段值格式错误，应为列表')
            matches = [a for a in attrs if a.get('id') == field_id]
            if not matches:
                selected[key] = (None, None)
                continue
            if len(matches) > 1:
                invalid('employee', identifier, key, '自定义字段不能重复返回')
            attr = matches[0]
            if key == 'store_attribute' and definitions[field_id]['type'] == 'TEXT':
                if attr.get('type') != 'TEXT' or not isinstance(attr.get('value'), dict) or 'text' not in attr['value']:
                    invalid('employee', identifier, key, '门店属性需要明确返回文本字段及 text 值')
                text = attr['value']['text']
                if text is not None and (not isinstance(text, str) or len(text) > 255):
                    invalid('employee', identifier, key, '门店属性必须为不超过 255 字符的文本或合法空值')
                selected[key] = (None, text)
                continue
            if attr.get('type') != 'ENUMERATION' or not isinstance(attr.get('value'), dict):
                invalid('employee', identifier, key, '需要单选字段对象，不能截取多选值或猜测格式')
            option_id, option_name = attr['value'].get('option_id'), attr['value'].get('option_value')
            if any(v is not None and not isinstance(v, str) for v in (option_id, option_name)):
                invalid('employee', identifier, key, '单选字段的标识和名称必须为文本')
            choices = {o['id']: o['value'] for o in definitions[field_id]['options']['options']}
            if option_id:
                if option_id not in choices or (option_name and choices[option_id] != option_name):
                    invalid('employee', identifier, key, '未知选项或选项名称与定义不一致')
                selected[key] = (option_id, choices[option_id])
            else:
                if option_name:
                    invalid('employee', identifier, key, '选项名称存在但缺少标识')
                selected[key] = (None, None)
    if field_results is not None and any(item['status'] != 'passed' for item in field_results[result_start:]):
        return None
    try:
        value = normalize_user(raw, mappings, set(type_options))
    except (RuntimeError, KeyError, TypeError):
        invalid('employee', identifier, 'status', '人员状态不可读或格式错误')
    value['employee_type_id'], value['employee_type_name'] = type_id, type_options.get(type_id)
    for key, (option_id, option_name) in selected.items():
        value[key + '_id'], value[key + '_name'] = option_id, option_name
    value['sync_quality'] = 'complete'
    if field_results is not None:
        for key, readability in value['field_readability'].items():
            field_results.append({'key': f'user:{identifier}:{key}', 'object_id': identifier,
                                  'object_type': 'user', 'field': key, 'title': USER_FIELD_TITLES[key],
                                  'status': 'passed', 'readability': readability,
                                  'message': '可读（允许合法空值）' if readability == 'readable' else
                                             '未知：接口未采集此字段' if readability == 'not_collected' else '未知：字段不可读或格式不支持'})
    return value


def validate_candidate(candidate):
    if not candidate.full or candidate.pending:
        raise InitializationFailure('INITIALIZATION_DATA_INVALID', '存在未读取成功或待核实的对象', [
            {'object_type': k, 'object_id': i, 'message': '对象读取失败'} for k, i in candidate.pending[:100]
        ])
    actual = set(candidate.employees)
    open_ids = {}
    for identifier, employee in candidate.employees.items():
        open_id = employee.get('open_id')
        if open_id and open_id in open_ids:
            invalid('employee', identifier, 'open_id', '不同人员返回了相同的 open_id')
        if open_id:
            open_ids[open_id] = identifier
    for identifier, department in candidate.departments.items():
        visited, current = set(), identifier
        while current is not None:
            if current in visited or current not in candidate.departments:
                invalid('department', identifier, 'parent_department_id', '部门层级存在环或断链')
            visited.add(current)
            current = candidate.departments[current]['parent_id']
        leader = department.get('leader_user_id')
        if leader and leader not in actual:
            invalid('department', identifier, 'leader_user_id', '部门负责人不在全量人员中')
    for identifier, employee in candidate.employees.items():
        if set(employee['department_ids']) - set(candidate.departments):
            invalid('employee', identifier, 'department_ids', '人员引用了未读取的部门')
        visited, current = set(), identifier
        while current:
            if current in visited or current not in actual:
                invalid('employee', identifier, 'leader_user_id', '直属上级关系存在环或无效引用')
            visited.add(current)
            current = candidate.employees[current].get('leader_user_id')
    candidate.coverage_status = 'complete'


class InitializationCollector(Collector):
    def __init__(self, api, mappings, definitions, progress):
        super().__init__(api, coverage_verified=True, progress=progress, custom_mappings=mappings)
        self.definitions = definitions

    def _progress(self, phase, result):
        if self.progress:
            departments = sum(not d.get('is_root') for d in result.departments.values())
            known = phase in ('validating', 'publishing')
            self.progress(phase=phase, departments_processed=departments, employees_processed=len(result.employees),
                          departments_total=departments if known else None,
                          employees_total=len(result.employees) if known else None)

    def _department(self, identifier):
        value = validate_department(self.api.detail('department', identifier))
        if value['id'] != identifier:
            invalid('department', identifier, 'id', '部门响应标识不一致')
        return value

    def _user(self, result, identifier):
        value = validate_user(self.api.detail('user', identifier), self.custom_mappings, self.definitions)
        if value['id'] != identifier:
            invalid('employee', identifier, 'id', '人员响应标识不一致')
        result.employees[identifier] = value

    def run(self):
        # 根部门接口成功才证明全员权限；不能由本地布尔配置替代。
        next(self.api.pages('users', department_id='0'))
        result = self.collect()
        self._progress('validating', result)
        validate_candidate(result)
        # 对象遍历期间出现变化时，重新确认根部门读取权限。
        next(self.api.pages('users', department_id='0'))
        return result
