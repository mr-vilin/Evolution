"""组织工作台 HTTP 契约；SQLite 合成数据不替代真实 MySQL 验收。"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_admin_identity, get_runtime, require_admin_write
from app.main import app
from app.persistence.models import Department, Employee, EmployeeDepartment
from app.persistence.read_service import SqlReadService


@pytest.fixture
def organization_client(sqlite_sessions):
    with sqlite_sessions.begin() as db:
        for identifier, parent, name in [('0', None, '组织'), ('a', '0', '总部'), ('b', 'a', '区域'), ('c', 'b', '人民路店'), ('x', '0', '其他')]:
            db.add(Department(id=identifier, feishu_department_id=identifier, parent_id=parent,
                              name=name, is_root=identifier == '0', sync_quality='complete'))
            db.flush()
    identity = SimpleNamespace(open_id='admin')
    app.dependency_overrides[get_admin_identity] = lambda: identity
    app.dependency_overrides[require_admin_write] = lambda: (identity, None)
    app.dependency_overrides[get_runtime] = lambda: SimpleNamespace(
        sessions=sqlite_sessions, reads=SqlReadService(sqlite_sessions, 'test-secret'))
    try:
        yield TestClient(app), sqlite_sessions
    finally:
        app.dependency_overrides.clear()


def test_initial_tree_only_reads_top_level_and_search_returns_ancestors(organization_client):
    client, _ = organization_client
    response = client.get('/admin/api/organization/departments', params={'parent_id': '0', 'limit': 20})
    assert response.status_code == 200
    body = response.json()
    assert [row['id'] for row in body['data']] == ['a', 'x']
    assert all(row['is_root'] is False and 'is_virtual_root' not in row for row in body['data'])
    assert body['data'][0]['has_children'] is True
    assert body['data'][1]['has_children'] is False
    found = client.get('/admin/api/organization/search', params={'keyword': '民路', 'dataset_epoch': 'e', 'data_version': 1}).json()
    assert {row['id'] for row in found['data']} == {'0', 'a', 'b', 'c'}
    assert [row['id'] for row in found['data'] if row['is_root'] is True] == ['0']
    assert found['meta']['matched_ids'] == ['c']
    assert client.get('/admin/api/organization/search', params={'keyword': 'c'}).json()['data'] == []


def test_company_summary_counts_all_records_once_and_only_explicit_status_facts(organization_client):
    client, sessions = organization_client
    params = {'dataset_epoch': 'e', 'data_version': 1}
    empty = client.get('/admin/api/organization/summary', params=params)
    assert empty.status_code == 200
    assert empty.json()['data'] == dict(department_id='0', department_count=4, employee_count=0,
                                       unactivated_count=0, unjoin_count=0, resigned_count=0, member_count=0, members_limited=False)
    with sessions.begin() as db:
        db.get(Department, 'x').status = 'inactive'
        db.add_all([
            Employee(id='a1', feishu_user_id='a1', name='重叠状态', is_activated=False, is_unjoin=True),
            Employee(id='a2', feishu_user_id='a2', name='历史离职', status='inactive', is_resigned=True),
            Employee(id='a3', feishu_user_id='a3', name='未知状态'),
            Employee(id='a4', feishu_user_id='a4', name='已激活', is_activated=True, is_unjoin=False, is_resigned=False),
        ])
        db.flush()
        db.add_all([EmployeeDepartment(employee_id='a1', department_id='a', is_active=True),
                    EmployeeDepartment(employee_id='a1', department_id='b', is_active=True)])
    response = client.get('/admin/api/organization/summary', params=params).json()
    assert response['data'] == dict(department_id='0', department_count=3, employee_count=4,
                                    unactivated_count=1, unjoin_count=1, resigned_count=1, member_count=3, members_limited=False)
    assert response['meta']['dataset_epoch'] == 'e'
    assert response['meta']['data_version'] == 1
    assert client.get('/admin/api/organization/summary', params={**params, 'dataset_epoch': 'old'}).status_code == 409
    assert client.get('/admin/api/organization/summary', params={**params, 'data_version': 0}).status_code == 409
    from app.dependencies import get_admin_identity
    del app.dependency_overrides[get_admin_identity]
    assert client.get('/admin/api/organization/summary', params=params).status_code == 401


def test_selection_cycle_includes_unloaded_descendants_and_preserves_partial_branches(organization_client):
    client, _ = organization_client
    def toggle(selected, target):
        response = client.post('/admin/api/organization/selection', json={
            'dataset_epoch': 'e', 'data_version': 1, 'selected_ids': selected, 'toggle_id': target})
        assert response.status_code == 200
        return response.json()['data']
    first = toggle(['x'], 'a')
    assert first['selected_ids'] == ['a', 'x']
    assert first['states']['a']['selected_count'] == 1
    assert first['states']['0']['selected_count'] == 2
    second = toggle(first['selected_ids'], 'a')
    assert second['selected_ids'] == ['a', 'b', 'c', 'x']
    assert second['count'] == 4
    assert second['states']['a']['selected_count'] == 3
    partial = toggle(second['selected_ids'], 'c')
    assert partial['states']['a'] == {'self_selected': True, 'descendants': 'partial', 'selected_count': 2}
    assert toggle(partial['selected_ids'], 'a')['selected_ids'] == ['b', 'x']
    assert toggle(['b', 'x'], 'a')['selected_ids'] == ['x']
    descendants = toggle(['a', 'b', 'c'], 'a')
    assert descendants['selected_ids'] == ['b', 'c']
    assert descendants['states']['a']['selected_count'] == 2
    assert toggle(['b', 'c'], 'a')['selected_ids'] == []
    assert toggle([], '0')['selected_ids'] == ['a', 'b', 'c', 'x']
    assert toggle(['x'], '0')['selected_ids'] == []
    leaf = toggle([], 'c')
    assert leaf['selected_ids'] == ['c']
    assert leaf['states']['c']['selected_count'] == 1
    assert leaf['states']['a']['selected_count'] == 1
    assert client.post('/admin/api/organization/selection', json={
        'dataset_epoch': 'old', 'data_version': 1, 'selected_ids': []}).status_code == 409


def test_members_are_paged_deduplicated_and_filtered_by_raw_facts(organization_client):
    client, sessions = organization_client
    with sessions.begin() as db:
        for index in range(45):
            identifier = f'u{index:02}'
            db.add(Employee(id=identifier, feishu_user_id=identifier, name=f'测试成员{index}',
                            mobile='+8613800000000' if index == 0 else None,
                            is_activated=True if index == 0 else False if index == 1 else None,
                            is_frozen=True if index == 0 else None,
                            is_unjoin=False if index == 0 else None,
                            is_resigned=False if index == 0 else None,
                            is_exited=False if index == 0 else None))
            db.flush()
            db.add(EmployeeDepartment(employee_id=identifier, department_id='a', is_active=True))
            db.add(EmployeeDepartment(employee_id=identifier, department_id='c', is_active=True))
        db.add(Employee(id='old', feishu_user_id='old', name='历史成员', is_activated=True))
        db.flush()
        db.add(EmployeeDepartment(employee_id='old', department_id='a', is_active=False))
    params = {'department_id': 'a', 'include_descendants': True, 'dataset_epoch': 'e', 'data_version': 1, 'limit': 20}
    first = client.get('/admin/api/organization/employees', params=params).json()
    assert len(first['data']) == 20 and first['meta']['total_count'] == 45
    second = client.get('/admin/api/organization/employees', params={**params, 'cursor': first['meta']['next_cursor']}).json()
    third = client.get('/admin/api/organization/employees', params={**params, 'cursor': second['meta']['next_cursor']}).json()
    assert len(second['data']) == 20 and len(third['data']) == 5
    assert third['meta']['next_cursor'] is None
    assert len({row['id'] for row in first['data'] + second['data'] + third['data']}) == 45
    def found(**extra):
        return client.get('/admin/api/organization/employees', params={**params, **extra}).json()
    assert found(keyword='  +8613800000000  ')['meta']['total_count'] == 1
    assert found(keyword='000000')['data'] == []
    assert found(keyword='u00')['data'][0]['user_id'] == 'u00'
    assert found(keyword='试成员')['meta']['total_count'] == 45
    assert found(account_status='activated')['meta']['total_count'] == 1
    assert found(account_status='frozen')['meta']['total_count'] == 1
    assert found(account_status='unactivated')['meta']['total_count'] == 1
    assert found(account_status='unknown')['meta']['total_count'] == 44
    assert found(include_descendants=False)['meta']['total_count'] == 45
    assert first['meta']['members_limited'] is True
    assert first['meta']['include_descendants'] is False
    assert client.get('/admin/api/organization/employees', params={**params, 'cursor': first['meta']['next_cursor'], 'keyword': 'changed'}).status_code == 400


def test_sibling_order_persists_without_changing_parent_and_rejects_stale_writes(organization_client):
    client, _ = organization_client
    body = {'dataset_epoch': 'e', 'data_version': 1, 'department_id': 'x', 'parent_id': '0', 'anchor_id': 'a', 'position': 'before'}
    response = client.post('/admin/api/organization/order', json=body)
    assert response.status_code == 200
    assert response.json()['meta']['data_version'] == 2
    rows = client.get('/admin/api/organization/departments', params={'parent_id': '0', 'limit': 1}).json()
    assert rows['data'][0]['id'] == 'x' and rows['data'][0]['parent_id'] == '0'
    tail = client.get('/admin/api/organization/departments', params={'parent_id': '0', 'limit': 1, 'cursor': rows['meta']['next_cursor']}).json()
    assert [row['id'] for row in tail['data']] == ['a']
    assert client.post('/admin/api/organization/order', json=body).status_code == 409
    assert client.post('/admin/api/organization/order', json={**body, 'data_version': 2, 'department_id': 'c'}).status_code == 422


def test_account_badges_follow_member_scope_without_search_or_status_filter(organization_client):
    client, sessions = organization_client
    with sessions.begin() as db:
        db.add_all([
            Employee(id='direct', feishu_user_id='direct', name='直属', is_activated=True, is_frozen=False,
                     is_unjoin=False, is_resigned=False, is_exited=False),
            Employee(id='child', feishu_user_id='child', name='下级', is_activated=False, is_frozen=True, is_unjoin=True),
            Employee(id='past', feishu_user_id='past', name='历史', status='inactive', is_activated=False),
        ])
        db.flush()
        db.add_all([EmployeeDepartment(employee_id='direct', department_id='a', is_active=True),
                    EmployeeDepartment(employee_id='direct', department_id='c', is_active=True),
                    EmployeeDepartment(employee_id='child', department_id='c', is_active=True),
                    EmployeeDepartment(employee_id='past', department_id='a', is_active=False)])
    params = dict(department_id='a', dataset_epoch='e', data_version=1)
    def read(**extra):
        return client.get('/admin/api/organization/employees', params={**params, **extra}).json()
    direct = read()['meta']['account_status_counts']
    assert direct == dict(activated=1, unactivated=0, frozen=0, unjoin=0, unknown=0)
    complete = read(include_descendants=True)['meta']['account_status_counts']
    assert complete == dict(activated=1, unactivated=1, frozen=1, unjoin=1, unknown=1)
    assert read(include_descendants=True, account_status='activated', keyword='不存在')['meta']['account_status_counts'] == complete
    # 普通搜索仍能找到下级；数标保持下拉框所选的直属范围。
    searched = read(keyword='下级')
    assert searched['meta']['total_count'] == 1
    assert searched['meta']['account_status_counts'] == direct
    assert read(department_id='x')['meta']['account_status_counts'] == dict.fromkeys(direct, 0)


@pytest.mark.parametrize('view_status', ['unactivated', 'unjoin', 'resigned'])
def test_panel_view_matches_global_summary_includes_history_and_pages(organization_client, view_status):
    from app.persistence.models import DatasetState
    client, sessions = organization_client
    with sessions.begin() as db:
        for index in range(45):
            identifier = f'panel{index:02}'
            db.add(Employee(id=identifier, feishu_user_id=identifier, name=f'状态人员{index}',
                            status='inactive' if index % 2 else 'active',
                            is_activated=False, is_unjoin=True, is_resigned=True))
        db.add(Employee(id='unknown', feishu_user_id='unknown', name='未知'))
    params = dict(department_id='0', dataset_epoch='e', data_version=1, view_status=view_status)
    summary = client.get('/admin/api/organization/summary', params=params).json()['data']
    pages, cursor = [], None
    for expected in [20, 20, 5]:
        response = client.get('/admin/api/organization/employees', params={**params, **({'cursor': cursor} if cursor else {})})
        assert response.status_code == 200
        result = response.json()
        assert len(result['data']) == expected
        assert result['meta']['total_count'] == summary[f'{view_status}_count'] == 45
        pages.extend(result['data'])
        cursor = result['meta']['next_cursor']
    assert cursor is None and len({row['id'] for row in pages}) == 45
    assert {row['status'] for row in pages} == {'active', 'inactive'}
    searched = client.get('/admin/api/organization/employees', params={**params, 'keyword': 'panel01', 'account_status': 'activated'}).json()
    assert [row['id'] for row in searched['data']] == ['panel01']
    first = client.get('/admin/api/organization/employees', params=params).json()
    assert client.get('/admin/api/organization/employees', params={**params, 'cursor': first['meta']['next_cursor'], 'view_status': 'none'}).status_code == 400
    assert client.get('/admin/api/organization/employees', params={**params, 'data_version': 0}).status_code == 409
    assert client.get('/admin/api/organization/employees', params={**params, 'view_status': 'other'}).status_code == 422
    with sessions() as db:
        assert db.get(DatasetState, 1).data_version == 1
    del app.dependency_overrides[get_admin_identity]
    assert client.get('/admin/api/organization/employees', params=params).status_code == 401


def test_sync_preserves_local_order_appends_moves_and_keeps_raw_optional_facts(organization_client):
    from app.sync.collector import Collector
    from app.sync.publisher import Publisher
    client, sessions = organization_client
    client.post('/admin/api/organization/order', json={
        'dataset_epoch': 'e', 'data_version': 1, 'department_id': 'x', 'parent_id': '0', 'anchor_id': 'a', 'position': 'before'})
    class FeishuResponse:
        def detail(self, kind, identifier):
            if kind == 'department':
                return {'open_department_id': identifier, 'parent_department_id': '0', 'name': identifier, 'status': {'is_deleted': False}}
            return {'user_id': 'u', 'name': '人员', 'department_ids': ['a'], 'mobile': '',
                    'status': {'is_resigned': False, 'is_exited': False, 'is_activated': False, 'is_frozen': True}}
    publisher = Publisher(sessions)
    collector = Collector(FeishuResponse())
    publisher.publish(collector.event('contact.department.updated_v3', 'a'))
    publisher.publish(collector.event('contact.department.updated_v3', 'c'))
    publisher.publish(collector.event('contact.user.updated_v3', 'u'))
    rows = client.get('/admin/api/organization/departments').json()['data']
    assert [row['id'] for row in rows] == ['x', 'a', 'c']
    employee = client.get('/admin/api/employees/u').json()['data']
    assert employee['mobile'] is None
    assert employee['sync_quality'] == 'pending_verification'
    assert employee['field_readability']['mobile'] == 'readable'
    assert employee['account_status']['is_activated'] is False
    assert employee['account_status']['is_unjoin'] is None
    assert employee['field_readability']['is_unjoin'] == 'not_collected'


def test_organization_direct_save_over_500_is_atomic_epoch_bound_and_isolated_from_other_entrypoints(organization_client):
    from app.persistence.models import DatasetState, StoreProfile
    client, sessions = organization_client
    with sessions.begin() as db:
        db.add_all([Department(id=f's{i:03}', feishu_department_id=f's{i:03}', parent_id='a', name=f'门店{i}') for i in range(501)])
    changes = [{'department_id': f's{i:03}', 'is_store': True, 'store_code': f'S{i:03}'} for i in range(501)]
    body = {'dataset_epoch': 'e', 'data_version': 1, 'changes': changes}
    assert client.post('/admin/api/stores/batch/apply', json=body).status_code == 422
    assert client.post('/admin/api/organization/stores', json={**body, 'dataset_epoch': 'old'}).status_code == 409
    bad = {**body, 'changes': changes + [{'department_id': '0', 'is_store': False}]}
    assert client.post('/admin/api/organization/stores', json=bad).status_code == 422
    with sessions() as db:
        assert db.get(StoreProfile, 's000') is None
        assert db.get(DatasetState, 1).data_version == 1
    response = client.post('/admin/api/organization/stores', json=body)
    assert response.status_code == 200
    assert response.json()['data']['saved_count'] == 501
    assert response.json()['meta'] == {'dataset_epoch': 'e', 'data_version': 2}
    with sessions() as db:
        assert db.get(StoreProfile, 's500').store_code == 'S500'


@pytest.mark.parametrize('count', [20, 21])
def test_member_limit_is_based_on_unfiltered_deduplicated_subtree(organization_client, count):
    client, sessions = organization_client
    with sessions.begin() as db:
        for index in range(count):
            identifier = f't{index:02}'
            db.add(Employee(id=identifier, feishu_user_id=identifier, name=f'成员{index}',
                            job_title='工程师', email='person@example.test', employee_type_name='正式员工',
                            field_readability={'email': 'readable'}))
            db.flush()
            db.add(EmployeeDepartment(employee_id=identifier, department_id='c', is_active=True))
            if index == 0:
                db.add(EmployeeDepartment(employee_id=identifier, department_id='a', is_active=True))
    params = {'dataset_epoch': 'e', 'data_version': 1, 'department_id': 'a'}
    summary = client.get('/admin/api/organization/summary', params=params).json()['data']
    assert summary['member_count'] == count
    assert summary['department_count'] == 3
    assert summary['employee_count'] == count
    assert summary['members_limited'] == (count > 20)
    result = client.get('/admin/api/organization/employees', params={**params, 'include_descendants': True}).json()
    assert result['meta']['total_count'] == (count if count <= 20 else 1)
    # 搜索独立于浏览范围，超限部门也能找到下级成员。
    filtered = client.get('/admin/api/organization/employees', params={**params, 'include_descendants': True, 'keyword': 't01'}).json()
    assert filtered['meta']['total_count'] == 1
    direct_search = client.get('/admin/api/organization/employees', params={**params, 'include_descendants': False, 'keyword': 't01'}).json()
    assert direct_search['data'] == filtered['data']
    assert direct_search['meta']['include_descendants'] is True
    whitespace = client.get('/admin/api/organization/employees', params={**params, 'include_descendants': False, 'keyword': '   '}).json()
    assert whitespace['meta']['total_count'] == 1
    outside = client.get('/admin/api/organization/employees', params={**params, 'department_id': 'x', 'keyword': 't01'}).json()
    assert outside['data'] == []
    row = result['data'][0]
    assert row['email'] == 'person@example.test'
    assert row['job_title'] == '工程师'
    assert row['employee_type_name'] == '正式员工'
    assert {department['id'] for department in row['departments']} == {'a', 'c'}
    company = client.get('/admin/api/organization/employees', params={**params, 'department_id': '0', 'include_descendants': True}).json()
    assert company['meta']['total_count'] == (count if count <= 20 else 0)
    assert client.get('/admin/api/organization/summary', params={**params, 'department_id': 'x'}).json()['data']['employee_count'] == 0


@pytest.mark.parametrize(('raw', 'value', 'readability'), [
    ({}, None, 'not_collected'), ({'email': ''}, '', 'readable'),
    ({'email': ' person@example.test '}, 'person@example.test', 'readable'),
    ({'email': 12}, None, 'unreadable'), ({'email': 'x' * 255}, None, 'unreadable'),
])
def test_email_collection_preserves_missing_empty_and_unreadable(raw, value, readability):
    from app.sync.collector import optional_user_facts
    facts = optional_user_facts(raw)
    assert facts['email'] == value
    assert facts['field_readability']['email'] == readability
