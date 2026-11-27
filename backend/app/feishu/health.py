import json
from datetime import datetime, timezone, timedelta
from app.persistence.models import SystemSetting


def connection_summary(settings, observation):
    configured = bool(settings.feishu_app_id and settings.feishu_app_secret and settings.feishu_tenant_key)
    status = 'degraded' if configured else 'unconfigured'
    checked_at = observation.get('checked_at') if observation else None
    if configured and observation and observation.get('status') == 'connected' and checked_at:
        checked = datetime.fromisoformat(checked_at)
        if datetime.now(timezone.utc) - checked < timedelta(seconds=90): status = 'connected'
    def mask(value): return ('***'+value[-4:]) if value else None
    return {'status': status, 'checked_at': checked_at, 'app_id_masked': mask(settings.feishu_app_id), 'tenant_key_masked': mask(settings.feishu_tenant_key), 'scopes': [s.strip() for s in settings.feishu_scopes.split(',') if s.strip()]}


def observe(sessions, status):
    with sessions.begin() as db:
        db.merge(SystemSetting(setting_key='feishu_connection_observation', value=json.dumps({'status':status,'checked_at':datetime.now(timezone.utc).isoformat()})))


EVENT_MONITOR_STARTED = 'feishu_event_monitor_started'
EVENT_MONITOR_CONFIG = 'feishu_event_monitor_config'
DEFAULT_EVENT_MONITOR = {'normal_minutes': 60, 'disconnect_minutes': 180}


def start_event_monitor(sessions):
    from sqlalchemy import select
    with sessions.begin() as db:
        db.scalar(select(SystemSetting).where(SystemSetting.setting_key == 'task_queue_lock').with_for_update())
        if db.get(SystemSetting, EVENT_MONITOR_STARTED) is None:
            db.add(SystemSetting(setting_key=EVENT_MONITOR_STARTED, value=datetime.now(timezone.utc).isoformat()))


def event_monitor_config(db):
    row = db.get(SystemSetting, EVENT_MONITOR_CONFIG)
    return json.loads(row.value) if row else dict(DEFAULT_EVENT_MONITOR)


def save_event_monitor_config(sessions, value, actor):
    from sqlalchemy import select
    from app.persistence.models import ChangeLog
    now = datetime.now(timezone.utc)
    with sessions.begin() as db:
        db.scalar(select(SystemSetting).where(SystemSetting.setting_key == 'task_queue_lock').with_for_update())
        before = event_monitor_config(db)
        db.merge(SystemSetting(setting_key=EVENT_MONITOR_CONFIG, value=json.dumps(value)))
        db.add(ChangeLog(object_type='settings', object_id=EVENT_MONITOR_CONFIG, source='admin', actor=actor,
                         before_data=before, after_data=value, committed_at=now.replace(tzinfo=None)))
    return value


def event_connection_summary(settings, db, now=None):
    from sqlalchemy import select, func
    from app.persistence.models import EventInbox
    config = event_monitor_config(db)
    result = connection_summary(settings, None)
    now = now or datetime.now(timezone.utc)
    last = db.scalar(select(func.max(EventInbox.received_at)).where(EventInbox.object_id.is_not(None)))
    stored = db.get(SystemSetting, 'feishu_last_event_received_at')
    started = db.get(SystemSetting, EVENT_MONITOR_STARTED)
    last = last.replace(tzinfo=timezone.utc) if last else None
    if stored:
        last = max(filter(None, (last, datetime.fromisoformat(stored.value))))
    baseline = last or (datetime.fromisoformat(started.value) if started else None)
    minutes = max(0, (now - baseline).total_seconds() / 60) if baseline else None
    if result['status'] != 'unconfigured':
        if last is not None and minutes <= config['normal_minutes']:
            result['status'] = 'normal'
        elif minutes is not None and minutes > config['disconnect_minutes']:
            result['status'] = 'disconnected'
        else:
            result['status'] = 'warning'
    result.update(checked_at=last.isoformat() if last else None,
                  last_event_received_at=last.isoformat() if last else None,
                  monitoring_started_at=started.value if started else None,
                  elapsed_minutes=int(minutes) if minutes is not None else None, **config)
    return result
