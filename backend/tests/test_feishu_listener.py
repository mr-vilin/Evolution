from test_sync_persistence import sessions
from app.config import Settings
from app.persistence.models import SyncJob, SystemSetting, EventInbox
from sqlalchemy import select
import pytest


def test_listener_startup_and_reconnected_enqueue_one_reconcile_without_claiming_connected(sessions):
    from app.feishu.listener import Listener
    listener=Listener(sessions,Settings(feishu_app_id='a',feishu_app_secret='s',feishu_tenant_key='t',
                                       feishu_reconcile_on_startup=True,feishu_reconcile_on_reconnect=True))
    listener.starting()
    listener.starting()
    with sessions() as db:
        assert len(list(db.scalars(select(SyncJob)))) == 1
        assert 'degraded' in db.get(SystemSetting,'feishu_connection_observation').value
    listener.reconnected()
    with sessions() as db: assert len(list(db.scalars(select(SyncJob)))) == 1


def test_listener_callback_only_inboxes_and_never_swallows_persistence_failure(sessions):
    from app.feishu.listener import Listener
    listener=Listener(sessions,Settings(feishu_app_id='a',feishu_app_secret='s',feishu_tenant_key='t'))
    payload={'header':{'event_id':'e','event_type':'contact.user.created_v3','app_id':'a','tenant_key':'t'},'event':{'object':{'user_id':'u'}}}
    listener.receive(payload)
    listener.receive(payload)
    with sessions() as db: assert db.get(EventInbox,'e').status == 'queued'


def test_listener_remains_available_before_initialization_and_resumes_reconcile(sessions):
    from app.feishu.listener import Listener
    from app.persistence.models import DatasetState
    with sessions.begin() as db:
        db.get(DatasetState, 1).initialization_status = 'pending'
    listener = Listener(sessions, Settings(feishu_app_id='a', feishu_app_secret='s', feishu_tenant_key='t',
                                           feishu_reconcile_on_startup=True, feishu_reconcile_on_reconnect=True))
    listener.starting()
    listener.reconnected()
    listener.receive({'header': {'event_id': 'before-init', 'event_type': 'contact.scope.updated_v3',
                                 'app_id': 'a', 'tenant_key': 't'}, 'event': {}})
    with sessions() as db:
        assert list(db.scalars(select(SyncJob))) == []
        assert db.get(EventInbox, 'before-init').status == 'queued'
        assert db.get(SystemSetting, 'coverage_invalidated').value == 'true'
        assert 'connected' in db.get(SystemSetting, 'feishu_connection_observation').value
    with sessions.begin() as db:
        db.get(DatasetState, 1).initialization_status = 'complete'
    listener.reconnected()
    with sessions() as db:
        assert len(list(db.scalars(select(SyncJob)))) == 1


def test_listener_does_not_hide_unexpected_reconcile_failures(sessions, monkeypatch):
    from app.feishu.listener import Listener, SqlSyncJobRepository
    def fail(*args, **kwargs):
        raise RuntimeError('DATABASE_SCHEMA_INCOMPLETE')
    monkeypatch.setattr(SqlSyncJobRepository, 'submit', fail)
    listener = Listener(sessions, Settings(feishu_reconcile_on_startup=True))
    with pytest.raises(RuntimeError, match='DATABASE_SCHEMA_INCOMPLETE'):
        listener.starting()


@pytest.mark.parametrize('startup,reconnect', [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize('method,reason,health', [
    ('starting', 'listener:startup', 'degraded'),
    ('reconnected', 'listener:reconnected', 'connected'),
])
def test_listener_reconcile_switches_are_independent(sessions, startup, reconnect, method, reason, health):
    from app.feishu.listener import Listener
    listener = Listener(sessions, Settings(feishu_reconcile_on_startup=startup,
                                           feishu_reconcile_on_reconnect=reconnect))
    getattr(listener, method)()
    with sessions() as db:
        jobs = list(db.scalars(select(SyncJob)))
        enabled = startup if method == 'starting' else reconnect
        assert len(jobs) == int(enabled)
        if enabled:
            assert jobs[0].type == 'reconcile'
            assert jobs[0].requested_by == reason
        assert health in db.get(SystemSetting, 'feishu_connection_observation').value


def test_listener_defaults_skip_reconcile_but_continue_receiving_events(sessions, monkeypatch):
    from app.feishu.listener import Listener
    monkeypatch.delenv('ORG_FEISHU_RECONCILE_ON_STARTUP', raising=False)
    monkeypatch.delenv('ORG_FEISHU_RECONCILE_ON_RECONNECT', raising=False)
    settings = Settings(feishu_app_id='a', feishu_tenant_key='t')
    assert settings.feishu_reconcile_on_startup is False
    assert settings.feishu_reconcile_on_reconnect is False
    listener = Listener(sessions, settings)
    listener.starting()
    listener.reconnecting()
    listener.reconnected()
    listener.receive({'header': {'event_id': 'switches-off', 'event_type': 'contact.user.created_v3',
                                 'app_id': 'a', 'tenant_key': 't'},
                      'event': {'object': {'user_id': 'u'}}})
    with sessions() as db:
        assert list(db.scalars(select(SyncJob))) == []
        assert db.get(EventInbox, 'switches-off').status == 'queued'
        assert 'connected' in db.get(SystemSetting, 'feishu_connection_observation').value


@pytest.mark.parametrize('startup,reconnect', [('true', 'false'), ('false', 'true')])
def test_listener_reconcile_switches_load_from_environment(monkeypatch, startup, reconnect):
    monkeypatch.setenv('ORG_FEISHU_RECONCILE_ON_STARTUP', startup)
    monkeypatch.setenv('ORG_FEISHU_RECONCILE_ON_RECONNECT', reconnect)
    settings = Settings()
    assert settings.feishu_reconcile_on_startup is (startup == 'true')
    assert settings.feishu_reconcile_on_reconnect is (reconnect == 'true')
