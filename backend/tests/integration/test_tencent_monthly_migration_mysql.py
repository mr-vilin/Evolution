"""仅专用临时 MySQL：旧手动工单升级保留和含批次证据的降级拒绝。"""
import json
from datetime import datetime
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from app.main import app
from app.config import get_settings
from test_tencent_accounts_mysql import tencent_http


def test_monthly_migration_preserves_legacy_request_namespace_and_refuses_batch_evidence_loss(tencent_http):
    from app.tencent.cost_scheduler import TencentCostScheduler
    client,sessions,_=tencent_http
    account=client.post('/admin/api/tencent/accounts',json={'uin':'10001','alias':'迁移账号','credential_ref':'finance-a'}).json()['data']
    config=Config(str(Path(__file__).parents[2]/'alembic.ini'))
    # 夹具已核实实际版本/端口/会话和owner/active/running静默；此库仅本测试占用。
    with sessions() as db:
        assert db.execute(text("SELECT COUNT(*) FROM tencent_sync_job WHERE status IN ('pending','running','retry_wait')")).scalar_one()==0
        assert db.execute(text('SELECT COUNT(*) FROM tencent_sync_config WHERE owner IS NOT NULL OR active_job_id IS NOT NULL')).scalar_one()==0
    try:
        command.downgrade(config,'0017_tencent_maintenance')
        with sessions.begin() as db:
            db.execute(text("INSERT INTO tencent_sync_config(account_id,business,is_enabled,revision,control_revision,generation,frequency,currency) VALUES (:account,'cost',1,1,1,0,'manual','CNY')"),{'account':account['id']})
            config_id=db.execute(text('SELECT id FROM tencent_sync_config WHERE account_id=:account'),{'account':account['id']}).scalar_one()
            db.execute(text("INSERT INTO tencent_sync_job(config_id,account_id,dataset_epoch,idempotency_key,month,status,snapshot,request_id) VALUES (:config,:account,'tencent-account-test','schedule:monthly:2026-12','2026-08','failed',:snapshot,'legacy-request')"),
                {'config':config_id,'account':account['id'],'snapshot':json.dumps({'currency':'CNY','dataset_epoch':'tencent-account-test'})})
            legacy_id=db.execute(text('SELECT id FROM tencent_sync_job WHERE config_id=:config'),{'config':config_id}).scalar_one()
        command.upgrade(config,'head')
        legacy=client.get(f'/admin/api/tencent/cost-jobs/{legacy_id}').json()['data']
        assert legacy['kind']=='period' and legacy['parent_job_id'] is None and legacy['month']=='2026-08'
        path=f"/admin/api/tencent/accounts/{account['id']}/cost-config"
        saved=client.put(path,json={'revision':1,'is_enabled':True,'frequency':'monthly','currency':'CNY','execution_time':'13:30'})
        assert saved.status_code==200,saved.text
        assert TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:datetime(2026,12,3,5,30)).tick()==1
        before_jobs=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs").json()['data']
        with sessions() as db:
            before_ddl={name:db.execute(text('SHOW CREATE TABLE '+name)).one()[1]
                for name in ('tencent_sync_config','tencent_sync_job','tencent_cost_period','tencent_cost_item')}
        with pytest.raises(RuntimeError,match='TENCENT_(MONTHLY|HISTORY)_DOWNGRADE_EVIDENCE'):
            command.downgrade(config,'0017_tencent_maintenance')
        assert client.get(f'/admin/api/tencent/cost-jobs/{legacy_id}').json()['data']==legacy
        assert client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs").json()['data']==before_jobs
        with sessions() as db:
            assert db.execute(text('SELECT version_num FROM alembic_version')).scalars().all()==['0020_tencent_history']
            assert {name:db.execute(text('SHOW CREATE TABLE '+name)).one()[1] for name in before_ddl}==before_ddl
        from app.persistence.schema_check import check_schema
        assert not check_schema(sessions.kw['bind'])['errors']
    finally:
        command.upgrade(config,'head')
