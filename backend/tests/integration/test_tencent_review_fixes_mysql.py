from datetime import datetime
from app.main import app
from app.config import get_settings
from app.tencent import cost_router
from app.tencent.cost_worker import TencentCostWorker
from app.tencent.cost_scheduler import TencentCostScheduler
from test_tencent_accounts_mysql import tencent_http
from test_tencent_cost_mysql import cost_http
from test_tencent_monthly_mysql import monthly, drain
from test_tencent_daily_mysql import daily_transport


def test_monthly_single_day_must_respect_selected_mode(cost_http, monkeypatch):
    client,sessions,account=cost_http
    now=datetime(2026,11,2,5,30)
    monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='monthly')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    result=client.post(base+'/cost-jobs',json={'month':'2026-11','day':'2026-11-01','idempotency_key':'monthly-bypass'})
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    drain(worker)
    assert result.status_code==422


def test_daily_small_queue_keeps_unadmitted_recent_periods_visible(cost_http,monkeypatch):
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30)
    monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    config=monthly(client,account,frequency='daily')
    monthly(client,account,frequency='daily',run_policy={**config['run_policy'],'queue_limit':1})
    base=f"/admin/api/tencent/accounts/{account['id']}"
    seen=[]
    def outbound(credential,action,params):
        if action=='DescribeCostExplorerSummary' and params['PageNo']==1:seen.append(params['BeginTime'][:10])
        return daily_transport(credential,action,params)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),outbound,now=lambda:now)
    covered=client.post(base+'/cost-jobs',json={'month':'2026-10','day':'2026-10-31','idempotency_key':'covered-recent-day'})
    assert covered.status_code==202;drain(worker);seen.clear()
    accepted=client.post(base+'/cost-batches',json={'idempotency_key':'small-daily'})
    assert accepted.status_code==202,accepted.text
    drain(worker)
    result=client.get(accepted.headers['location']).json()['data']
    assert result['deferred_periods']
    assert result['status']!='succeeded'


    assert len(result['deferred_periods'])==46
    assert '2026-10-31' in result['deferred_periods']
    from app.persistence.models import ChangeLog
    from sqlalchemy import select
    with sessions() as db:
        events=db.scalars(select(ChangeLog).where(ChangeLog.object_type=='tencent_batch',ChangeLog.object_id==accepted.json()['data']['id'])).all()
        assert any(event.after_data.get('deferred_count')==46 for event in events)
    assert result['scope_status']=='pending'
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    for _ in range(80):
        if client.get(accepted.headers['location']).json()['data']['status']=='succeeded':break
        assert scheduler.tick()==1
        drain(worker)
    final=client.get(accepted.headers['location']).json()['data']
    assert final['status']=='succeeded' and final['scope_status']=='complete'
    assert len(final['children'])==47 and not final['deferred_periods']
    assert '2026-10-31' in seen # 已覆盖近期也重新采集，不能退化为仅补缺。
    replay=client.post(base+'/cost-batches',json={'idempotency_key':'small-daily'})
    assert replay.json()['data']['id']==final['id']
    assert replay.json()['data']['periods']==final['periods']


def test_weekly_history_cannot_collect_new_monday_before_next_sunday(cost_http,monkeypatch):
    client,sessions,account=cost_http
    clock=[datetime(2026,11,15,5,30)] # Sunday
    monkeypatch.setattr(cost_router,'utcnow',lambda:clock[0])
    monthly(client,account,frequency='weekly')
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:clock[0])
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:clock[0])
    for _ in range(20):
        created=scheduler.tick();drain(worker,250)
        if not created:break
    base=f"/admin/api/tencent/accounts/{account['id']}"
    before=client.get(base+'/cost-history').json()['data']
    clock[0]=datetime(2026,11,17,5,30) # Tuesday, next schedule Sunday 22
    created=scheduler.tick()
    drain(worker,250)
    history=client.get(base+'/cost-history').json()['data']
    period=client.get(base+'/cost-periods/2026-11').json()['data']
    assert period.get('covered_through')=='2026-11-14'

    assert history['recent']==before['recent']
    assert history['target_period_count']==before['target_period_count']
    assert history['unexplored']==[]
    manual=client.post(base+'/cost-range-batches',json={'scope':'range','start_date':'2026-11-16','end_date':'2026-11-16','idempotency_key':'manual-monday'})
    assert manual.status_code==202
    drain(worker)
    assert client.get(base+'/cost-periods/2026-11-16').status_code==200
    clock[0]=datetime(2026,11,22,5,30)
    assert scheduler.tick()==1
    drain(worker,250)
    assert client.get(base+'/cost-periods/2026-11').json()['data']['covered_through']=='2026-11-21'


def test_epoch_rejected_old_refresh_does_not_degrade_committed_coverage(cost_http):
    from app.persistence.models import DatasetState
    from test_tencent_cost_mysql import enable_cost,run_job
    client,sessions,account=cost_http
    enable_cost(client,account)
    for m in ('2026-09','2026-10'):
        assert run_job(client,sessions,account,'base-'+m,month=m)['status']=='succeeded'
    base=f"/admin/api/tencent/accounts/{account['id']}"
    query='?start_month=2026-09&end_month=2026-10'
    accepted=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'old-refresh'})
    with sessions.begin() as db:db.get(DatasetState,1).dataset_epoch='restored-epoch'
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport)
    drain(worker)
    old=client.get(accepted.headers['location']).json()['data']
    data=client.get(base+'/cost-dashboard'+query).json()['data']
    assert old['status']=='failed' and old['error_code']=='DATASET_CHANGED' and old['attempts']==[]
    assert data['months'][-1]['status']=='complete'
    assert data['months'][-1]['latest_task_status']=='failed'
    assert data['complete_total']=='24.00000000'
    assert data['months'][-1]['mom']['value']=='0.000000'


def test_monthly_queue_one_rechecks_already_covered_months_on_original_parent(cost_http,monkeypatch):
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    config=monthly(client,account)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    seen=[]
    def outbound(c,a,p):
        if a=='DescribeCostExplorerSummary':seen.append(p['BeginTime'][:7])
        return daily_transport(c,a,p)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),outbound,now=lambda:now)
    for month in ('2026-09','2026-10'):
        assert client.post(base+'/cost-jobs',json={'month':month,'idempotency_key':'covered-'+month}).status_code==202
        drain(worker)
    config=monthly(client,account,run_policy={**config['run_policy'],'queue_limit':1})
    accepted=client.post(base+'/cost-batches',json={'idempotency_key':'small-monthly'})
    assert accepted.status_code==202
    seen.clear();drain(worker)
    detail=client.get(accepted.headers['location']).json()['data']
    assert detail['status']=='pending' and detail['scope_status']=='pending'
    assert detail['deferred_months']==['2026-09'] and detail['deferred_periods']==['2026-09']
    monthly(client,account,frequency='manual',run_policy={**config['run_policy'],'max_attempts':2})
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    assert scheduler.tick()==1;drain(worker)
    final=client.get(accepted.headers['location']).json()['data']
    assert final['status']=='succeeded' and final['scope_status']=='complete'
    assert list(dict.fromkeys(seen))==['2026-10','2026-09']
    child=client.get('/admin/api/tencent/cost-jobs/'+final['children'][-1]['id']).json()['data']
    assert child['attempts'][0]['execution_input']['frequency']=='monthly'
    assert child['attempts'][0]['execution_input']['policy']==config['run_policy']


def test_unexpected_database_failure_has_safe_diagnostic_and_terminal_error_log(cost_http,caplog):
    from sqlalchemy import event
    import logging
    client,sessions,account=cost_http
    from test_tencent_cost_mysql import enable_cost
    enable_cost(client,account)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    accepted=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'diagnostic-db'})
    engine=sessions.kw['bind'];fired=[]
    def fail_financial_write(connection,cursor,statement,parameters,context,many):
        if not fired and statement.startswith('INSERT INTO tencent_cost_period'):
            fired.append(True)
            raise RuntimeError('synthetic-password SECRET_KEY financial-response-body 123456789')
    event.listen(engine,'before_cursor_execute',fail_financial_write)
    try:
        with caplog.at_level(logging.INFO,logger='evolution.tencent.cost_worker'):
            assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport).run_once()
    finally:event.remove(engine,'before_cursor_execute',fail_financial_write)
    detail=client.get(accepted.headers['location']).json()['data']
    assert detail['status']=='failed' and detail['error_code']=='TENCENT_COST_EXECUTION_FAILED'
    diagnostic=detail['attempts'][0]['failure_evidence']['diagnostic']
    assert diagnostic['error_type']=='RuntimeError'
    assert diagnostic['exception_chain'][0]['frames'][-1]['function']=='fail_financial_write'
    records=[record for record in caplog.records if 'tencent.cost_failed' in record.getMessage()]
    assert len(records)==1 and records[0].levelno==logging.ERROR
    assert records[0].safe_diagnostic['error_type']=='RuntimeError'
    assert 'SECRET_KEY' not in caplog.text and 'financial-response-body' not in str(diagnostic)


def test_terminal_upstream_failure_is_error_and_real_commit_is_info(cost_http,caplog):
    import logging
    from test_tencent_cost_mysql import enable_cost
    client,sessions,account=cost_http;enable_cost(client,account)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    config=monthly(client,account,frequency='manual')
    monthly(client,account,frequency='manual',run_policy={**config['run_policy'],'max_attempts':1})
    job=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'terminal-log'})
    def timeout(c,a,p):raise TimeoutError('synthetic-private-response')
    with caplog.at_level(logging.INFO,logger='evolution.tencent.cost_worker'):
        assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),timeout).run_once()
    assert client.get(job.headers['location']).json()['data']['status']=='failed'
    assert any(r.levelno==logging.ERROR and 'tencent.cost_failed' in r.getMessage() for r in caplog.records)
    assert client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'successful-log'}).status_code==202
    with caplog.at_level(logging.INFO,logger='evolution.tencent.cost_worker'):
        assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport).run_once()
    assert any(r.levelno==logging.INFO and 'tencent.cost_started' in r.getMessage() for r in caplog.records)
    assert any(r.levelno==logging.INFO and 'tencent.cost_committed' in r.getMessage() for r in caplog.records)
    assert 'synthetic-private-response' not in caplog.text


import pytest

@pytest.mark.parametrize('rollover',['queued','during_auxiliary'])
def test_oldest_month_zero_evidence_expires_when_actual_source_window_moves(cost_http,monkeypatch,rollover):
    import json
    from test_tencent_cost_mysql import wire
    from app.persistence.models import TencentSyncJob
    client,sessions,account=cost_http
    clock=[datetime(2026,10,31,15,50)]
    monkeypatch.setattr(cost_router,'utcnow',lambda:clock[0])
    monthly(client,account,frequency='manual')
    base=f"/admin/api/tencent/accounts/{account['id']}";month='2025-10'
    def populated(credential,action,params):
        if action=='DescribeAccountBalance':return b'{"Response":{"Uin":10001,"RequestId":"rollover-identity"}}'
        result=wire(month)
        if params['PageNo']>1:result['Response']['Detail']=[]
        return json.dumps(result).encode()
    assert client.post(base+'/cost-jobs',json={'month':month,'idempotency_key':'existing-nonzero'}).status_code==202
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),populated,now=lambda:clock[0]).run_once()
    original=client.get(base+'/cost-periods/'+month).json()['data']
    assert original['total']=='12.00000000' and len(original['items'])==2
    clock[0]=datetime(2026,10,31,15,55)
    accepted=client.post(base+'/cost-jobs',json={'month':month,'idempotency_key':'last-window-month'})
    with sessions() as db:
        pending=db.get(TencentSyncJob,int(accepted.json()['data']['id']))
        assert pending.snapshot['month_zero_eligible'] is True
        deadline=pending.queue_deadline_at
    clock[0]=datetime(2026,10,31,16,5) if rollover=='queued' else datetime(2026,10,31,15,59,59)
    def empty_ready(credential,action,params):
        if action=='DescribeAccountBalance':return b'{"Response":{"Uin":10001,"RequestId":"rollover-identity"}}'
        if action=='DescribeBillSummaryByProduct':
            clock[0]=datetime(2026,10,31,16,0,1)
            return b'{"Response":{"RequestId":"rollover-ready","Ready":1,"SummaryOverview":[],"SummaryTotal":{"RealTotalCost":"0.00000000"}}}'
        result=wire(month)['Response'];result['Total']=0;result['Detail']=[]
        result['TotalDetail']['Total']='0.00000000';result['TotalDetail']['TimeDetail'][0]['Money']='0.00000000'
        return json.dumps({'Response':result}).encode()
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),empty_ready,now=lambda:clock[0]).run_once()
    result=client.get(accepted.headers['location']).json()['data']
    retained=client.get(base+'/cost-periods/'+month).json()['data']
    assert clock[0]<deadline
    assert result['status']=='failed' and result['error_code']=='TENCENT_COST_ZERO_UNCONFIRMED'
    assert retained==original


def test_independent_main_process_outputs_actual_worker_start_commit_and_stop(cost_http):
    import json,os,subprocess,sys
    from pathlib import Path
    client,sessions,account=cost_http
    monthly(client,account,frequency='manual')
    accepted=client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs",json={'month':'2026-10','idempotency_key':'independent-main'})
    env=os.environ.copy()
    env.update(SESSION_SECRET='test-pepper',TENCENT_CREDENTIALS='{"finance-a":{"label":"合成测试凭据","secret_id":"synthetic-id","secret_key":"synthetic-key"}}')
    env['PYTHONPATH']=str(Path(__file__).parents[2])+os.pathsep+str(Path(__file__).parent)
    script="""
import threading
from app.tencent import cost_worker
from test_tencent_daily_mysql import daily_transport
# 仅替换官方出站传输；main、调度、领取、执行、发布和独立MySQL连接均为真实实现。
cost_worker.TencentCostWorker.__init__.__defaults__=(daily_transport,)
original_run=cost_worker.TencentCostWorker.run
def bounded(self,stop):
    timer=threading.Timer(3,stop.set);timer.start()
    try:original_run(self,stop,poll_seconds=.02)
    finally:timer.cancel()
cost_worker.TencentCostWorker.run=bounded
cost_worker.main()
"""
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=20)
    assert result.returncode==0,result.stderr
    logs=[json.loads(line) for line in result.stderr.splitlines()]
    names=[row['event_name'] for row in logs]
    assert 'tencent.cost_worker_started' in names and 'tencent.cost_started' in names
    assert 'tencent.cost_committed' in names and 'tencent.cost_worker_stopped' in names
    assert all(row['severity']=='INFO' for row in logs if row['event_name'] in {'tencent.cost_worker_started','tencent.cost_started','tencent.cost_committed','tencent.cost_worker_stopped'})
    assert client.get(accepted.headers['location']).json()['data']['status']=='succeeded'
    assert 'synthetic-key' not in result.stderr


@pytest.mark.parametrize('boundary',['identity','cost','timeout'])
def test_inflight_qualification_rejection_keeps_committed_coverage_but_real_collection_failure_does_not(cost_http,boundary):
    from app.persistence.models import DatasetState
    from test_tencent_cost_mysql import enable_cost,run_job
    client,sessions,account=cost_http;enable_cost(client,account)
    for month in ('2026-09','2026-10'):
        assert run_job(client,sessions,account,'inflight-base-'+month,month=month)['status']=='succeeded'
    base=f"/admin/api/tencent/accounts/{account['id']}"
    accepted=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'inflight-'+boundary})
    calls=[]
    def transport(credential,action,params):
        calls.append(action)
        if boundary=='timeout' and action=='DescribeCostExplorerSummary':raise TimeoutError('synthetic-private-upstream')
        value=daily_transport(credential,action,params)
        if action==('DescribeAccountBalance' if boundary=='identity' else 'DescribeCostExplorerSummary') and boundary!='timeout':
            with sessions.begin() as db:db.get(DatasetState,1).dataset_epoch='new-inflight-epoch'
        return value
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport).run_once()
    job=client.get(accepted.headers['location']).json()['data']
    view=client.get(base+'/cost-dashboard?start_month=2026-09&end_month=2026-10').json()['data']
    assert job['started_at'] and len(job['attempts'])==1 and job['status']=='failed'
    assert view['known_total']=='24.00000000' and view['months'][-1]['latest_task_status']=='failed'
    if boundary=='timeout':
        assert job['error_code']=='TENCENT_TIMEOUT'
        assert view['complete_total'] is None and view['months'][-1]['status']=='failed_retained'
        assert view['months'][-1]['mom']['value'] is None
    else:
        assert job['error_code']=='DATASET_CHANGED'
        assert view['complete_total']=='24.00000000' and view['months'][-1]['status']=='complete'
        assert view['months'][-1]['mom']=={'value':'0.000000','reason':None}
    if boundary=='identity':assert calls==['DescribeAccountBalance']
