"""实时余额的已确认 seam：HTTP → 隔离 MySQL，只模拟腾讯云原始出站。"""
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.tencent.gateway import get_tencent_transport
from app.persistence.models import TencentApiCall
from test_tencent_accounts_mysql import tencent_http

BALANCE = b'{"Response":{"Uin":10001,"RequestId":"balance-query","RealBalance":9007199254740991.12345678,"CashAccountBalance":12000.50,"IncomeIntoAccountBalance":100,"PresentAccountBalance":25,"FreezeAmount":5,"OweAmount":0,"CreditAmount":20000,"CreditBalance":32000.5,"RealCreditBalance":31995.5}}'


def register(client):
    result = client.post('/admin/api/tencent/accounts', json={'uin':'10001','alias':'主账号','credential_ref':'finance-a'})
    assert result.status_code == 201, result.text
    return result.json()['data']['id']


def test_registered_account_can_query_live_balance_without_cost_configuration(tencent_http):
    client, sessions, calls = tencent_http
    account_id = register(client)
    app.dependency_overrides[get_tencent_transport] = lambda: lambda credential, action, params: BALANCE
    before = datetime.now(timezone.utc)
    result = client.get(f'/admin/api/tencent/accounts/{account_id}/balance')
    assert result.status_code == 200, result.text
    data = result.json()['data']
    assert data['account_id'] == account_id
    assert data['uin'] == '10001'
    assert data['currency'] == 'CNY'
    assert data['unit'] == 'yuan'
    assert data['amounts']['real_balance'] == '90071992547409.9112345678'
    assert data['amounts']['cash_account_balance'] == '120.005'
    assert data['amounts']['income_into_account_balance'] == '1.00'
    assert data['amounts']['present_account_balance'] == '0.25'
    assert data['amounts']['freeze_amount'] == '0.05'
    assert data['amounts']['owe_amount'] == '0.00'
    assert data['amounts']['credit_amount'] == '200.00'
    assert data['amounts']['credit_balance'] == '320.005'
    assert data['amounts']['real_credit_balance'] == '319.955'
    queried = datetime.fromisoformat(data['queried_at'].replace('Z','+00:00'))
    assert before <= queried <= datetime.now(timezone.utc)
    assert result.headers['cache-control'] == 'no-store'
    assert 'RealBalance' not in result.text
    with sessions() as db:
        facts = db.scalars(select(TencentApiCall).where(TencentApiCall.request_id == result.headers['x-request-id'])).all()
        assert len(facts) == 2
        assert {row.action for row in facts} == {'tencent.balance.query','DescribeAccountBalance'}
        assert all('9007199254740991' not in str(vars(row)) for row in facts)


def test_concurrent_balance_query_is_rejected_without_second_outbound(tencent_http):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    client, sessions, calls = tencent_http
    account_id = register(client)
    entered, release = Event(), Event()
    outbound = []
    def blocked(credential, action, params):
        outbound.append(action)
        entered.set()
        assert release.wait(timeout=5)
        return BALANCE
    app.dependency_overrides[get_tencent_transport] = lambda: blocked
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.get, f'/admin/api/tencent/accounts/{account_id}/balance')
        assert entered.wait(timeout=5)
        try:
            second = client.get(f'/admin/api/tencent/accounts/{account_id}/balance')
            assert second.status_code == 429, second.text
            assert second.json()['error']['code'] == 'TENCENT_BALANCE_BUSY'
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
    assert outbound == ['DescribeAccountBalance']


import json
import pytest
from sqlalchemy import delete
from app.persistence.models import DatasetState, TencentAccount, AdminAllowlist


@pytest.mark.parametrize('raw,expected', [(b'-123.456', '-1.23456'), (b'0', '0.00'), (b'-0.000', '0.00')])
def test_balance_preserves_negative_and_zero_exact_amounts(tencent_http, raw, expected):
    client, sessions, calls = tencent_http
    account_id = register(client)
    response = BALANCE.replace(b'9007199254740991.12345678', raw)
    app.dependency_overrides[get_tencent_transport] = lambda: lambda *_: response
    result = client.get(f'/admin/api/tencent/accounts/{account_id}/balance')
    assert result.status_code == 200
    assert result.json()['data']['amounts']['real_balance'] == expected


@pytest.mark.parametrize('raw', [b'null', b'false', b'"12000"', b'NaN', b'1e1000'])
def test_unverifiable_amount_never_becomes_zero_or_a_successful_balance(tencent_http, raw):
    client, sessions, calls = tencent_http
    account_id = register(client)
    app.dependency_overrides[get_tencent_transport] = lambda: lambda *_: BALANCE.replace(b'9007199254740991.12345678', raw)
    result = client.get(f'/admin/api/tencent/accounts/{account_id}/balance')
    assert result.status_code == 502
    assert result.json()['error']['code'] == 'TENCENT_UPSTREAM_INVALID'
    assert 'amounts' not in result.text


@pytest.mark.parametrize('change,code,status', [('epoch','DATASET_CHANGED',409), ('disabled','TENCENT_ACCOUNT_UNAVAILABLE',409),
    ('revision','TENCENT_CREDENTIAL_CHANGED',409), ('admin','ADMIN_SESSION_REQUIRED',401), ('initialization','INITIALIZATION_INCOMPLETE',409)])
def test_inflight_financial_result_is_discarded_when_eligibility_changes(tencent_http, change, code, status):
    client, sessions, calls = tencent_http
    account_id = register(client)
    def changed(*_):
        with sessions.begin() as db:
            if change == 'epoch': db.get(DatasetState,1).dataset_epoch = 'replaced'
            if change == 'initialization': db.get(DatasetState,1).initialization_status = 'pending'
            if change == 'disabled': db.get(TencentAccount,int(account_id)).is_enabled = False
            if change == 'revision': db.get(TencentAccount,int(account_id)).credential_revision += 1
            if change == 'admin': db.execute(delete(AdminAllowlist))
        return BALANCE
    app.dependency_overrides[get_tencent_transport] = lambda: changed
    result = client.get(f'/admin/api/tencent/accounts/{account_id}/balance')
    assert result.status_code == status, result.text
    assert result.json()['error']['code'] == code
    assert 'amounts' not in result.text
    assert result.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('failure,code,status', [('mismatch','TENCENT_ACCOUNT_MISMATCH',422),('timeout','TENCENT_TIMEOUT',504),
    ('permission','TENCENT_PERMISSION_DENIED',502),('json','TENCENT_UPSTREAM_INVALID',502)])
def test_balance_upstream_failures_are_explicit_and_never_return_old_values(tencent_http, failure, code, status):
    client, sessions, calls = tencent_http
    account_id = register(client)
    def failed(*_):
        if failure == 'timeout': raise TimeoutError('synthetic-key must not leak')
        if failure == 'permission': return b'{"Response":{"Error":{"Code":"UnauthorizedOperation","Message":"synthetic-key must not leak"},"RequestId":"denied"}}'
        if failure == 'json': return b'not json synthetic-key'
        return BALANCE.replace(b'"Uin":10001',b'"Uin":20002')
    app.dependency_overrides[get_tencent_transport] = lambda: failed
    result = client.get(f'/admin/api/tencent/accounts/{account_id}/balance')
    assert result.status_code == status
    assert result.json()['error']['code'] == code
    assert 'synthetic-key' not in result.text and 'amounts' not in result.text


@pytest.mark.parametrize('gate', ['anonymous','machine','viewer','uninitialized','disabled'])
def test_balance_server_gates_refuse_before_outbound(tencent_http, gate):
    client, sessions, calls = tencent_http
    account_id = register(client)
    if gate in {'anonymous','machine'}: client.cookies.clear()
    if gate == 'machine': client.headers['Authorization'] = 'Bearer machine.synthetic'
    with sessions.begin() as db:
        if gate == 'viewer': db.execute(delete(AdminAllowlist))
        if gate == 'uninitialized': db.get(DatasetState,1).initialization_status = 'pending'
        if gate == 'disabled': db.get(TencentAccount,int(account_id)).is_enabled = False
    result = client.get(f'/admin/api/tencent/accounts/{account_id}/balance')
    assert result.status_code in {401,409}
    assert len(calls) == 1
    with sessions() as db:
        row = db.get(TencentApiCall,result.headers['x-request-id'])
        assert row.action == 'tencent.balance.query'
        assert row.outcome == 'failed'


def test_balance_rate_limit_counts_actual_recent_calls_without_financial_persistence(tencent_http):
    from datetime import timedelta
    from sqlalchemy import text
    import uuid
    client, sessions, calls = tencent_http
    account_id = register(client)
    with sessions.begin() as db:
        for index in range(5):
            db.add(TencentApiCall(id=str(uuid.uuid4()),request_id='seed-rate-'+str(index),direction='outbound',action='DescribeAccountBalance',
                method='POST',route='DescribeAccountBalance',outcome='succeeded',target_id='10001',started_at=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(seconds=60)))
    result = client.get(f'/admin/api/tencent/accounts/{account_id}/balance')
    assert result.status_code == 429
    assert result.json()['error']['code'] == 'TENCENT_BALANCE_RATE_LIMITED'
    assert len(calls) == 1


def test_successful_live_query_changes_only_request_audit_rows(tencent_http):
    from sqlalchemy import inspect, text
    client, sessions, calls = tencent_http
    account_id = register(client)
    def snapshot():
        with sessions() as db:
            return {table:db.execute(text('SELECT COUNT(*) FROM `'+table+'`')).scalar_one()
                for table in inspect(db.get_bind()).get_table_names() if table!='tencent_api_call'}
    before = snapshot()
    app.dependency_overrides[get_tencent_transport] = lambda: lambda *_: BALANCE
    result = client.get(f'/admin/api/tencent/accounts/{account_id}/balance')
    assert result.status_code == 200
    assert snapshot() == before


def test_actual_mysql_balance_rate_limit_has_matching_range_index(tencent_http):
    from sqlalchemy import inspect
    from app.persistence.models import TencentApiCall
    client, sessions, calls = tencent_http
    with sessions() as db:
        actual = {item['name']:item['column_names'] for item in inspect(db.get_bind()).get_indexes('tencent_api_call')}
    expected = ['direction','action','target_id','started_at']
    assert actual.get('ix_tencent_api_call_rate_window') == expected
    declared = next(index for index in TencentApiCall.__table__.indexes if index.name=='ix_tencent_api_call_rate_window')
    assert [column.name for column in declared.columns] == expected
