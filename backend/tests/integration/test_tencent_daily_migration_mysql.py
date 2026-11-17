"""T07 独立 MySQL：扩展旧月期间身份，保留原值并拒绝丢失日证据的降级。"""
from pathlib import Path
from datetime import datetime
from alembic import command
from alembic.config import Config
from sqlalchemy import text
import pytest
from app.main import app
from app.config import get_settings
from test_tencent_accounts_mysql import tencent_http
from test_tencent_cost_mysql import cost_http
from test_tencent_monthly_mysql import monthly
from test_tencent_daily_mysql import daily_transport


def test_daily_migration_preserves_month_and_refuses_daily_data_loss(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    from app.persistence.schema_check import check_schema
    client,sessions,account=cost_http
    now=datetime(2026,11,3,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    accepted=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'legacy'})
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    assert worker.run_once()
    before=client.get(base+'/cost-periods/2026-10').json()['data']
    config=Config(str(Path(__file__).parents[2]/'alembic.ini'))
    # 公共夹具已检查13306/专库/实际8.4会话、owner即使过期、active_job_id及running静默。
    command.downgrade(config,'0018_tencent_monthly')
    command.upgrade(config,'head')
    assert client.get(base+'/cost-periods/2026-10').json()['data']==before
    assert not check_schema(sessions.kw['bind'])['errors']
    with sessions() as db:
        row=db.execute(text("SELECT granularity,period_key FROM tencent_cost_period")).one()
        assert row==('month','2026-10')
        columns=db.execute(text("SELECT COLUMN_NAME,COLUMN_COMMENT FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='tencent_cost_period' AND COLUMN_NAME IN ('granularity','period_key')")).all()
        assert len(columns)==2 and all(comment and any('\u4e00'<=c<='\u9fff' for c in comment) for _,comment in columns)
    monthly(client,account,frequency='daily')
    day=client.post(base+'/cost-jobs',json={'month':'2026-11','day':'2026-11-02','idempotency_key':'new-day'})
    assert worker.run_once()
    with pytest.raises(RuntimeError,match='TENCENT_DAILY_DOWNGRADE_EVIDENCE'):
        command.downgrade(config,'0018_tencent_monthly')
    assert client.get(day.headers['location']).json()['data']['status']=='succeeded'
    assert not check_schema(sessions.kw['bind'])['errors']


@pytest.mark.parametrize('evidence',['daily_config','weekly_config','saved_anchor','pending_day','failed_day','pending_month'])
def test_daily_downgrade_refuses_unexpressible_config_or_task_before_any_ddl(cost_http,monkeypatch,evidence):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    from app.persistence.schema_check import check_schema
    client,sessions,account=cost_http
    now=datetime(2026,11,3,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    if evidence in {'daily_config','weekly_config','saved_anchor'}:
        monthly(client,account,frequency='weekly' if evidence=='weekly_config' else 'daily')
        if evidence=='saved_anchor':monthly(client,account,frequency='manual')
    else:
        monthly(client,account,frequency='manual')
        body={'month':'2026-10','idempotency_key':'unsupported'}
        if evidence!='pending_month':body['day']='2026-10-31'
        accepted=client.post(base+'/cost-jobs',json=body)
        assert accepted.status_code==202,accepted.text
        if evidence=='failed_day':
            def denied(c,a,p):
                if a=='DescribeCostExplorerSummary':return b'{"Response":{"Error":{"Code":"UnauthorizedOperation"},"RequestId":"day-no-success"}}'
                return daily_transport(c,a,p)
            assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),denied,now=lambda:now).run_once()
            assert client.get(accepted.headers['location']).json()['data']['status']=='failed'
    config=Config(str(Path(__file__).parents[2]/'alembic.ini'))
    before_config=client.get(base+'/cost-config').json()['data']
    before_jobs=client.get(base+'/cost-jobs').json()['data']
    with sessions() as db:
        assert db.execute(text("SELECT COUNT(*) FROM tencent_cost_period WHERE granularity='day'")).scalar_one()==0
        before_ddl={name:db.execute(text('SHOW CREATE TABLE '+name)).one()[1]
            for name in ('tencent_sync_config','tencent_sync_job','tencent_cost_period','tencent_cost_item')}
    with pytest.raises(RuntimeError,match='TENCENT_DAILY_DOWNGRADE_EVIDENCE'):
        command.downgrade(config,'0018_tencent_monthly')
    assert client.get(base+'/cost-config').json()['data']==before_config
    assert client.get(base+'/cost-jobs').json()['data']==before_jobs
    with sessions() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalars().all()==['0019_tencent_daily']
        assert {name:db.execute(text('SHOW CREATE TABLE '+name)).one()[1] for name in before_ddl}==before_ddl
    assert not check_schema(sessions.kw['bind'])['errors']
