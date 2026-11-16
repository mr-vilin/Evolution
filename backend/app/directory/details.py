"""管理端部门详情：本地目录资料加飞书实时只读补充，不写入同步数据集。"""
from sqlalchemy import select

from app.persistence.models import Department, Employee
from app.sync.collector import optional_user_facts


def department_details(data, sessions, api):
    result = {**data, 'leaders': [], 'chat_id': None, 'chat_name': None, 'chat_owner': None,
              'chat_status': 'unavailable', 'detail_warnings': []}
    people = {}
    with sessions() as db:
        row = db.get(Department, data['id'])
        result['feishu_department_id'] = row.feishu_department_id
        parent = db.get(Department, row.parent_id) if row.parent_id else None
        result['parent_name'] = ('本组织' if parent.is_virtual_root else parent.name) if parent else None

    def person(identifier):
        if identifier in people:
            return people[identifier]
        with sessions() as db:
            employee = db.scalar(select(Employee).where(Employee.feishu_user_id == identifier))
            value = {'user_id': identifier, 'name': employee.name, 'avatar_url': employee.avatar_url} if employee else None
        if value is None and api is not None:
            try:
                raw = api.detail('user', identifier)
                value = {'user_id': identifier, 'name': raw.get('name') or identifier,
                         'avatar_url': optional_user_facts(raw)['avatar_url']}
            except RuntimeError:
                pass
        people[identifier] = value or {'user_id': identifier, 'name': identifier, 'avatar_url': None}
        return people[identifier]

    def fallback_leader():
        if data.get('leader_user_id'):
            result['leaders'] = [{**person(data['leader_user_id']), 'leader_type': 1}]

    if data.get('is_virtual_root'):
        result['chat_status'] = 'not_applicable'
        return result
    try:
        if api is None:
            raise RuntimeError('FEISHU_NOT_CONFIGURED')
        raw = api.detail('department', result['feishu_department_id'])
    except RuntimeError:
        fallback_leader()
        result['detail_warnings'].append('飞书部门资料暂无法读取，负责人暂显示已同步信息，请稍后重试。')
        return result

    leaders = raw.get('leaders')
    if not isinstance(leaders, list):
        leaders = []
        if raw.get('leader_user_id'):
            leaders = [{'leaderID': raw['leader_user_id'], 'leaderType': 1}]
        result['detail_warnings'].append('飞书未返回完整负责人列表，暂无法确认副负责人。')
    unique = {}
    for leader in leaders:
        if not isinstance(leader, dict):
            continue
        identifier = leader.get('leaderID') or leader.get('leader_id')
        kind = leader.get('leaderType', leader.get('leader_type'))
        if isinstance(identifier, str) and identifier and type(kind) is int and kind in (1, 2):
            unique[identifier] = {**person(identifier), 'leader_type': kind}
    result['leaders'] = sorted(unique.values(), key=lambda item: item['leader_type'])
    if 'chat_id' not in raw or raw['chat_id'] is None:
        result['detail_warnings'].append('飞书未返回部门群信息，请检查部门群字段权限。')
    elif raw['chat_id'] == '':
        result['chat_status'] = 'not_set'
    elif isinstance(raw['chat_id'], str):
        result['chat_id'] = raw['chat_id']
        try:
            chat = api.chat(raw['chat_id'])
            result['chat_name'] = chat.get('name') or None
            result['chat_status'] = 'available'
            if chat.get('owner_id'):
                result['chat_owner'] = person(chat['owner_id'])
        except RuntimeError as error:
            result['detail_warnings'].append('读取部门群资料需要开通飞书群信息只读权限（im:chat:read）并发布应用版本。'
                                             if str(error) == 'FEISHU_PERMISSION_REQUIRED' else
                                             '部门群资料暂无法读取，请检查群信息权限及应用可见范围，或稍后重试。')
    return result
