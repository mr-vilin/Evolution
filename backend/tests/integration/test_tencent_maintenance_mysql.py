from app.persistence.models import DatasetState
from test_tencent_accounts_mysql import tencent_http


def test_credential_options_require_complete_initialization(tencent_http):
    client, sessions, calls = tencent_http
    with sessions.begin() as db:
        db.get(DatasetState, 1).initialization_status = 'pending'
    response = client.get('/admin/api/tencent/credential-options')
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'INITIALIZATION_INCOMPLETE'
    assert calls == []


def test_alias_maintenance_uses_optimistic_revision_without_revalidating_credentials(tencent_http):
    client, sessions, calls = tencent_http
    original = client.post('/admin/api/tencent/accounts', json={
        'uin': '10001', 'alias': '原别名', 'credential_ref': 'finance-a'}).json()['data']
    response = client.patch('/admin/api/tencent/accounts/' + original['id'], json={'revision': 1, 'alias': '  财务主账号  '})
    assert response.status_code == 200, response.text
    updated = response.json()['data']
    assert updated['alias'] == '财务主账号'
    assert updated['revision'] == 2
    assert updated['credential_revision'] == original['credential_revision']
    assert calls == [('DescribeAccountBalance', {})]
    stale = client.patch('/admin/api/tencent/accounts/' + original['id'], json={'revision': 1, 'alias': '过时编辑'})
    assert stale.status_code == 409
    assert stale.json()['error']['code'] == 'TENCENT_ACCOUNT_CONFLICT'
    assert client.get('/admin/api/tencent/accounts').json()['data'][0]['alias'] == '财务主账号'


def test_disabling_and_reenabling_fences_queued_work_and_preserves_successful_costs(tencent_http):
    from app.config import get_settings
    from app.main import app
    from app.tencent.cost_worker import TencentCostWorker
    from test_tencent_cost_mysql import enable_cost, run_job
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin': '10001', 'alias': '主账号', 'credential_ref': 'finance-a'}).json()['data']
    path = '/admin/api/tencent/accounts/' + account['id']
    enable_cost(client, account)
    completed = run_job(client, sessions, account, 'original-cost')
    pending = client.post(path + '/cost-jobs', json={'month': '2026-10', 'idempotency_key': 'before-disable'})
    disabled = client.patch(path, json={'revision': 1, 'is_enabled': False})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()['data']['credential_revision'] == 2
    assert client.get(path + '/balance').json()['error']['code'] == 'TENCENT_ACCOUNT_UNAVAILABLE'
    assert client.post(path + '/cost-jobs', json={'month': '2026-10', 'idempotency_key': 'disabled-new'}).status_code == 409
    enabled = client.patch(path, json={'revision': 2, 'is_enabled': True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()['data']['credential_revision'] == 3
    outbound = []
    worker = TencentCostWorker(sessions, app.dependency_overrides[get_settings](), lambda *args: outbound.append(args))
    assert worker.run_once() is False
    rejected = client.get(pending.headers['location']).json()['data']
    assert rejected['status'] == 'failed'
    assert rejected['error_code'] == 'TENCENT_CREDENTIAL_CHANGED'
    assert rejected['attempts'] == []
    assert outbound == []
    assert client.get(path + '/cost-periods/2026-10').json()['data']['total'] == '12.00000000'
    assert client.get('/admin/api/tencent/cost-jobs/' + completed['id']).json()['data']['attempts'][0]['status'] == 'succeeded'
    assert run_job(client, sessions, account, 'after-reenable')['status'] == 'succeeded'


def test_credential_rotation_requires_same_uin_and_keeps_original_binding_on_failure(tencent_http):
    from app.main import app
    from app.tencent.gateway import get_tencent_transport
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin': '10001', 'alias': '主账号', 'credential_ref': 'finance-a'}).json()['data']
    path = '/admin/api/tencent/accounts/' + account['id']
    app.dependency_overrides[get_tencent_transport] = lambda: lambda *_: b'{"Response":{"Uin":20002,"RequestId":"wrong-owner"}}'
    mismatch = client.patch(path, json={'revision': 1, 'credential_ref': 'finance-b'})
    assert mismatch.status_code == 422, mismatch.text
    assert mismatch.json()['error']['code'] == 'TENCENT_ACCOUNT_MISMATCH'
    assert client.get('/admin/api/tencent/accounts').json()['data'][0] == account
    seen = []
    def same_owner(credential, action, params):
        seen.append((credential.label, action))
        return b'{"Response":{"Uin":10001,"RequestId":"same-owner"}}'
    app.dependency_overrides[get_tencent_transport] = lambda: same_owner
    rotated = client.patch(path, json={'revision': 1, 'credential_ref': 'finance-b'})
    assert rotated.status_code == 200, rotated.text
    data = rotated.json()['data']
    assert data['uin'] == '10001'
    assert data['credential_ref'] == 'finance-b'
    assert data['revision'] == 2 and data['credential_revision'] == 2
    assert seen == [('生产只读账号 B', 'DescribeAccountBalance')]
    assert 'synthetic-key' not in rotated.text


import json
import pytest
from app.main import app
from app.tencent.gateway import get_tencent_transport


@pytest.mark.parametrize('denied_action', ['DescribeCostExplorerSummary', 'DescribeBillSummaryByProduct'])
def test_rotation_checks_every_enabled_cost_action_and_does_not_publish_unverified_binding(tencent_http, denied_action):
    from test_tencent_cost_mysql import enable_cost
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin': '10001', 'alias': '成本账号', 'credential_ref': 'finance-a'}).json()['data']
    enable_cost(client, account)
    seen = []
    def limited(credential, action, params):
        seen.append(action)
        if action == denied_action:
            return b'{"Response":{"Error":{"Code":"UnauthorizedOperation","Message":"synthetic-key never disclose"},"RequestId":"permission-check-denied"}}'
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"rotation-owner"}}'
        return b'{"Response":{"Total":0,"Detail":[],"RequestId":"rotation-cost"}}'
    app.dependency_overrides[get_tencent_transport] = lambda: limited
    response = client.patch('/admin/api/tencent/accounts/' + account['id'], json={'revision': 1, 'credential_ref': 'finance-b'})
    assert response.status_code == 502, response.text
    assert response.json()['error']['code'] == 'TENCENT_PERMISSION_DENIED'
    assert seen == ['DescribeAccountBalance', 'DescribeCostExplorerSummary'] + (['DescribeBillSummaryByProduct'] if denied_action == 'DescribeBillSummaryByProduct' else [])
    assert client.get('/admin/api/tencent/accounts').json()['data'][0] == account
    assert 'synthetic-key' not in response.text


@pytest.mark.parametrize('change,expected', [('enable-cost', 'TENCENT_CAPABILITY_CHANGED'), ('toggle-cost', 'TENCENT_CAPABILITY_CHANGED'),
    ('alias', 'TENCENT_ACCOUNT_CONFLICT'), ('account-toggle', 'TENCENT_ACCOUNT_CONFLICT'), ('epoch', 'DATASET_CHANGED'),
    ('admin', 'ADMIN_SESSION_REQUIRED'), ('initialization', 'INITIALIZATION_INCOMPLETE')])
def test_rotation_rechecks_current_qualification_after_external_validation(tencent_http, change, expected):
    from sqlalchemy import delete
    from app.persistence.models import AdminAllowlist, TencentAccount
    from test_tencent_cost_mysql import enable_cost
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin': '10001', 'alias': '主账号', 'credential_ref': 'finance-a'}).json()['data']
    path = '/admin/api/tencent/accounts/' + account['id']
    if change == 'toggle-cost':
        enable_cost(client, account)
    changed = False
    def racing(credential, action, params):
        nonlocal changed
        if not changed:
            changed = True
            if change == 'enable-cost':
                enable_cost(client, account)
            if change == 'toggle-cost':
                off = client.put(path + '/cost-config', json={'revision': 1, 'is_enabled': False, 'frequency': 'manual', 'currency': 'CNY'})
                assert off.status_code == 200
                on = client.put(path + '/cost-config', json={'revision': 2, 'is_enabled': True, 'frequency': 'manual', 'currency': 'CNY'})
                assert on.status_code == 200
            if change == 'alias':
                assert client.patch(path, json={'revision': 1, 'alias': '另一位管理员'}).status_code == 200
            if change == 'account-toggle':
                assert client.patch(path, json={'revision': 1, 'is_enabled': False}).status_code == 200
                assert client.patch(path, json={'revision': 2, 'is_enabled': True}).status_code == 200
            with sessions.begin() as db:
                if change == 'epoch': db.get(DatasetState, 1).dataset_epoch = 'later-epoch'
                if change == 'admin': db.execute(delete(AdminAllowlist))
                if change == 'initialization': db.get(DatasetState, 1).initialization_status = 'pending'
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"rotation-owner"}}'
        if action == 'DescribeBillSummaryByProduct':
            return b'{"Response":{"Ready":0,"RequestId":"rotation-not-ready"}}'
        return b'{"Response":{"Total":0,"Detail":[],"RequestId":"rotation-cost"}}'
    app.dependency_overrides[get_tencent_transport] = lambda: racing
    response = client.patch(path, json={'revision': 1, 'credential_ref': 'finance-b'})
    assert response.status_code in {401, 409}, response.text
    assert response.json()['error']['code'] == expected
    with sessions() as db:
        assert db.get(TencentAccount, int(account['id'])).credential_ref == 'finance-a'


@pytest.mark.parametrize('change,status', [('alias', 200), ('disable-enable', 409), ('rotate', 409)])
def test_balance_inflight_uses_security_fence_but_survives_alias_edit(tencent_http, change, status):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from test_tencent_balance_mysql import BALANCE
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin': '10001', 'alias': '原别名', 'credential_ref': 'finance-a'}).json()['data']
    path = '/admin/api/tencent/accounts/' + account['id']
    entered, release = Event(), Event()
    def delayed(*_):
        entered.set()
        assert release.wait(timeout=10)
        return BALANCE
    app.dependency_overrides[get_tencent_transport] = lambda: delayed
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(client.get, path + '/balance')
        assert entered.wait(timeout=10)
        try:
            if change == 'alias':
                changed = client.patch(path, json={'revision': 1, 'alias': '新别名'})
            elif change == 'disable-enable':
                assert client.patch(path, json={'revision': 1, 'is_enabled': False}).status_code == 200
                changed = client.patch(path, json={'revision': 2, 'is_enabled': True})
            else:
                # 已进入的余额调用保留自己的传输；轮换使用当前新请求的传输。
                app.dependency_overrides[get_tencent_transport] = lambda: lambda *_: BALANCE
                changed = client.patch(path, json={'revision': 1, 'credential_ref': 'finance-b'})
            assert changed.status_code == 200, changed.text
        finally:
            release.set()
        response = pending.result(timeout=10)
    assert response.status_code == status, response.text
    if status == 409:
        assert response.json()['error']['code'] == 'TENCENT_CREDENTIAL_CHANGED'
        assert 'amounts' not in response.text
    else:
        assert response.json()['data']['amounts']['real_balance'] == '90071992547409.9112345678'


@pytest.mark.parametrize('change,success', [('alias', True), ('disable-enable', False), ('rotate', False)])
def test_actual_worker_inflight_does_not_cross_account_security_change(tencent_http, change, success):
    from app.config import get_settings
    from app.tencent.cost_worker import TencentCostWorker
    from test_tencent_cost_mysql import enable_cost, run_job, wire
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin': '10001', 'alias': '成本账号', 'credential_ref': 'finance-a'}).json()['data']
    path = '/admin/api/tencent/accounts/' + account['id']
    enable_cost(client, account)
    original = run_job(client, sessions, account, 'original')
    accepted = client.post(path + '/cost-jobs', json={'month': '2026-10', 'idempotency_key': 'inflight'})
    changed = False
    def racing(credential, action, params):
        nonlocal changed
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"worker-owner"}}'
        if action == 'DescribeBillSummaryByProduct':
            return b'{"Response":{"Ready":1,"RequestId":"rotation-aux"}}'
        if not changed:
            changed = True
            if change == 'alias':
                result = client.patch(path, json={'revision': 1, 'alias': '新别名'})
            elif change == 'disable-enable':
                assert client.patch(path, json={'revision': 1, 'is_enabled': False}).status_code == 200
                result = client.patch(path, json={'revision': 2, 'is_enabled': True})
            else:
                result = client.patch(path, json={'revision': 1, 'credential_ref': 'finance-b'})
            assert result.status_code == 200, result.text
        value = wire(single=True)
        if params['PageNo'] > 1:
            value['Response']['Detail'] = []
        return json.dumps(value).encode()
    app.dependency_overrides[get_tencent_transport] = lambda: racing
    worker = TencentCostWorker(sessions, app.dependency_overrides[get_settings](), racing)
    assert worker.run_once()
    result = client.get(accepted.headers['location']).json()['data']
    current = client.get(path + '/cost-periods/2026-10').json()['data']
    assert result['status'] == ('succeeded' if success else 'failed')
    assert current['total'] == ('12.34567890' if success else '12.00000000')
    if not success:
        assert result['error_code'] == 'TENCENT_CREDENTIAL_CHANGED'
        assert current['latest_job_id'] == original['id']
    else:
        assert result['attempts'][0]['execution_input']['credential_revision'] == account['credential_revision']


def test_rotation_not_ready_is_distinct_from_permission_denial_and_audits_metadata_only(tencent_http):
    from sqlalchemy import select
    from app.persistence.models import TencentApiCall, ChangeLog
    from test_tencent_cost_mysql import enable_cost
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin': '10001', 'alias': '主账号', 'credential_ref': 'finance-a'}).json()['data']
    enable_cost(client, account)
    credentials = []
    def permitted(credential, action, params):
        credentials.append(credential)
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RealBalance":123456789,"RequestId":"owner-safe"}}'
        if action == 'DescribeBillSummaryByProduct':
            return b'{"Response":{"Ready":0,"SummaryTotal":null,"SummaryOverview":null,"RequestId":"not-ready-safe"}}'
        return b'{"Response":{"Total":0,"Detail":[],"RequestId":"cost-safe"}}'
    app.dependency_overrides[get_tencent_transport] = lambda: permitted
    response = client.patch('/admin/api/tencent/accounts/' + account['id'], json={'revision': 1, 'credential_ref': 'finance-b'})
    assert response.status_code == 200, response.text
    assert response.json()['meta']['verification']['auxiliary_readiness'] == 'not_ready'
    assert len(credentials) == 3 and all(value is credentials[0] for value in credentials)
    with sessions() as db:
        rows = db.scalars(select(TencentApiCall).where(TencentApiCall.request_id == response.headers['x-request-id'])).all()
        assert len(rows) == 4
        assert {row.target_id for row in rows} == {'10001'}
        assert next(row for row in rows if row.direction == 'inbound').action == 'tencent.account.update'
        assert all(row.outcome == 'succeeded' for row in rows)
        changes = db.scalars(select(ChangeLog).where(ChangeLog.object_type == 'tencent_account', ChangeLog.object_id == account['id'])).all()
        assert len(changes) == 2
        assert all('RealBalance' not in str(vars(row)) and 'synthetic-key' not in str(vars(row)) for row in [*rows, *changes])
    assert 'RealBalance' not in response.text


@pytest.mark.parametrize('body', [{'revision':1,'uin':'20002'}, {'revision':1,'alias':None}, {'revision':1,'is_enabled':None},
    {'revision':1,'credential_ref':None}, {'revision':True,'is_enabled':False}, {'revision':1}, {'revision':1,'alias':'  '}])
def test_maintenance_refuses_identity_rebinding_and_invalid_structured_fields(tencent_http, body):
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin':'10001','alias':'主账号','credential_ref':'finance-a'}).json()['data']
    response = client.patch('/admin/api/tencent/accounts/' + account['id'], json=body)
    assert response.status_code == 422, response.text
    assert client.get('/admin/api/tencent/accounts').json()['data'][0] == account
    assert len(calls) == 1


@pytest.mark.parametrize('gate', ['csrf', 'anonymous', 'machine', 'viewer', 'initialization'])
def test_maintenance_server_gates_reject_before_outbound(tencent_http, gate):
    from sqlalchemy import delete
    from app.persistence.models import AdminAllowlist
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin':'10001','alias':'主账号','credential_ref':'finance-a'}).json()['data']
    if gate == 'csrf': client.headers.pop('X-CSRF-Token')
    if gate in {'anonymous','machine'}: client.cookies.clear()
    if gate == 'machine': client.headers['Authorization'] = 'Bearer machine.synthetic'
    with sessions.begin() as db:
        if gate == 'viewer': db.execute(delete(AdminAllowlist))
        if gate == 'initialization': db.get(DatasetState,1).initialization_status = 'pending'
    response = client.patch('/admin/api/tencent/accounts/' + account['id'], json={'revision':1,'credential_ref':'finance-b'})
    assert response.status_code in {401,403,409}, response.text
    assert len(calls) == 1


def test_restarted_worker_keeps_old_lease_isolated_after_account_toggle(tencent_http):
    from datetime import timedelta
    from app.config import get_settings
    from app.tencent.cost_worker import TencentCostWorker
    from test_tencent_cost_mysql import enable_cost, run_job
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin':'10001','alias':'主账号','credential_ref':'finance-a'}).json()['data']
    path = '/admin/api/tencent/accounts/' + account['id']
    enable_cost(client, account)
    accepted = client.post(path + '/cost-jobs', json={'month':'2026-10','idempotency_key':'old-lease'})
    outbound = []
    worker = TencentCostWorker(sessions, app.dependency_overrides[get_settings](), lambda *args: outbound.append(args))
    claim = worker.claim()
    assert claim is not None
    assert client.patch(path, json={'revision':1,'is_enabled':False}).status_code == 200
    assert client.patch(path, json={'revision':2,'is_enabled':True}).status_code == 200
    later = worker.now() + timedelta(seconds=121)
    restarted = TencentCostWorker(sessions, app.dependency_overrides[get_settings](), lambda *args: outbound.append(args), now=lambda:later)
    assert restarted.recover() == 1
    before_late = client.get(accepted.headers['location']).json()['data']
    assert before_late['status'] == 'failed'
    assert before_late['attempts'][0]['return_state'] == 'UNKNOWN'
    assert before_late['attempts'][0]['finished_at'] is None
    assert worker.execute(claim) is None
    assert client.get(accepted.headers['location']).json()['data'] == before_late
    assert outbound == []
    assert run_job(client, sessions, account, 'new-after-restart')['status'] == 'succeeded'


def test_account_security_maintenance_is_isolated_and_cost_switch_does_not_disable_balance(tencent_http):
    from test_tencent_cost_mysql import enable_cost
    from test_tencent_balance_mysql import BALANCE
    client, sessions, calls = tencent_http
    first = client.post('/admin/api/tencent/accounts', json={'uin':'10001','alias':'账号A','credential_ref':'finance-a'}).json()['data']
    app.dependency_overrides[get_tencent_transport] = lambda: lambda *_: BALANCE.replace(b'"Uin":10001', b'"Uin":20002')
    second = client.post('/admin/api/tencent/accounts', json={'uin':'20002','alias':'账号B','credential_ref':'finance-b'}).json()['data']
    enable_cost(client, first)
    enable_cost(client, second)
    path = '/admin/api/tencent/accounts/' + first['id']
    assert client.put(path + '/cost-config', json={'revision':1,'is_enabled':False,'frequency':'manual','currency':'CNY'}).status_code == 200
    app.dependency_overrides[get_tencent_transport] = lambda: lambda *_: BALANCE
    assert client.get(path + '/balance').status_code == 200
    assert client.patch(path, json={'revision':1,'credential_ref':'finance-b','is_enabled':False}).status_code == 200
    assert client.get(path + '/balance').status_code == 409
    app.dependency_overrides[get_tencent_transport] = lambda: lambda *_: BALANCE.replace(b'"Uin":10001', b'"Uin":20002')
    assert client.get('/admin/api/tencent/accounts/' + second['id'] + '/balance').status_code == 200
    assert client.get('/admin/api/tencent/accounts/' + second['id'] + '/cost-config').json()['data']['is_enabled'] is True
    assert next(row for row in client.get('/admin/api/tencent/accounts').json()['data'] if row['id'] == second['id']) == second


def test_concurrent_rotations_publish_once_and_record_each_actual_request(tencent_http):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import select
    from app.persistence.models import TencentApiCall
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={'uin':'10001','alias':'主账号','credential_ref':'finance-a'}).json()['data']
    barrier = Barrier(2)
    def together(*_):
        barrier.wait(timeout=10)
        return b'{"Response":{"Uin":10001,"RequestId":"parallel-rotation"}}'
    app.dependency_overrides[get_tencent_transport] = lambda: together
    path = '/admin/api/tencent/accounts/' + account['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.patch(path,json={'revision':1,'credential_ref':'finance-b'}), range(2)))
    assert sorted(response.status_code for response in results) == [200,409]
    current = client.get('/admin/api/tencent/accounts').json()['data'][0]
    assert current['revision'] == 2 and current['credential_revision'] == 2
    with sessions() as db:
        facts = db.scalars(select(TencentApiCall).where(TencentApiCall.action == 'tencent.account.update')).all()
        assert len(facts) == 2
        assert {fact.outcome for fact in facts} == {'failed','succeeded'}
        assert next(fact for fact in facts if fact.outcome == 'failed').reason_code == 'TENCENT_ACCOUNT_CONFLICT'
