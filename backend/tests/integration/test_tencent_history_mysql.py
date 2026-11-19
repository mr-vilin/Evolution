"""管理端 HTTP / 实际 scheduler、worker / 独立 MySQL 的历史回溯行为。"""
from datetime import datetime
from app.config import get_settings
from app.main import app
from test_tencent_accounts_mysql import tencent_http
from test_tencent_cost_mysql import cost_http
from test_tencent_daily_mysql import daily_transport
from test_tencent_monthly_mysql import monthly, drain


def test_existing_configuration_discovers_bounded_history_without_claiming_account_origin(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    before=client.get(base+'/cost-history')
    assert before.status_code==200,before.text
    history=before.json()['data']
    assert history['origin_status']=='unknown' and history['first_bill_period'] is None
    assert history['earlier_history_unknown'] is True
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    assert scheduler.tick()==1
    drain(worker)
    assert scheduler.tick()==1
    drain(worker)
    assert scheduler.tick()==0
    done=client.get(base+'/cost-history').json()['data']
    assert done['covered_period_count']==12 and done['discovery_status']=='known_window_probed'
    assert done['origin_status']=='unknown' and done['earlier_history_unknown'] is True
    assert done['earliest_success_period']=='2025-11'
    assert done['continuous_coverage']=={'begin':'2025-11-01','end_exclusive':'2026-11-01'}


def test_manual_range_preview_expands_existing_month_and_replays_original_intent(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='daily')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    assert client.post(base+'/cost-jobs',json={'month':'2026-02','idempotency_key':'old-month'}).status_code==202
    assert worker.run_once()
    request={'scope':'range','start_date':'2026-02-14','end_date':'2026-03-05','idempotency_key':'range'}
    preview=client.post(base+'/cost-range-preview',json=request)
    assert preview.status_code==200,preview.text
    view=preview.json()['data']
    assert view['expanded'] is True
    assert [(p['period_key'],p['granularity']) for p in view['periods']]==[('2026-03','month'),('2026-02','month')]
    assert view['periods'][1]['begin']=='2026-02-01T00:00:00+08:00'
    accepted=client.post(base+'/cost-range-batches',json={**request,'preview_token':view['preview_token']})
    assert accepted.status_code==202,accepted.text
    drain(worker)
    detail=client.get(accepted.headers['location']).json()['data']
    assert detail['status']=='succeeded' and detail['attempts']==[]
    assert all(c['granularity']=='month' for c in detail['children'])
    monthly(client,account,frequency='monthly')
    duplicate=client.post(base+'/cost-range-batches',json=request)
    assert duplicate.status_code==202 and duplicate.json()['data']['id']==detail['id']
    assert duplicate.json()['data']['periods']==detail['periods']
    assert client.post(base+'/cost-range-batches',json={**request,'end_date':'2026-03-06'}).status_code==409


def test_new_recent_batch_is_actually_claimed_ahead_of_older_history_backlog(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    from datetime import timedelta
    client,sessions,account=cost_http
    now=[datetime(2026,11,17,5,30)];monkeypatch.setattr(cost_router,'utcnow',lambda:now[0])
    monthly(client,account)
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0])
    seen=[]
    def observed(c,a,p):
        if a=='DescribeCostExplorerSummary':seen.append(p['BeginTime'][:7])
        return daily_transport(c,a,p)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),observed,now=lambda:now[0])
    scheduler.tick();drain(worker);scheduler.tick() # old history pending
    now[0]=datetime(2026,12,3,5,30)
    assert scheduler.tick()==1
    seen.clear();assert worker.run_once()
    assert seen[0]=='2026-11' # actual outbound, not insertion order
    drain(worker)


def test_outside_source_window_empty_ready_month_cannot_erase_prior_nonzero(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_worker import TencentCostWorker
    import json
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='manual')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    accepted=client.post(base+'/cost-jobs',json={'month':'2024-01','idempotency_key':'old-real'})
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now).run_once()
    def empty(c,a,p):
        if a=='DescribeBillSummaryByProduct':return b'{"Response":{"RequestId":"ready-empty","Ready":1,"SummaryOverview":[],"SummaryTotal":{"RealTotalCost":"0"}}}'
        value=json.loads(daily_transport(c,a,p))
        if a=='DescribeCostExplorerSummary':
            r=value['Response'];r['Total']=0;r['Detail']=[];r['TotalDetail']['Total']='0';r['TotalDetail']['TimeDetail'][0]['Money']='0'
        return json.dumps(value).encode()
    again=client.post(base+'/cost-jobs',json={'month':'2024-01','idempotency_key':'old-empty'})
    assert TencentCostWorker(sessions,app.dependency_overrides[get_settings](),empty,now=lambda:now).run_once()
    result=client.get(again.headers['location']).json()['data']
    assert result['status']=='failed' and result['error_code']=='TENCENT_COST_ZERO_UNCONFIRMED'
    assert client.get(base+'/cost-periods/2024-01').json()['data']['total']=='12.00000000'


def test_partial_failure_does_not_stop_earlier_discovery_or_bridge_continuous_coverage(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    def mixed(c,a,p):
        if a=='DescribeCostExplorerSummary' and p['BeginTime'].startswith('2026-07'):
            return b'{"Response":{"Error":{"Code":"UnauthorizedOperation"},"RequestId":"gap-denied"}}'
        return daily_transport(c,a,p)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),mixed,now=lambda:now)
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    for _ in range(5):scheduler.tick();drain(worker)
    view=client.get(base+'/cost-history').json()['data']
    assert view['earliest_success_period']=='2025-11'
    assert view['continuous_coverage']=={'begin':'2026-08-01','end_exclusive':'2026-11-01'}
    assert view['gaps'][0]['period_key']=='2026-07' and view['gaps'][0]['automatic_paused'] is True
    assert view['gaps'][0]['category']=='permission_denied'
    assert scheduler.tick()==0 and scheduler.tick()==0
    manual=client.post(base+'/cost-range-batches',json={'scope':'range','start_date':'2026-07-01','end_date':'2026-07-31','idempotency_key':'reprobe'})
    assert manual.status_code==202,manual.text
    drain(TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now))
    assert client.get(manual.headers['location']).json()['data']['scope_status']=='complete'
    assert client.get(base+'/cost-history').json()['data']['gaps']==[]


def test_range_all_continues_same_parent_in_manual_mode_and_partial_success_is_explicit(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    config=monthly(client,account,frequency='manual')
    monthly(client,account,frequency='manual',run_policy={**config['run_policy'],'queue_limit':6})
    base=f"/admin/api/tencent/accounts/{account['id']}"
    body={'scope':'all','idempotency_key':'all-small-queue'}
    preview=client.post(base+'/cost-range-preview',json=body).json()['data']
    assert preview['total_count']==12 and preview['accepted_count']==4
    accepted=client.post(base+'/cost-range-batches',json={**body,'preview_token':preview['preview_token']})
    assert accepted.status_code==202
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    drain(worker)
    partial=client.get(accepted.headers['location']).json()['data']
    assert partial['status']=='pending' and partial['scope_status']=='pending' and partial['deferred_periods']
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    assert scheduler.tick()==1
    drain(worker)
    assert scheduler.tick()==1
    drain(worker)
    finished=client.get(accepted.headers['location']).json()['data']
    assert finished['status']=='succeeded' and len(finished['children'])==12 and finished['attempts']==[]
    assert scheduler.tick()==0


def test_daily_history_continues_to_old_months_without_fabricating_daily_amounts(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account,frequency='daily')
    base=f"/admin/api/tencent/accounts/{account['id']}"
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    assert scheduler.tick()==1;drain(worker,200)
    for _ in range(8):
        if scheduler.tick()==0:break
        drain(worker,200)
    else:raise AssertionError('history did not finish within finite slices')
    done=client.get(base+'/cost-history').json()['data']
    assert done['origin_status']=='unknown' and done['unexplored']==[] and done['gaps']==[]
    old=client.get(base+'/cost-periods/2026-02').json()['data']
    assert old['granularity']=='month' and old['total']=='12.00000000'
    assert client.get(base+'/cost-periods/2026-02-01').status_code==404
    # 每天普通计划只复核近期；已成功历史不会全史重采。
    from datetime import timedelta
    now2=datetime(2026,11,18,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now2)
    assert TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now2).tick()==1
    newest=next(j for j in client.get(base+'/cost-jobs').json()['data'] if j['kind']=='batch')
    assert all(p['period_key']>='2026-10' for p in newest['periods'])
    drain(TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now2),200)


def test_auto_failure_budget_survives_epoch_and_manual_new_key_reopens_gap(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    from app.persistence.models import DatasetState
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account)
    base=f"/admin/api/tencent/accounts/{account['id']}";seen=[]
    def denied(c,a,p):
        if a=='DescribeCostExplorerSummary':
            seen.append(p['BeginTime'][:7])
            if p['BeginTime'].startswith('2026-07'):
                return b'{"Response":{"Error":{"Code":"UnauthorizedOperation"},"RequestId":"history-denied"}}'
        return daily_transport(c,a,p)
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),denied,now=lambda:now)
    for _ in range(6):
        if scheduler.tick()==0:break
        drain(worker,100)
    history=client.get(base+'/cost-history').json()['data']
    assert history['gaps'][0]['period_key']=='2026-07' and history['gaps'][0]['automatic_paused'] is True
    assert history['continuous_coverage']=={'begin':'2026-08-01','end_exclusive':'2026-11-01'}
    assert history['earliest_success_period']=='2025-11'
    with sessions.begin() as db:db.get(DatasetState,1).dataset_epoch='history-new-epoch'
    seen.clear();assert scheduler.tick()==1;drain(worker,100)
    assert set(seen)=={'2026-09','2026-10'} # success preserved, paused gap stays paused
    assert scheduler.tick()==0
    body={'scope':'range','start_date':'2026-07-01','end_date':'2026-07-31','idempotency_key':'explicit-reprobe'}
    accepted=client.post(base+'/cost-range-batches',json=body)
    assert accepted.status_code==202
    drain(TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now),100)
    assert client.get(accepted.headers['location']).json()['data']['status']=='succeeded'
    assert client.get(base+'/cost-history').json()['data']['gaps']==[]


def test_deferred_manual_children_keep_original_policy_frequency_and_source_window(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=[datetime(2026,11,17,5,30)];monkeypatch.setattr(cost_router,'utcnow',lambda:now[0])
    config=monthly(client,account,frequency='manual')
    monthly(client,account,frequency='manual',run_policy={**config['run_policy'],'queue_limit':6})
    base=f"/admin/api/tencent/accounts/{account['id']}"
    accepted=client.post(base+'/cost-range-batches',json={'scope':'all','idempotency_key':'frozen-all'})
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now[0])
    drain(worker)
    original=client.get(accepted.headers['location']).json()['data']
    first=client.get('/admin/api/tencent/cost-jobs/'+original['children'][0]['id']).json()['data']['attempts'][0]['execution_input']
    current=client.get(base+'/cost-config').json()['data']
    monthly(client,account,frequency='manual',run_policy={**current['run_policy'],'queue_limit':10,'max_attempts':2})
    now[0]=datetime(2026,11,18,5,30)
    assert TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0]).tick()==1
    drain(worker)
    later=client.get(accepted.headers['location']).json()['data']
    added=next(c for c in later['children'] if c['id'] not in {c['id'] for c in original['children']})
    actual=client.get('/admin/api/tencent/cost-jobs/'+added['id']).json()['data']['attempts'][0]['execution_input']
    for field in ('handler','config_revision','control_revision','credential_revision','frequency','policy','source_window'):
        assert actual[field]==first[field],field
    while TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now[0]).tick():drain(worker)


import pytest


@pytest.mark.parametrize('frequency,limit',[('manual',1),('monthly',2),('daily',10)])
def test_small_legal_queue_still_accepts_and_advances_history(cost_http,monkeypatch,frequency,limit):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    config=monthly(client,account,frequency=frequency)
    monthly(client,account,frequency=frequency,run_policy={**config['run_policy'],'queue_limit':limit})
    base=f"/admin/api/tencent/accounts/{account['id']}"
    body={'scope':'all','idempotency_key':'small-queue'}
    accepted=client.post(base+'/cost-range-batches',json=body)
    assert accepted.status_code==202,accepted.text
    assert 1<=len(accepted.json()['data']['periods'])<=limit
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),daily_transport,now=lambda:now)
    drain(worker,20)
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    assert scheduler.tick()==1
    drain(worker,20)
    assert scheduler.tick()==1
    drain(worker,20)
    current=client.get(accepted.headers['location']).json()['data']
    assert len(current['children'])>=2


def test_unready_first_empty_history_month_does_not_end_discovery(cost_http,monkeypatch):
    from app.tencent import cost_router
    from app.tencent.cost_scheduler import TencentCostScheduler
    from app.tencent.cost_worker import TencentCostWorker
    import json
    client,sessions,account=cost_http
    now=datetime(2026,11,17,5,30);monkeypatch.setattr(cost_router,'utcnow',lambda:now)
    monthly(client,account)
    base=f"/admin/api/tencent/accounts/{account['id']}"
    def empty_first(c,a,p):
        if a=='DescribeBillSummaryByProduct':return b'{"Response":{"RequestId":"not-ready-old","Ready":0,"SummaryOverview":[],"SummaryTotal":{"RealTotalCost":"0"}}}'
        value=json.loads(daily_transport(c,a,p))
        if a=='DescribeCostExplorerSummary' and p['BeginTime'].startswith('2026-08'):
            r=value['Response'];r['Total']=0;r['Detail']=[];r['TotalDetail']['Total']='0';r['TotalDetail']['TimeDetail'][0]['Money']='0'
        return json.dumps(value).encode()
    scheduler=TencentCostScheduler(sessions,app.dependency_overrides[get_settings](),now=lambda:now)
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),empty_first,now=lambda:now)
    scheduler.tick();drain(worker);scheduler.tick();drain(worker)
    history=client.get(base+'/cost-history').json()['data']
    assert history['earliest_success_period']=='2025-11'
    assert history['gaps'][0]['category']=='not_ready'
    assert history['continuous_coverage']=={'begin':'2026-09-01','end_exclusive':'2026-11-01'}
