"""已确认 seam：管理端 HTTP → 真实 MySQL；仅 SDK 原始出站传输使用模拟。"""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text, select, inspect
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.dependencies import get_runtime
from app.main import app
from app.persistence.database import create_mysql_engine, session_factory
from app.persistence.models import AdminAllowlist, AdminSession, DatasetState, TencentAccount, TencentApiCall, TencentSyncConfig, TencentSyncJob, TencentSyncAttempt, TencentCostPeriod, TencentCostItem
from app.persistence.repositories import SqlIdentityRepository


@pytest.fixture
def tencent_http(request):
    from app.tencent.gateway import get_tencent_transport
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        if request.config.getoption('--require-mysql'):
            pytest.fail('未提供独立 MySQL 测试连接')
        pytest.skip('未提供独立 MySQL 测试连接')
    parsed = make_url(url)
    import re
    if (parsed.drivername != 'mysql+pymysql' or parsed.host not in {'127.0.0.1','localhost'}
        or parsed.port != 13306 or not re.fullmatch(r'tencent_[a-z0-9_]+_test',parsed.database or '')):
        pytest.fail('本测试仅允许已登记本机13306端口的 tencent_*_test 独立库')
    engine = create_mysql_engine(url)
    with engine.connect() as db:
        target = db.execute(text('SELECT DATABASE(),VERSION(),@@character_set_connection,@@collation_connection,@@time_zone,@@transaction_isolation')).one()
        if target[0] != parsed.database or not target[1].startswith('8.4.') or target[2:] != ('utf8mb4','utf8mb4_general_ci','+00:00','REPEATABLE-READ'):
            engine.dispose()
            pytest.fail('实际 MySQL 测试目标或连接会话不符，禁止写入')
        lease = db.execute(text('SELECT COUNT(*) FROM worker_lease WHERE owner IS NOT NULL')).scalar_one()
        active = db.execute(text("SELECT COUNT(*) FROM sync_job WHERE status IN ('validating','pending','running')")).scalar_one()
        if 'tencent_sync_job' in inspect(db).get_table_names():
            active += db.execute(text("SELECT COUNT(*) FROM tencent_sync_job WHERE status IN ('validating','pending','queued','running','retry_wait')")).scalar_one()
        if 'tencent_sync_config' in inspect(db).get_table_names():
            lease += db.execute(text('SELECT COUNT(*) FROM tencent_sync_config WHERE owner IS NOT NULL OR active_job_id IS NOT NULL')).scalar_one()
        if lease or active:
            engine.dispose()
            pytest.fail('隔离库仍有活动执行资格，禁止重置')
    sessions = session_factory(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    identities = SqlIdentityRepository(sessions, 'test-pepper')
    with sessions.begin() as db:
        db.execute(delete(TencentApiCall))
        for model in (TencentCostItem,TencentCostPeriod,TencentSyncAttempt,TencentSyncJob,TencentSyncConfig):
            db.execute(delete(model))
        db.execute(delete(TencentAccount))
        db.execute(delete(AdminSession))
        db.execute(delete(AdminAllowlist))
        db.add(AdminAllowlist(open_id='tencent-admin', created_at=now))
        state = db.get(DatasetState, 1)
        state.initialization_status = 'complete'
        state.dataset_epoch = 'tencent-account-test'
    issued = identities.create_session('tencent-admin', 'test-csrf', now + timedelta(hours=1), now)
    settings = Settings(session_secret='test-pepper', tencent_credentials='{"finance-a":{"label":"生产只读账号 A","secret_id":"synthetic-id","secret_key":"synthetic-key"},"finance-b":{"label":"生产只读账号 B","secret_id":"synthetic-id-b","secret_key":"synthetic-key-b"}}')
    calls = []
    def transport(credential, action, params):
        calls.append((action, params))
        return b'{"Response":{"Uin":10001,"RequestId":"synthetic-request","RealBalance":12345.6789}}'
    app.dependency_overrides[get_runtime] = lambda: SimpleNamespace(sessions=sessions, identities=identities)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_tencent_transport] = lambda: transport
    client = TestClient(app)
    client.cookies.set('org_session', issued.token)
    client.headers['X-CSRF-Token'] = 'test-csrf'
    try:
        yield client, sessions, calls
    finally:
        app.dependency_overrides.clear()
        with sessions.begin() as db:
            db.execute(delete(TencentApiCall))
            # Tests must join all cloud execution before fixture teardown.
            if db.scalar(select(TencentSyncConfig.id).where((TencentSyncConfig.owner.is_not(None) | TencentSyncConfig.active_job_id.is_not(None))).limit(1)) is not None:
                pytest.fail('云worker仍持有执行资格，禁止清理')
            for model in (TencentCostItem,TencentCostPeriod,TencentSyncAttempt,TencentSyncJob,TencentSyncConfig):
                db.execute(delete(model))
            db.execute(delete(TencentAccount))
            db.execute(delete(AdminSession).where(AdminSession.open_id=='tencent-admin'))
            db.execute(delete(AdminAllowlist).where(AdminAllowlist.open_id=='tencent-admin'))
        engine.dispose()


def test_admin_registers_verified_account_and_can_read_it_without_secrets(tencent_http):
    client, sessions, calls = tencent_http
    response = client.post('/admin/api/tencent/accounts', json={'uin':'10001','alias':'主账号','credential_ref':'finance-a'})
    assert response.status_code == 201, response.text
    account = response.json()['data']
    assert account['uin'] == '10001'
    assert account['alias'] == '主账号'
    assert account['verification_status'] == 'verified'
    assert account['is_enabled'] is True
    assert client.get('/admin/api/tencent/accounts').json()['data'] == [account]
    assert calls == [('DescribeAccountBalance', {})]
    assert 'synthetic-key' not in response.text
    assert 'RealBalance' not in response.text
    assert response.headers['cache-control'] == 'no-store'

@pytest.mark.parametrize('path,method', [('/admin/api/tencent/accounts','get'),('/admin/api/tencent/credential-options','get'),('/admin/api/tencent/accounts','post'),('/admin/api/tencent/accounts/validate','post')])
def test_other_identities_and_csrf_cannot_bypass_server_gate(tencent_http, path, method):
    client, sessions, calls = tencent_http
    kwargs = {'json':{'uin':'10001','alias':'主账号','credential_ref':'finance-a'}} if method == 'post' else {}
    client.cookies.clear()
    client.headers['Authorization'] = 'Bearer machine.synthetic'
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401
    assert calls == []
    with sessions() as db:
        rows = db.query(TencentApiCall).filter_by(direction='inbound').all()
        assert len(rows) == 1
        assert rows[0].status_code == 401
        assert rows[0].actor_id is None


def test_registration_rejects_csrf_and_uninitialized_state_without_outbound_call(tencent_http):
    client, sessions, calls = tencent_http
    body = {'uin':'10001','alias':'主账号','credential_ref':'finance-a'}
    client.headers.pop('X-CSRF-Token')
    assert client.post('/admin/api/tencent/accounts',json=body).json()['error']['code'] == 'CSRF_REQUIRED'
    client.headers['X-CSRF-Token'] = 'test-csrf'
    with sessions.begin() as db:
        db.get(DatasetState,1).initialization_status = 'pending'
    response = client.post('/admin/api/tencent/accounts',json=body)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'INITIALIZATION_INCOMPLETE'
    assert calls == []


def test_mismatched_uin_and_uncontrolled_reference_never_register(tencent_http):
    client, sessions, calls = tencent_http
    mismatch = client.post('/admin/api/tencent/accounts',json={'uin':'20002','alias':'错误账号','credential_ref':'finance-a'})
    assert mismatch.status_code == 422
    assert mismatch.json()['error']['code'] == 'TENCENT_ACCOUNT_MISMATCH'
    invalid = client.post('/admin/api/tencent/accounts',json={'uin':'10001','alias':'错误引用','credential_ref':'unregistered-ref'})
    assert invalid.status_code == 422
    assert invalid.json()['error']['code'] == 'TENCENT_CREDENTIAL_REF_INVALID'
    assert client.get('/admin/api/tencent/accounts').json()['data'] == []
    assert len(calls) == 1


def test_repeated_account_is_rejected_without_revalidating_and_identity_cannot_be_rebound(tencent_http):
    client, sessions, calls = tencent_http
    body = {'uin':'10001','alias':'主账号','credential_ref':'finance-a'}
    first = client.post('/admin/api/tencent/accounts',json=body)
    assert first.status_code == 201
    assert client.post('/admin/api/tencent/accounts',json={**body,'credential_ref':'finance-b'}).status_code == 409
    assert client.patch('/admin/api/tencent/accounts/'+first.json()['data']['id'],json={'uin':'20002'}).status_code == 422
    assert len(calls) == 1
    assert len(client.get('/admin/api/tencent/accounts').json()['data']) == 1


def test_validation_does_not_create_account_or_balance_history_and_audits_each_actual_call(tencent_http):
    client, sessions, calls = tencent_http
    response = client.post('/admin/api/tencent/accounts/validate',json={'uin':'10001','credential_ref':'finance-a'})
    assert response.status_code == 200
    assert client.get('/admin/api/tencent/accounts').json()['data'] == []
    with sessions() as db:
        rows = db.query(TencentApiCall).all()
        assert len([row for row in rows if row.direction == 'inbound']) == 2
        assert len([row for row in rows if row.direction == 'outbound']) == 1
        assert {row.action for row in rows} == {'tencent.account.validate','tencent.account.read','DescribeAccountBalance'}
        assert all(row.finished_at is not None for row in rows)
        assert all('RealBalance' not in str(vars(row)) and 'synthetic-key' not in str(vars(row)) for row in rows)
        assert next(row for row in rows if row.direction=='outbound').request_id == response.headers['x-request-id']


def test_epoch_change_during_verification_prevents_registration(tencent_http):
    from app.tencent.gateway import get_tencent_transport
    client, sessions, calls = tencent_http
    def changed(credential, action, params):
        with sessions.begin() as db:
            db.get(DatasetState,1).dataset_epoch = 'next-epoch'
        return b'{"Response":{"Uin":10001,"RequestId":"synthetic-request"}}'
    app.dependency_overrides[get_tencent_transport] = lambda: changed
    response = client.post('/admin/api/tencent/accounts',json={'uin':'10001','alias':'主账号','credential_ref':'finance-a'})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'DATASET_CHANGED'
    assert client.get('/admin/api/tencent/accounts').json()['data'] == []


def test_non_admin_session_is_rejected_and_reference_options_only_expose_labels(tencent_http):
    client, sessions, calls = tencent_http
    response = client.get('/admin/api/tencent/credential-options')
    assert response.json()['data'] == [{'value':'finance-a','label':'生产只读账号 A'},{'value':'finance-b','label':'生产只读账号 B'}]
    with sessions.begin() as db:
        db.execute(delete(AdminAllowlist))
    assert client.get('/admin/api/tencent/accounts').status_code == 401
    assert calls == []


def test_admin_revoked_while_external_verification_is_in_flight_cannot_register(tencent_http):
    from app.tencent.gateway import get_tencent_transport
    client, sessions, calls = tencent_http
    def revoked(credential, action, params):
        with sessions.begin() as db:
            db.execute(delete(AdminAllowlist))
        return b'{"Response":{"Uin":10001,"RequestId":"synthetic-request"}}'
    app.dependency_overrides[get_tencent_transport] = lambda: revoked
    response = client.post('/admin/api/tencent/accounts',json={'uin':'10001','alias':'主账号','credential_ref':'finance-a'})
    assert response.status_code == 401
    with sessions() as db:
        assert db.query(TencentAccount).count() == 0


def test_official_sdk_raw_http_boundary_registers_without_generated_float_conversion(tencent_http, monkeypatch):
    import requests
    from app.tencent.gateway import get_tencent_transport
    client, sessions, calls = tencent_http
    sent = []
    def http_send(self, **kwargs):
        sent.append(kwargs.get('headers',{}).get('X-TC-Action'))
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"Response":{"Uin":10001,"RequestId":"sdk-raw-request","RealBalance":9007199254740991.12345678}}'
        return response
    monkeypatch.setattr(requests.Session, 'request', http_send)
    del app.dependency_overrides[get_tencent_transport]
    response = client.post('/admin/api/tencent/accounts',json={'uin':'10001','alias':'主账号','credential_ref':'finance-a'})
    assert response.status_code == 201, response.text
    assert sent == ['DescribeAccountBalance']

def test_concurrent_registration_keeps_one_account_and_each_request_is_audited(tencent_http):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.tencent.gateway import get_tencent_transport
    client, sessions, calls = tencent_http
    barrier = Barrier(2)
    def concurrent(credential, action, params):
        barrier.wait(timeout=5)
        return b'{"Response":{"Uin":10001,"RequestId":"concurrent-request"}}'
    app.dependency_overrides[get_tencent_transport] = lambda: concurrent
    body = {'uin':'10001','alias':'主账号','credential_ref':'finance-a'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post('/admin/api/tencent/accounts',json=body).status_code, range(2)))
    assert sorted(results) == [201,409]
    assert len(client.get('/admin/api/tencent/accounts').json()['data']) == 1
    with sessions() as db:
        assert db.query(TencentApiCall).filter_by(direction='inbound',method='POST').count() == 2


def test_audit_finalization_failure_does_not_rewrite_a_delivered_success(tencent_http):
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session
    client, sessions, calls = tencent_http
    def fail_completion(db, context, instances):
        if any(isinstance(row,TencentApiCall) and row.direction=='inbound' and row.outcome=='succeeded' for row in db.dirty):
            raise SQLAlchemyError('synthetic audit storage interruption')
    event.listen(Session,'before_flush',fail_completion)
    try:
        response = client.get('/admin/api/tencent/accounts')
    finally:
        event.remove(Session,'before_flush',fail_completion)
    assert response.status_code == 200
    with sessions() as db:
        row = db.query(TencentApiCall).filter_by(direction='inbound').one()
        assert row.status_code == 200
        assert row.outcome == 'unknown'
        assert row.finished_at is None


def test_actual_mysql_new_tables_preserve_character_sets_comments_and_immutable_uin_key(tencent_http):
    from sqlalchemy import text
    client, sessions, calls = tencent_http
    with sessions() as db:
        session = db.execute(text('SELECT VERSION(), @@character_set_connection, @@collation_connection, @@time_zone')).one()
        assert session[0].startswith('8.4.')
        assert session[1:] == ('utf8mb4','utf8mb4_general_ci','+00:00')
        columns = db.execute(text("SELECT TABLE_NAME,COLUMN_NAME,COLUMN_COMMENT,COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('tencent_account','tencent_api_call')")).all()
        assert columns and all(row.COLUMN_COMMENT.strip() for row in columns)
        assert next(row for row in columns if row.TABLE_NAME=='tencent_account' and row.COLUMN_NAME=='uin').COLLATION_NAME == 'utf8mb4_bin'
        tables = db.execute(text("SELECT ENGINE,TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('tencent_account','tencent_api_call')")).all()
        assert len(tables)==2 and all(tuple(row)==('InnoDB','utf8mb4_general_ci') for row in tables)
