"""公开 seam：HTTP 配置与批次查询 → 实际月调度/worker → 独立 MySQL。"""
from datetime import datetime
import json
from app.config import get_settings
from app.main import app
from test_tencent_accounts_mysql import tencent_http
from test_tencent_cost_mysql import cost_http, wire


def monthly(client, account, **changes):
    path=f"/admin/api/tencent/accounts/{account['id']}/cost-config"
    current=client.get(path).json()['data']
    body={'revision':current['revision'],'is_enabled':True,'frequency':'monthly','currency':'CNY',
        'execution_time':'13:30','run_policy':{**current['run_policy'],'max_attempts':1},**changes}
    result=client.put(path,json=body)
    assert result.status_code==200,result.text
    return result.json()['data']


def transport(credential,action,params):
    if action=='DescribeAccountBalance':return b'{"Response":{"Uin":10001,"RequestId":"monthly-identity"}}'
    value=wire(params['BeginTime'][:7])
    if params['PageNo']>1:value['Response']['Detail']=[]
    return json.dumps(value).encode()


def test_monthly_event_is_durable_and_parent_only_succeeds_after_real_period_children(cost_http):
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    now=datetime(2026,12,3,5,30)
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    assert scheduler.tick()==1
    assert scheduler.tick()==0
    base=f"/admin/api/tencent/accounts/{account['id']}"
    batches=[j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch']
    assert len(batches)==1
    url='/admin/api/tencent/cost-jobs/'+batches[0]['id']
    batch=client.get(url).json()['data']
    assert [j['month'] for j in batch['children']][:2]==['2026-11','2026-10']
    assert batch['attempts']==[]
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport,now=lambda:now)
    while worker.run_once():pass
    done=client.get(url).json()['data']
    assert done['status']=='succeeded'
    assert done['attempts']==[]
    assert all(j['status']=='succeeded' for j in done['children'])
    assert client.get(base+'/cost-periods/2026-11').json()['data']['total']=='12.00000000'

def test_period_and_batch_request_namespaces_cannot_suppress_a_monthly_event(cost_http):
    from app.tencent.cost_scheduler import TencentCostScheduler
    client,sessions,account=cost_http
    monthly(client,account)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    disguised=client.post(base+'/cost-jobs',json={'month':'2026-10','idempotency_key':'schedule:monthly:2026-12'})
    assert disguised.status_code==202
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:datetime(2026,12,3,5,30))
    assert scheduler.tick()==1
    assert len([j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch'])==1

def test_fast_monthly_pages_obey_shared_account_action_admission_before_actual_outbound(cost_http,monkeypatch):
    from app.tencent.cost_worker import TencentCostWorker
    from app.tencent import audit
    from sqlalchemy import select
    from app.persistence.models import TencentApiCall
    client,sessions,account=cost_http
    monthly(client,account)
    admitted=[];clock=[datetime(2026,12,3,5,30)]
    monkeypatch.setattr(audit,'now',lambda:clock[0])
    monkeypatch.setattr(audit,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+__import__('datetime').timedelta(seconds=seconds)))
    def wire_pages(credential,action,params):
        admitted.append((action,clock[0]))
        if action=='DescribeAccountBalance':return b'{"Response":{"Uin":10001,"RequestId":"identity"}}'
        value=wire(params['BeginTime'][:7])
        if params['PageNo']>1:value['Response']['Detail']=[]
        return json.dumps(value).encode()
    base=f"/admin/api/tencent/accounts/{account['id']}"
    # Two independent scheduler batches quickly create enough real calls for one limit window.
    from app.tencent.cost_scheduler import TencentCostScheduler
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:datetime(2027,6,3,5,30))
    assert scheduler.tick()==1
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),wire_pages,now=lambda:datetime(2027,6,3,5,30))
    while worker.run_once():pass
    cost_times=[t for action,t in admitted if action=='DescribeCostExplorerSummary']
    assert len(cost_times)>20
    assert max(sum(t<=other<t+__import__('datetime').timedelta(seconds=1) for other in cost_times) for t in cost_times)<=20
    with sessions() as db:
        assert len(db.scalars(select(TencentApiCall).where(TencentApiCall.direction=='outbound',TencentApiCall.action=='DescribeCostExplorerSummary')).all())==len(cost_times)

import pytest
from datetime import timedelta


def drain(worker,limit=60):
    for _ in range(limit):
        if not worker.run_once():return
    raise AssertionError('bounded monthly queue did not drain')


@pytest.mark.parametrize('date,expected',[(datetime(2027,1,1,1),['2026-11','2026-10']),
    (datetime(2027,1,2,15),['2026-11','2026-10']),(datetime(2027,1,3,5,30),['2026-12','2026-11'])])
def test_manual_immediate_batch_respects_shanghai_sync_day_and_year_boundary(cost_http,monkeypatch,date,expected):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    monkeypatch.setattr(cost_router,'utcnow',lambda:date)
    response=client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-batches",json={'idempotency_key':'boundary'})
    assert response.status_code==202,response.text
    data=client.get(response.headers['location']).json()['data']
    assert [j['month'] for j in data['children']][:2]==expected
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport,now=lambda:date)
    drain(worker)
    assert client.get(response.headers['location']).json()['data']['status']=='succeeded'


def test_config_edit_cannot_reinterpret_existing_event_and_late_adjustment_is_recollected(cost_http):
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    now=[datetime(2026,12,3,5,30)]
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0])
    assert scheduler.tick()==1
    monthly(client,account,execution_time='14:20')
    now[0]=datetime(2026,12,3,7)
    assert scheduler.tick()==0
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport,now=lambda:now[0])
    drain(worker)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    jobs=client.get(base+'/cost-jobs').json()['data']
    old_batch=next(j for j in jobs if j['kind']=='batch')
    assert client.get('/admin/api/tencent/cost-jobs/'+old_batch['id']).json()['data']['scheduled_at']=='2026-12-03T05:30:00Z'
    now[0]=datetime(2027,1,3,7)
    assert scheduler.tick()==1
    def adjusted(credential,action,params):
        if action=='DescribeAccountBalance':return transport(credential,action,params)
        value=wire(params['BeginTime'][:7],single=True)
        if params['PageNo']>1:value['Response']['Detail']=[]
        return json.dumps(value).encode()
    newer=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),adjusted,now=lambda:now[0])
    drain(newer)
    assert client.get(base+'/cost-periods/2026-11').json()['data']['total']=='12.34567890'
    assert client.get(base+'/cost-periods/2026-10').json()['data']['total']=='12.00000000'


def test_missed_months_merge_into_one_batch_partial_failure_keeps_recent_months_usable(cost_http):
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    now=datetime(2027,3,3,5,30)
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    assert scheduler.tick()==1
    base=f"/admin/api/tencent/accounts/{account['id']}"
    batch=next(j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch')
    url='/admin/api/tencent/cost-jobs/'+batch['id']
    before=client.get(url).json()['data']
    assert [j['month'] for j in before['children']]==['2027-02','2027-01','2026-09','2026-10','2026-11','2026-12']
    def missing(credential,action,params):
        if action=='DescribeCostExplorerSummary' and params['BeginTime'].startswith('2026-09'):
            return b'{"Response":{"Error":{"Code":"UnauthorizedOperation"},"RequestId":"old-gap"}}'
        return transport(credential,action,params)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),missing,now=lambda:now)
    drain(worker)
    done=client.get(url).json()['data']
    assert done['status']=='partial_failed'
    assert done['attempts']==[]
    assert next(j for j in done['children'] if j['month']=='2026-09')['status']=='failed'
    assert client.get(base+'/cost-periods/2027-02').json()['data']['total']=='12.00000000'
    assert scheduler.tick()==0


@pytest.mark.parametrize('gate',['initialization','account','config'])
def test_current_gates_prevent_automatic_generation_and_claim(cost_http,gate):
    from app.persistence.models import DatasetState,TencentAccount,TencentSyncConfig
    from sqlalchemy import select
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    with sessions.begin() as db:
        if gate=='initialization':db.get(DatasetState,1).initialization_status='pending'
        if gate=='account':db.get(TencentAccount,int(account['id'])).is_enabled=False
        if gate=='config':db.scalar(select(TencentSyncConfig)).is_enabled=False
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:datetime(2026,12,3,5,30))
    assert scheduler.tick()==0
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport).claim() is None


def test_new_epoch_only_refills_real_gaps_and_never_rebinds_old_batches(cost_http):
    from app.persistence.models import DatasetState
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    now=[datetime(2026,12,3,5,30)]
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0])
    assert scheduler.tick()==1
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport,now=lambda:now[0])
    drain(worker)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    old_ids={j['id'] for j in client.get(base+'/cost-jobs').json()['data']}
    with sessions.begin() as db:db.get(DatasetState,1).dataset_epoch='new-epoch'
    assert scheduler.tick()==1
    new=[j for j in client.get(base+'/cost-jobs').json()['data'] if j['id'] not in old_ids]
    assert [j['month'] for j in new if j['kind']=='period']==['2026-10','2026-11']
    assert client.get(base+'/cost-periods/2026-09').json()['data']['coverage']['status']=='complete'
    drain(worker)


def test_two_scheduler_instances_race_on_independent_connections_and_create_one_event(cost_http):
    from concurrent.futures import ThreadPoolExecutor
    from app.tencent.cost_scheduler import TencentCostScheduler
    client,sessions,account=cost_http
    monthly(client,account)
    def run():return TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:datetime(2026,12,3,5,30)).tick()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
    assert sum(results)==1
    jobs=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs").json()['data']
    assert len([j for j in jobs if j['kind']=='batch'])==1

def test_unavailable_old_gap_is_visible_but_not_reenqueued_without_bound(cost_http):
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    now=[datetime(2027,3,3,5,30)]
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0])
    def unavailable(credential,action,params):
        if action=='DescribeCostExplorerSummary' and params['BeginTime'].startswith('2026-09'):
            return b'{"Response":{"Error":{"Code":"UnauthorizedOperation"},"RequestId":"gap"}}'
        return transport(credential,action,params)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),unavailable,now=lambda:now[0])
    for _ in range(3):
        assert scheduler.tick()==1
        drain(worker)
        now[0]=now[0].replace(month=now[0].month+1)
    assert scheduler.tick()==1
    batches=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs").json()['data']
    newest=next(j for j in batches if j['kind']=='batch')
    data=client.get('/admin/api/tencent/cost-jobs/'+newest['id']).json()['data']
    assert '2026-09' not in [j['month'] for j in data['children']]
    assert '2026-09' in data['deferred_months']
    assert data['blocked_months']==[{'month':'2026-09','reason_code':'TENCENT_MONTH_AUTO_BUDGET_EXHAUSTED'}]
    drain(worker)

def test_balance_rate_window_keeps_whole_second_facts_across_fractional_boundary(tencent_http,monkeypatch):
    from datetime import timezone
    from app.tencent import audit,balance
    client,sessions,_=tencent_http
    clock=[datetime.now(timezone.utc).replace(microsecond=100000)]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return clock[0].astimezone(tz)
    monkeypatch.setattr(audit,'now',lambda:clock[0].replace(tzinfo=None))
    monkeypatch.setattr(balance,'datetime',Clock)
    created=client.post('/admin/api/tencent/accounts',json={'uin':'10001','alias':'限频账号','credential_ref':'finance-a'})
    assert created.status_code==201
    url=f"/admin/api/tencent/accounts/{created.json()['data']['id']}/balance"
    # 合成金额仍经过真实 HTTP/gateway/audit；本测试只观察准入，业务正文无关。
    for _ in range(4):assert client.get(url).status_code==502
    clock[0]=clock[0].replace(microsecond=0)+timedelta(seconds=1,microseconds=50000)
    limited=client.get(url)
    assert limited.status_code==429
    assert limited.json()['error']['code']=='TENCENT_BALANCE_RATE_LIMITED'

def test_production_worker_loop_runs_month_scheduler_without_a_browser_session(cost_http):
    import threading
    from sqlalchemy import delete
    from app.persistence.models import AdminAllowlist
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    finished=threading.Event()
    def loop_wire(credential,action,params):
        result=transport(credential,action,params)
        if action=='DescribeCostExplorerSummary' and params['BeginTime'].startswith('2026-11') and params['PageNo']==2:finished.set()
        return result
    now=datetime(2026,12,3,5,30)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),loop_wire,now=lambda:now)
    with sessions.begin() as db:db.execute(delete(AdminAllowlist))
    stop=threading.Event()
    thread=threading.Thread(target=worker.run,args=(stop,),kwargs={'poll_seconds':0.01})
    thread.start()
    try:assert finished.wait(5)
    finally:
        stop.set();thread.join(5)
        with sessions.begin() as db:db.add(AdminAllowlist(open_id='tencent-admin',created_at=now))
    assert not thread.is_alive()
    drain(worker)
    jobs=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs").json()['data']
    batch=next(j for j in jobs if j['kind']=='batch')
    data=client.get('/admin/api/tencent/cost-jobs/'+batch['id']).json()['data']
    assert data['status']=='succeeded'
    child=client.get('/admin/api/tencent/cost-jobs/'+data['children'][0]['id']).json()['data']
    assert child['attempts'][0]['execution_input']['execution_identity']=='system-monthly'
    assert child['attempts'][0]['execution_input']['actor_id']=='system:tencent-monthly'


def test_long_outage_is_bounded_recent_first_and_keeps_deferred_gaps_visible(cost_http):
    from sqlalchemy import select
    from app.persistence.models import TencentSyncConfig
    from app.tencent.cost_scheduler import TencentCostScheduler
    client,sessions,account=cost_http
    monthly(client,account)
    with sessions.begin() as db:db.scalar(select(TencentSyncConfig)).schedule_start_month='2020-01'
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:datetime(2026,12,3,5,30))
    assert scheduler.tick()==1
    jobs=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs").json()['data']
    batch=next(j for j in jobs if j['kind']=='batch')
    data=client.get('/admin/api/tencent/cost-jobs/'+batch['id']).json()['data']
    assert len(data['children'])==14
    assert [j['month'] for j in data['children']][:2]==['2026-11','2026-10']
    assert len(data['deferred_months'])==69


def test_system_monthly_publish_rechecks_epoch_and_does_not_resurrect_old_jobs(cost_http):
    from app.persistence.models import DatasetState
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    now=datetime(2026,12,3,5,30)
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    assert scheduler.tick()==1
    base=f"/admin/api/tencent/accounts/{account['id']}"
    old=next(j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch')
    changed=[False]
    def reset_during_fetch(credential,action,params):
        if action=='DescribeCostExplorerSummary' and not changed[0]:
            changed[0]=True
            with sessions.begin() as db:db.get(DatasetState,1).dataset_epoch='reinitialized'
        return transport(credential,action,params)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),reset_during_fetch,now=lambda:now)
    assert worker.run_once()
    assert client.get(base+'/cost-periods/2026-11').status_code==404
    assert client.get('/admin/api/tencent/cost-jobs/'+old['id']).json()['data']['children'][0]['error_code']=='DATASET_CHANGED'
    assert scheduler.tick()==1
    for _ in range(3):worker.run_once()
    fresh=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport,now=lambda:now)
    drain(fresh)
    assert client.get(base+'/cost-periods/2026-11').status_code==200
    original=client.get('/admin/api/tencent/cost-jobs/'+old['id']).json()['data']
    assert original['status']=='failed'
    assert all(j['status']=='failed' for j in original['children'])


def test_manual_failed_batches_do_not_spend_automatic_old_gap_budget(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    monthly(client,account)
    now=datetime(2027,3,3,5,30)
    monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    def unavailable(credential,action,params):
        if action=='DescribeCostExplorerSummary' and params['BeginTime'].startswith('2026-09'):
            return b'{"Response":{"Error":{"Code":"UnauthorizedOperation"},"RequestId":"manual-gap"}}'
        return transport(credential,action,params)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),unavailable,now=lambda:now)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    for attempt in range(3):
        response=client.post(base+'/cost-batches',json={'idempotency_key':f'manual-gap-{attempt}'})
        assert response.status_code==202,response.text
        drain(worker)
        failed=client.get(response.headers['location']).json()['data']
        assert next(child for child in failed['children'] if child['month']=='2026-09')['status']=='failed'
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    assert scheduler.tick()==1
    newest=next(job for job in client.get(base+'/cost-jobs').json()['data'] if job['kind']=='batch')
    batch=client.get('/admin/api/tencent/cost-jobs/'+newest['id']).json()['data']
    assert '2026-09' in [child['month'] for child in batch['children']]
    assert batch['blocked_months']==[]
    drain(worker)
