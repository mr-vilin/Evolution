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
                              name=name, is_virtual_root=identifier == '0', sync_quality='complete'))
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
    assert body['data'][0]['has_children'] is True
    assert body['data'][1]['has_children'] is False
    found = client.get('/admin/api/organization/search', params={'keyword': '民路', 'dataset_epoch': 'e', 'data_version': 1}).json()
    assert {row['id'] for row in found['data']} == {'0', 'a', 'b', 'c'}
    assert found['meta']['matched_ids'] == ['c']
    assert client.get('/admin/api/organization/search', params={'keyword': 'c'}).json()['data'] == []


def test_selection_cycle_includes_unloaded_descendants_and_preserves_partial_branches(organization_client):
    client, _ = organization_client
    def toggle(selected, target):
        response = client.post('/admin/api/organization/selection', json={
            'dataset_epoch': 'e', 'data_version': 1, 'selected_ids': selected, 'toggle_id': target})
        assert response.status_code == 200
        return response.json()['data']
    first = toggle(['x'], 'a')
    assert first['selected_ids'] == ['a', 'x']
    second = toggle(first['selected_ids'], 'a')
    assert second['selected_ids'] == ['a', 'b', 'c', 'x']
    assert second['count'] == 4
    partial = toggle(second['selected_ids'], 'c')
    assert partial['states']['a'] == {'self_selected': True, 'descendants': 'partial'}
    assert toggle(partial['selected_ids'], 'a')['selected_ids'] == ['b', 'x']
    assert toggle(['b', 'x'], 'a')['selected_ids'] == ['x']
    assert toggle(['a', 'b', 'c'], 'a')['selected_ids'] == ['b', 'c']
    assert toggle(['b', 'c'], 'a')['selected_ids'] == []
    assert toggle([], '0')['selected_ids'] == ['a', 'b', 'c', 'x']
    assert toggle(['x'], '0')['selected_ids'] == []
    assert toggle([], 'c')['selected_ids'] == ['c']
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
            db.add(EmployeeDepartment(employee_id=identifier, department_id='b', active=True))
            db.add(EmployeeDepartment(employee_id=identifier, department_id='c', active=True))
        db.add(Employee(id='old', feishu_user_id='old', name='历史成员', is_activated=True))
        db.flush()
        db.add(EmployeeDepartment(employee_id='old', department_id='a', active=False))
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
    assert found(include_descendants=False)['meta']['total_count'] == 0
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
    assert employee['mobile'] == ''
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
