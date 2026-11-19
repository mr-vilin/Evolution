"""真实 MySQL 迁移回填、中文备注及任何 DDL 前的历史证据保护。"""
from pathlib import Path
from datetime import datetime
from alembic import command
from alembic.config import Config
from sqlalchemy import text
import pytest
from app.config import get_settings
from app.main import app
from app.persistence.database import CURRENT_SCHEMA_HEAD
from test_tencent_accounts_mysql import tencent_http
from test_tencent_cost_mysql import cost_http
from test_tencent_monthly_mysql import monthly,drain
from test_tencent_daily_mysql import daily_transport


def alembic():return Config(str(Path(__file__).parents[2]/'alembic.ini'))


def structure(sessions):
    with sessions() as db:
        return {name:db.execute(text('SHOW CREATE TABLE '+name)).one()[1] for name in
            ('tencent_sync_config','tencent_sync_job','tencent_cost_period','tencent_cost_item')}


def test_history_migration_roundtrip_retains_existing_month_and_validates_orm_comments(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    from app.persistence.schema_check import check_schema
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='manual');base=f"/admin/api/tencent/accounts/{account['id']}"
    accepted=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'legacy-month'})
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now).run_once()
    before=client.get(base+'/cost-periods/2026-10').json()['data']
    command.downgrade(alembic(),'0019_tencent_daily');command.upgrade(alembic(),'head')
    assert client.get(base+'/cost-periods/2026-10').json()['data']==before
    assert not check_schema(sessions.kw['bind'])['errors']
    with sessions() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()==CURRENT_SCHEMA_HEAD
        rows=db.execute(text("SELECT TABLE_NAME,COLUMN_NAME,COLUMN_COMMENT FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND ((TABLE_NAME='tencent_sync_config' AND COLUMN_NAME='history_progress') OR (TABLE_NAME='tencent_sync_job' AND COLUMN_NAME='priority'))")).all()
        assert len(rows)==2 and all(any('\u4e00'<=c<='\u9fff' for c in row[2]) for row in rows)


@pytest.mark.parametrize('target',['0019_tencent_daily','0018_tencent_monthly','0017_tencent_maintenance'])
def test_history_progress_or_range_jobs_block_downgrade_before_any_ddl(cost_http,monkeypatch,target):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account);scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    scheduler.tick();drain(worker);scheduler.tick();drain(worker)
    before=structure(sessions)
    with pytest.raises(RuntimeError,match='TENCENT_HISTORY_DOWNGRADE_EVIDENCE'):command.downgrade(alembic(),target)
    assert structure(sessions)==before
    with sessions() as db:assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()==CURRENT_SCHEMA_HEAD


@pytest.mark.parametrize('target',['0018_tencent_monthly','0017_tencent_maintenance'])
def test_cross_older_downgrade_checks_daily_evidence_before_history_ddl(cost_http,monkeypatch,target):
    from app.tencent import cost_router
    client,sessions,account=cost_http
    monkeypatch.setattr(cost_router,'utcnow',lambda:datetime(2026,11,17,5,30))
    monthly(client,account,frequency='daily')
    before=structure(sessions)
    with pytest.raises(RuntimeError,match='TENCENT_DAILY_DOWNGRADE_EVIDENCE'):command.downgrade(alembic(),target)
    assert structure(sessions)==before


def test_upgrade_classifies_existing_old_queue_but_preserves_both_recent_months(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='manual');base=f"/admin/api/tencent/accounts/{account['id']}"
    old=client.post(base+'/cost-jobs',json={'month':'2026-08','idempotency_key':'old-first'})
    recent=client.post(base+'/cost-jobs',json={'month':'2026-09','idempotency_key':'recent-second'})
    command.downgrade(alembic(),'0019_tencent_daily');command.upgrade(alembic(),'head')
    seen=[]
    def observed(c,a,p):
        if a=='DescribeCostExplorerSummary':seen.append(p['BeginTime'][:7])
        return daily_transport(c,a,p)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),observed,now=lambda:now)
    assert worker.run_once() and seen[0]=='2026-09'
    drain(worker)
