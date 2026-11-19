"""已确认 seam：管理端 HTTP、实际 scheduler/worker、独立 MySQL 与完整看板/CSV。"""
from datetime import datetime
import json
from app.config import get_settings
from app.main import app
from test_tencent_accounts_mysql import tencent_http
from test_tencent_cost_mysql import cost_http, wire
from test_tencent_monthly_mysql import monthly, drain


def daily_transport(credential, action, params):
    if action == 'DescribeAccountBalance':
        return b'{"Response":{"Uin":10001,"RequestId":"daily-identity"}}'
    label = params['BeginTime'][:10] if params['PeriodType']=='day' else params['BeginTime'][:7]
    value=wire(label[:7])
    if params['PeriodType']=='day':
        value=json.loads(json.dumps(value).replace(label[:7]+'-01 00:00:00',label+' 00:00:00'))
    if params['PageNo']>1:value['Response']['Detail']=[]
    return json.dumps(value).encode()


def test_daily_batch_freezes_yesterday_and_aggregates_actual_days_without_month_copy(cost_http,monkeypatch):
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    from app.tencent import cost_router
    now=[datetime(2026,11,2,5,30)]
    monkeypatch.setattr(cost_router,'utcnow',lambda:now[0])
    monthly(client,account,frequency='daily')
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0])
    assert scheduler.tick()==1
    base=f"/admin/api/tencent/accounts/{account['id']}"
    batch=next(j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch')
    url='/admin/api/tencent/cost-jobs/'+batch['id']
    before=client.get(url).json()['data']
    assert before['periods'][0]=={'granularity':'day','period_key':'2026-11-01','month':'2026-11'}
    assert len(before['periods'])==32
    now[0]=datetime(2026,11,3,0)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now[0])
    drain(worker)
    done=client.get(url).json()['data']
    assert done['status']=='succeeded' and done['attempts']==[], done
    assert done['periods']==before['periods']
    dashboard=client.get(base+'/cost-dashboard?start_month=2026-10&end_month=2026-11').json()['data']
    assert dashboard['known_total']=='384.00000000'
    assert dashboard['months'][0]['total']=='372.00000000'
    assert dashboard['months'][0]['coverage_complete'] is True
    assert dashboard['months'][1]['total']=='12.00000000'
    assert dashboard['months'][1]['coverage_complete'] is False
    assert dashboard['months'][1]['source_granularity']=='day'
    assert dashboard['months'][1]['covered_through']=='2026-11-01'
    assert dashboard['months'][1]['mom']['value'] is None
    legacy_month=client.get(base+'/cost-periods/2026-10')
    assert legacy_month.status_code==200,legacy_month.text
    full=legacy_month.json()['data']
    assert full['total']=='372.00000000' and full['coverage']['status']=='complete'
    assert full['granularity']=='day' and len(full['covered_dates'])==31
    assert sum(__import__('decimal').Decimal(i['amount']) for i in full['items'])==__import__('decimal').Decimal('372')
    partial=client.get(base+'/cost-periods/2026-11').json()['data']
    assert partial['total']=='12.00000000' and partial['coverage']['status']=='incomplete'
    assert partial['covered_through']=='2026-11-01' and len(partial['missing_dates'])==29
    from app.persistence.models import DatasetState
    with sessions.begin() as db:db.get(DatasetState,1).dataset_epoch='fresh-organization-epoch'
    assert client.get(base+'/cost-dashboard?start_month=2026-10&end_month=2026-11').json()['data']==dashboard
    exported=client.get(base+'/cost-export?start_month=2026-10&end_month=2026-11')
    assert exported.status_code==200 and '372.00000000' not in exported.text # products retain separate precise amounts
    from sqlalchemy import select
    from app.persistence.models import TencentCostPeriod
    with sessions() as db:
        periods=db.scalars(select(TencentCostPeriod)).all()
        assert len(periods)==32 and all(p.granularity=='day' for p in periods)



def test_failed_daily_rerun_keeps_day_but_new_month_switch_replaces_days_atomically(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    from sqlalchemy import select
    from app.persistence.models import TencentCostPeriod
    client,sessions,account=cost_http
    now=datetime(2026,11,2,5,30)
    monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='daily')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    accepted=client.post(base+'/cost-jobs',json={'month':'2026-10','day':'2026-10-31','idempotency_key':'day-one'})
    assert accepted.status_code==202,accepted.text
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    assert worker.run_once()
    first=client.get(accepted.headers['location']).json()['data']
    assert first['status']=='succeeded'
    rerun=client.post(accepted.headers['location']+'/rerun',json={'idempotency_key':'rerun-day','reason':'refresh_result'})
    assert rerun.status_code==202,rerun.text
    assert rerun.json()['data']['period_key']=='2026-10-31'
    monthly(client,account,frequency='monthly')
    assert worker.run_once() # old daily snapshot remains a day after frequency edit
    assert client.get(rerun.headers['location']).json()['data']['status']=='succeeded'
    failed=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'failed-month'})
    def denied(c,a,p):
        if a=='DescribeCostExplorerSummary':return b'{"Response":{"Error":{"Code":"UnauthorizedOperation"},"RequestId":"denied-month"}}'
        return daily_transport(c,a,p)
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),denied,now=lambda:now).run_once()
    before=client.get(base+'/cost-dashboard?start_month=2026-10&end_month=2026-10').json()['data']
    assert before['known_total']=='12.00000000' and before['months'][0]['coverage_complete'] is False
    accepted_month=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'replace-month'})
    assert accepted_month.status_code==202
    assert worker.run_once()
    after=client.get(base+'/cost-dashboard?start_month=2026-10&end_month=2026-10').json()['data']
    assert after['known_total']=='12.00000000' and after['months'][0]['coverage_complete'] is True
    with sessions() as db:
        rows=db.scalars(select(TencentCostPeriod)).all()
        assert len(rows)==1 and rows[0].granularity=='month'
    monthly(client,account,frequency='weekly')
    normalized=client.post(base+'/cost-jobs',json={'month':'2026-10','day':'2026-10-31','idempotency_key':'day-hits-month'})
    assert normalized.status_code==202,normalized.text
    assert normalized.json()['data']['period_key']=='2026-10'
    assert worker.run_once()
    assert client.get(normalized.headers['location']).json()['data']['status']=='succeeded'

import pytest
from datetime import timedelta


@pytest.mark.parametrize('empty',[True,False])
def test_unconfirmed_daily_zero_preserves_prior_cost_without_month_ready_shortcut(cost_http,monkeypatch,empty):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,3,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='daily')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    first=client.post(base+'/cost-jobs',json={'month':'2026-10','day':'2026-10-31','idempotency_key':'nonzero'})
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    assert worker.run_once()
    rerun=client.post(first.headers['location']+'/rerun',json={'idempotency_key':'zero','reason':'refresh_result'})
    actions=[]
    def zeros(c,a,p):
        actions.append(a)
        if a=='DescribeAccountBalance':return daily_transport(c,a,p)
        root=json.loads(daily_transport(c,a,p));v=root['Response']
        v['TotalDetail']['Total']='0';v['TotalDetail']['TimeDetail'][0]['Money']='0'
        if empty:v['Total']=0;v['Detail']=[]
        for row in v['Detail']:row['Total']='0';row['TimeDetail'][0]['Money']='0'
        return json.dumps(root).encode()
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),zeros,now=lambda:now).run_once()
    result=client.get(rerun.headers['location']).json()['data']
    assert result['status']=='failed' and result['error_code']=='TENCENT_COST_ZERO_UNCONFIRMED'
    assert 'DescribeBillSummaryByProduct' not in actions
    retained=client.get(base+'/cost-periods/2026-10-31').json()['data']
    assert retained['total']=='12.00000000'
    dashboard=client.get(base+'/cost-dashboard?start_month=2026-10&end_month=2026-10').json()['data']
    assert dashboard['months'][0]['status']=='failed_retained'
    assert dashboard['months'][0]['missing_dates'][0]=='2026-10-01'
    assert dashboard['complete_total'] is None


def test_nonempty_daily_positive_negative_net_zero_preserves_all_products(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,3,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='daily')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    accepted=client.post(base+'/cost-jobs',json={'month':'2026-10','day':'2026-10-31','idempotency_key':'net-zero'})
    def netzero(c,a,p):
        if a=='DescribeAccountBalance':return daily_transport(c,a,p)
        root=json.loads(daily_transport(c,a,p));v=root['Response']
        v['TotalDetail']['Total']='0';v['TotalDetail']['TimeDetail'][0]['Money']='0'
        for index,row in enumerate(v['Detail']):
            row['Total']='1' if index==0 else '-1';row['TimeDetail'][0]['Money']=row['Total']
        return json.dumps(root).encode()
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),netzero,now=lambda:now).run_once()
    assert client.get(accepted.headers['location']).json()['data']['status']=='succeeded'
    period=client.get(base+'/cost-periods/2026-10-31').json()['data']
    assert period['total']=='0.00000000'
    assert [p['amount'] for p in period['items']]==['1.00000000','-1.00000000']


def test_weekly_sunday_uses_shanghai_last_scheduled_date_and_frozen_new_year_range(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=[datetime(2027,1,3,5,29)] # Sunday13:29 Shanghai
    monkeypatch.setattr(cost_router,'utcnow',lambda:now[0])
    monthly(client,account,frequency='weekly')
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0])
    assert scheduler.tick()==1 # one merged missed Sunday, never a fictitious Monday schedule
    base=f"/admin/api/tencent/accounts/{account['id']}"
    batch=next(j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch')
    old=client.get('/admin/api/tencent/cost-jobs/'+batch['id']).json()['data']
    assert old['scheduled_at']=='2026-12-27T05:30:00Z'
    assert all(p['period_key']<='2026-12-26' for p in old['periods'])
    # Finish old batch, then due Sunday creates exactly one current event with Jan1–2 and Dec dates.
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now[0])
    drain(worker,100)
    now[0]=datetime(2027,1,3,5,30)
    assert scheduler.tick()==1 and scheduler.tick()==0
    newest=next(j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch')
    current=client.get('/admin/api/tencent/cost-jobs/'+newest['id']).json()['data']
    assert current['scheduled_at']=='2027-01-03T05:30:00Z'
    assert current['periods'][:2]==[{'granularity':'day','period_key':'2027-01-01','month':'2027-01'},{'granularity':'day','period_key':'2027-01-02','month':'2027-01'}]
    assert len({p['period_key'] for p in current['periods']})==len(current['periods'])
    now[0]=datetime(2027,1,4,5,30)
    assert scheduler.tick()==0
    drain(worker,100)


def test_cross_midnight_retry_preserves_actual_day_and_original_budget_after_frequency_switch(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=[datetime(2026,11,3,15,59,58)]
    monkeypatch.setattr(cost_router,'utcnow',lambda:now[0])
    current=monthly(client,account,frequency='daily')
    monthly(client,account,frequency='daily',run_policy={**current['run_policy'],'max_attempts':2,'retry_base_seconds':5,'retry_max_seconds':5,'retry_jitter_seconds':0})
    base=f"/admin/api/tencent/accounts/{account['id']}"
    accepted=client.post(base+'/cost-jobs',json={'month':'2026-11','day':'2026-11-02','idempotency_key':'midnight'})
    fail=[True]
    def transient(c,a,p):
        if a=='DescribeCostExplorerSummary' and fail[0]:fail[0]=False;raise TimeoutError()
        return daily_transport(c,a,p)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transient,now=lambda:now[0])
    assert worker.run_once()
    assert client.get(accepted.headers['location']).json()['data']['status']=='retry_wait'
    monthly(client,account,frequency='monthly')
    now[0]+=timedelta(seconds=6)
    assert worker.run_once()
    result=client.get(accepted.headers['location']).json()['data']
    assert result['status']=='succeeded' and len(result['attempts'])==2
    assert [a['execution_input']['period_key'] for a in result['attempts']]==['2026-11-02','2026-11-02']
    assert result['attempts'][1]['execution_input']['frequency']=='daily'
    assert result['attempts'][1]['execution_input']['upstream_params']['EndTime']=='2026-11-02 23:59:59'


def test_pending_daily_snapshot_is_rejected_if_prior_month_job_committed_not_expanded_at_retry(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,3,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='monthly')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    month_job=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'month-first'})
    monthly(client,account,frequency='daily')
    day_job=client.post(base+'/cost-jobs',json={'month':'2026-10','day':'2026-10-31','idempotency_key':'day-after'})
    assert day_job.json()['data']['granularity']=='day'
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    assert worker.run_once() and worker.run_once()
    assert client.get(month_job.headers['location']).json()['data']['status']=='succeeded'
    rejected=client.get(day_job.headers['location']).json()['data']
    assert rejected['error_code']=='TENCENT_COST_PERIOD_OVERLAP' and rejected['period_key']=='2026-10-31'
    assert client.get(base+'/cost-dashboard?start_month=2026-10&end_month=2026-10').json()['data']['known_total']=='12.00000000'


def test_system_month_snapshot_survives_frequency_edit_and_next_daily_batch_normalizes_existing_month(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,3,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account)
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    assert scheduler.tick()==1
    base=f"/admin/api/tencent/accounts/{account['id']}"
    old=next(j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch')
    monthly(client,account,frequency='daily')
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    drain(worker)
    assert client.get('/admin/api/tencent/cost-jobs/'+old['id']).json()['data']['status']=='succeeded'
    accepted=client.post(base+'/cost-batches',json={'idempotency_key':'day-normalization'})
    batch=client.get(accepted.headers['location']).json()['data']
    assert batch['periods']==[{'granularity':'day','period_key':'2026-11-01','month':'2026-11'},
        {'granularity':'day','period_key':'2026-11-02','month':'2026-11'},
        {'granularity':'month','period_key':'2026-10','month':'2026-10'}]
    drain(worker)
    assert client.get(accepted.headers['location']).json()['data']['status']=='succeeded'
    data=client.get(base+'/cost-dashboard?start_month=2026-10&end_month=2026-11').json()['data']
    assert data['known_total']=='36.00000000'
    assert [m['source_granularity'] for m in data['months']]==['month','day']
    assert data['months'][1]['mom']=={'value':None,'reason':'incomplete_coverage'}


def test_day_to_month_switch_keeps_query_totals_products_and_csv_in_one_mysql_snapshot(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    from threading import Event
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import event
    client,sessions,account=cost_http
    now=datetime(2026,11,3,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='daily')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    first=client.post(base+'/cost-jobs',json={'month':'2026-10','day':'2026-10-31','idempotency_key':'old-day'})
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    assert worker.run_once()
    monthly(client,account,frequency='monthly')
    accepted=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'new-month'})
    paused,replaced=Event(),Event();engine=sessions.kw['bind']
    def barrier(connection,cursor,statement,parameters,context,many):
        if 'FROM tencent_cost_period' in statement and 'JOIN' not in statement and not paused.is_set():
            paused.set();assert replaced.wait(15)
    def replacement(c,a,p):
        if a=='DescribeAccountBalance':return daily_transport(c,a,p)
        v=wire('2026-10',single=True)
        if p['PageNo']>1:v['Response']['Detail']=[]
        return json.dumps(v).encode()
    event.listen(engine,'after_cursor_execute',barrier)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(client.get,base+'/cost-dashboard?start_month=2026-10&end_month=2026-10')
            assert paused.wait(5)
            try:assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),replacement,now=lambda:now).run_once()
            finally:replaced.set()
            observed=pending.result(timeout=15).json()['data']
    finally:event.remove(engine,'after_cursor_execute',barrier)
    assert observed['known_total']=='12.00000000'
    assert len(observed['products'])==2 and observed['months'][0]['source_granularity']=='day'
    current=client.get(base+'/cost-dashboard?start_month=2026-10&end_month=2026-10').json()['data']
    assert current['known_total']=='12.34567890' and len(current['products'])==1
    assert current['months'][0]['source_granularity']=='month'
    exported=client.get(base+'/cost-export?start_month=2026-10&end_month=2026-10')
    assert '12.34567890' in exported.text and '-0.34567890' not in exported.text


def test_old_daily_gap_counts_only_finished_automatic_batches_and_stops_after_three(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=[datetime(2026,11,3,5,30)];monkeypatch.setattr(cost_router,'utcnow',lambda:now[0])
    monthly(client,account,frequency='daily')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    def old_gap(c,a,p):
        if a=='DescribeCostExplorerSummary' and p['BeginTime'].startswith('2026-09-30'):
            return b'{"Response":{"Error":{"Code":"UnauthorizedOperation"},"RequestId":"old-day-denied"}}'
        return daily_transport(c,a,p)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),old_gap,now=lambda:now[0])
    for i in range(3):
        response=client.post(base+'/cost-jobs',json={'month':'2026-09','day':'2026-09-30','idempotency_key':f'manual-failure-{i}'})
        assert response.status_code==202
        assert worker.run_once()
        assert client.get(response.headers['location']).json()['data']['status']=='failed'
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0])
    for i in range(3):
        assert scheduler.tick()==1
        batch=next(j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch')
        detail=client.get('/admin/api/tencent/cost-jobs/'+batch['id']).json()['data']
        assert '2026-09-30' in [p['period_key'] for p in detail['periods']]
        assert detail['blocked_periods']==[]
        drain(worker,100)
        assert client.get('/admin/api/tencent/cost-jobs/'+batch['id']).json()['data']['finished_at'] is not None
        now[0]+=timedelta(days=1)
    monthly(client,account,frequency='weekly') # 同一实际日范围跨频率仍共享自动预算
    now[0]=datetime(2026,11,8,5,30)
    assert scheduler.tick()==1
    batch=next(j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch')
    blocked=client.get('/admin/api/tencent/cost-jobs/'+batch['id']).json()['data']
    assert blocked['blocked_periods']==[{'period_key':'2026-09-30','reason_code':'TENCENT_PERIOD_AUTO_BUDGET_EXHAUSTED'}]
    assert '2026-09-30' not in [p['period_key'] for p in blocked['periods']]
    assert scheduler.tick()==0
    drain(worker,100)


def test_daily_recent_recheck_applies_late_cost_and_complete_months_remain_comparable(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    from decimal import Decimal
    client,sessions,account=cost_http
    now=[datetime(2026,10,31,5,30)];monkeypatch.setattr(cost_router,'utcnow',lambda:now[0])
    monthly(client,account,frequency='daily')
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0])
    base=f"/admin/api/tencent/accounts/{account['id']}"
    assert scheduler.tick()==1
    drain(TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now[0]),100)
    initial=client.get(base+'/cost-dashboard?start_month=2026-09&end_month=2026-10').json()['data']
    assert initial['months'][0]['total']=='360.00000000' and initial['months'][1]['total']=='360.00000000'
    assert initial['months'][1]['coverage_complete'] is False
    # 翌日复核10月1日；迟到费用改成单产品24元，同时移除旧负退款产品。
    now[0]=datetime(2026,11,1,5,30)
    def corrected(c,a,p):
        if a=='DescribeAccountBalance' or not p['BeginTime'].startswith('2026-10-01'):
            return daily_transport(c,a,p)
        v=json.loads(daily_transport(c,a,p));r=v['Response'];r['Total']=1
        if p['PageNo']==1:
            r['Detail']=r['Detail'][:1]
            r['Detail'][0]['Total']='24';r['Detail'][0]['TimeDetail'][0]['Money']='24'
        r['TotalDetail']['Total']='24';r['TotalDetail']['TimeDetail'][0]['Money']='24'
        return json.dumps(v).encode()
    assert scheduler.tick()==1
    drain(TencentCostWorker(sessions,app.dependency_overrides[get_settings](),corrected,now=lambda:now[0]),100)
    result=client.get(base+'/cost-dashboard?start_month=2026-09&end_month=2026-10').json()['data']
    assert result['known_total']=='744.00000000' and result['complete_total']=='744.00000000'
    assert result['months'][1]['total']=='384.00000000' and result['months'][1]['coverage_complete'] is True
    assert result['months'][1]['mom']=={'value':'6.666667','reason':None}
    original=client.get(base+'/cost-periods/2026-10-01').json()['data']
    assert len(original['items'])==1 and original['items'][0]['amount']=='24.00000000'
    summary=client.get(base+'/cost-periods/2026-10').json()['data']
    assert summary['coverage']['aggregation']=='query' and summary['coverage']['source_period_count']==31
    assert sum(Decimal(row['amount']) for row in summary['items'])==Decimal('384')
    exported=client.get(base+'/cost-export?start_month=2026-09&end_month=2026-10')
    assert exported.status_code==200 and ',day,' in exported.text
