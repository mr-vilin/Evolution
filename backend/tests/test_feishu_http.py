import hashlib
import hmac
from http.cookies import SimpleCookie
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings, Settings
from app.dependencies import get_admin_identity, get_runtime
from app.feishu.client import FeishuClient
from app.persistence.repositories import SqlIdentityRepository


def test_admin_session_cookie_lifecycle(sqlite_sessions, monkeypatch):
    settings = Settings(
        session_secret='s' * 32,
        feishu_app_id='app',
        feishu_app_secret='test-secret',
        feishu_tenant_key='tenant',
        feishu_redirect_uri='https://test.invalid/admin/auth/callback',
        initial_admin_open_ids='ou',
    )
    identities = SqlIdentityRepository(sqlite_sessions, settings.session_secret.get_secret_value())
    runtime = SimpleNamespace(sessions=sqlite_sessions, identities=identities)
    monkeypatch.setitem(app.dependency_overrides, get_settings, lambda: settings)
    monkeypatch.setitem(app.dependency_overrides, get_runtime, lambda: runtime)
    monkeypatch.setattr(
        FeishuClient, 'login',
        lambda self, code: {'open_id': 'ou', 'user_id': 'user', 'tenant_key': 'tenant'},
    )

    with TestClient(app, base_url='https://test.invalid', follow_redirects=False) as client:
        login = client.get('/admin/auth/login')
        assert login.status_code == 302
        state = parse_qs(urlsplit(login.headers['location']).query)['state'][0]
        assert client.cookies.get('oauth_state') == state
        callback = client.get('/admin/auth/callback', params={'code': 'test-code', 'state': state})
        assert callback.status_code == 302
        cookies = SimpleCookie()
        for header in callback.headers.get_list('set-cookie'):
            cookies.load(header)
        assert set(cookies) == {'session', 'csrf', 'oauth_state'}
        cookie = cookies['session']
        assert cookie['path'] == '/'
        assert cookie['max-age'] == '43200'
        assert cookie['secure'] and cookie['httponly'] and cookie['samesite'] == 'lax'
        assert cookies['csrf']['path'] == '/admin/auth'
        assert cookies['csrf']['samesite'] == 'strict'
        assert cookies['csrf']['secure'] and cookies['csrf']['httponly']
        assert cookies['oauth_state']['path'] == '/admin/auth'
        assert cookies['oauth_state']['max-age'] == '0'
        assert 'oauth_state' not in client.cookies

        session = client.get('/admin/auth/session')
        assert session.status_code == 200
        assert client.get('/admin/api/system/version').status_code == 200
        assert client.post('/admin/auth/logout').status_code == 403
        csrf = session.json()['data']['csrf_token']
        logout = client.post('/admin/auth/logout', headers={'X-CSRF-Token': csrf})
        assert logout.status_code == 200
        deleted = SimpleCookie()
        for header in logout.headers.get_list('set-cookie'):
            deleted.load(header)
        assert deleted['session']['path'] == '/'
        assert deleted['csrf']['path'] == deleted['oauth_state']['path'] == '/admin/auth'
        assert {name: deleted[name]['max-age'] for name in deleted} == {
            'session': '0', 'csrf': '0', 'oauth_state': '0',
        }
        assert not client.cookies
        client.cookies.set('session', cookie.value)
        assert client.get('/admin/api/system/version').status_code == 401


def test_session_bootstrap_requires_matching_cookie_and_does_not_put_csrf_in_url(sqlite_sessions):
    secret='s'*32
    app.dependency_overrides[get_settings]=lambda: Settings(session_secret=secret)
    app.dependency_overrides[get_admin_identity]=lambda: SimpleNamespace(open_id='ou',csrf_hash=hmac.new(secret.encode(),b'csrf',hashlib.sha256).hexdigest())
    app.dependency_overrides[get_runtime]=lambda: SimpleNamespace(sessions=sqlite_sessions)
    try:
        client=TestClient(app)
        assert client.get('/admin/auth/session').status_code == 403
        client.cookies.set('csrf','csrf')
        response=client.get('/admin/auth/session')
        assert response.json() == {'data':{'open_id':'ou','csrf_token':'csrf','initialization_complete':True},'meta':{}}
        assert response.headers['cache-control'] == 'no-store'
    finally: app.dependency_overrides.clear()


def test_schedule_routes_and_login_unconfigured_are_safe():
    client=TestClient(app)
    assert client.get('/admin/auth/login').status_code == 503
    assert client.get('/admin/api/settings/reconcile-schedule').status_code == 401
    assert client.put('/admin/api/settings/reconcile-schedule',json={}).status_code == 401


def test_connection_unknown_is_degraded_and_secret_is_never_echoed():
    from app.feishu.health import connection_summary
    settings=Settings(feishu_app_id='cli_sensitive',feishu_app_secret='NEVER-ECHO',feishu_tenant_key='tenant_sensitive')
    result=connection_summary(settings,None)
    assert result['status']=='degraded'
    assert 'NEVER-ECHO' not in str(result)
    assert result['app_id_masked'] != 'cli_sensitive'
