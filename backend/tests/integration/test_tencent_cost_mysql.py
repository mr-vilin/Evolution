"""已确认 seam：管理端 HTTP → 云 worker → 独立 MySQL，仅模拟腾讯云出站。"""
import json
from pathlib import Path

import pytest
from app.main import app
from app.tencent.gateway import get_tencent_transport
from test_tencent_accounts_mysql import tencent_http


@pytest.fixture
def cost_http(tencent_http):
    client, sessions, calls = tencent_http
    account = client.post('/admin/api/tencent/accounts', json={
        'uin': '10001', 'alias': '成本测试账号', 'credential_ref': 'finance-a',
    }).json()['data']
    yield client, sessions, account


def test_admin_submits_complete_month_then_worker_publishes_all_products(cost_http):
    client, sessions, account = cost_http
    path = f"/admin/api/tencent/accounts/{account['id']}/cost-config"
    config = client.get(path)
    assert config.status_code == 200
    assert config.json()['data']['is_enabled'] is False
    enabled = client.put(path, json={'revision': 0, 'is_enabled': True, 'frequency': 'manual', 'currency': 'CNY'})
    assert enabled.status_code == 200, enabled.text
    accepted = client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs", json={'month': '2026-10', 'idempotency_key': 'happy-month'})
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()['data']['id']
    assert accepted.json()['data']['status'] == 'pending'
    assert client.get(f'/admin/api/tencent/cost-jobs/{job_id}').json()['data']['attempts'] == []

    fixture_root = Path(__file__).parents[1] / 'fixtures' / 'tencent-cost'
    def transport(credential, action, params):
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"identity-current"}}'
        response = json.loads((fixture_root / 'monthly-page-1.json').read_text(encoding='utf-8'))
        # Both products fit a production-size page; the fixture still uses the official shape.
        if params['PageSize'] == 100:
            response['Response']['Detail'].extend(json.loads((fixture_root / 'monthly-page-2.json').read_text(encoding='utf-8'))['Response']['Detail'])
        if params['PageNo'] > 1: response['Response']['Detail'] = []
        return json.dumps(response).encode()
    app.dependency_overrides[get_tencent_transport] = lambda: transport
    from app.tencent.cost_worker import TencentCostWorker
    from app.config import get_settings
    worker = TencentCostWorker(sessions, app.dependency_overrides[get_settings](), transport)
    assert worker.run_once() is True
    result = client.get(f'/admin/api/tencent/cost-jobs/{job_id}').json()['data']
    assert result['status'] == 'succeeded'
    assert result['attempts'][0]['execution_input']['month'] == '2026-10'
    assert result['attempts'][0]['execution_output']['row_count'] == 2
    period = client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-periods/2026-10").json()['data']
    assert period['total'] == '12.00000000'
    assert period['currency'] == 'CNY'
    assert [row['amount'] for row in period['items']] == ['12.34567890', '-0.34567890']
    assert [row['business_code'] for row in period['items']] == ['p_synthetic_a', 'p_synthetic_b']


def enable_cost(client, account):
    path = f"/admin/api/tencent/accounts/{account['id']}/cost-config"
    response = client.put(path, json={'revision':0,'is_enabled':True,'frequency':'manual','currency':'CNY'})
    assert response.status_code == 200, response.text


def wire(month='2026-10', *, single=False, mode=None):
    root = Path(__file__).parents[1] / 'fixtures' / 'tencent-cost'
    response = json.loads((root/'monthly-page-1.json').read_text(encoding='utf-8'))['Response']
    if single:
        response['Total'] = 1
        response['TotalDetail']['Total'] = '12.34567890'
        response['TotalDetail']['TimeDetail'][0]['Money'] = '12.34567890'
    else:
        response['Detail'].extend(json.loads((root/'monthly-page-2.json').read_text(encoding='utf-8'))['Response']['Detail'])
    response = json.loads(json.dumps(response).replace('2026-10',month))
    if mode: mode(response)
    return {'Response':response}


def run_job(client, sessions, account, key, *, month='2026-10', transport=None):
    from app.tencent.cost_worker import TencentCostWorker
    from app.config import get_settings
    accepted = client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs",json={'month':month,'idempotency_key':key})
    assert accepted.status_code==202, accepted.text
    def default_transport(credential,action,params):
        if action=='DescribeAccountBalance': return b'{"Response":{"Uin":10001,"RequestId":"identity-now"}}'
        value = wire(month)
        if params['PageNo'] > 1: value['Response']['Detail'] = []
        return json.dumps(value).encode()
    worker = TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport or default_transport)
    assert worker.run_once() is True
    return client.get(accepted.headers['location']).json()['data']


def test_recollection_replaces_disappeared_products_and_preserves_other_month_and_receipt(cost_http):
    client,sessions,account=cost_http
    enable_cost(client,account)
    first=run_job(client,sessions,account,'first')
    assert first['status']=='succeeded'
    other=run_job(client,sessions,account,'other',month='2026-09')
    assert other['status']=='succeeded'
    def transport(credential,action,params):
        if action=='DescribeAccountBalance': return b'{"Response":{"Uin":10001,"RequestId":"identity-now"}}'
        value = wire(single=True)
        if params['PageNo'] > 1: value['Response']['Detail'] = []
        return json.dumps(value).encode()
    second=run_job(client,sessions,account,'replacement',transport=transport)
    assert second['status']=='succeeded'
    path=f"/admin/api/tencent/accounts/{account['id']}/cost-periods/"
    current=client.get(path+'2026-10').json()['data']
    assert current['total']=='12.34567890'
    assert len(current['items'])==1
    assert current['latest_job_id']==second['id']
    assert client.get(path+'2026-09').json()['data']['total']=='12.00000000'
    # Historical receipt remains the actual old commit result, not current config/period reconstruction.
    history=client.get('/admin/api/tencent/cost-jobs/'+first['id']).json()['data']
    assert history['attempts'][0]['execution_output']['row_count']==2
    duplicate=client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs",json={'month':'2026-10','idempotency_key':'replacement'})
    assert duplicate.json()['data']['id']==second['id']
    conflict=client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs",json={'month':'2026-09','idempotency_key':'replacement'})
    assert conflict.status_code==409


def test_source_rows_after_declared_total_do_not_replace_old_complete_month(cost_http):
    client,sessions,account=cost_http
    enable_cost(client,account)
    assert run_job(client,sessions,account,'old')['status']=='succeeded'
    def transport(credential,action,params):
        if action=='DescribeAccountBalance': return b'{"Response":{"Uin":10001,"RequestId":"identity-now"}}'
        # Replaying a populated page after Total rows must not silently succeed.
        return json.dumps(wire(single=True)).encode()
    result=run_job(client,sessions,account,'extra',transport=transport)
    assert result['status']=='failed'
    assert result['attempts'][0]['error_code']=='TENCENT_COST_EXCESS_ROWS'
    current=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-periods/2026-10").json()['data']
    assert current['total']=='12.00000000'
    assert len(current['items'])==2


@pytest.mark.parametrize('fault,expected', [
    ('early-empty','TENCENT_COST_EARLY_EMPTY'), ('changed-count','TENCENT_COST_SOURCE_CHANGED'),
    ('repeated-page','TENCENT_COST_REPEATED_PAGE'), ('total-mismatch','TENCENT_COST_TOTAL_MISMATCH'),
    ('precision','TENCENT_COST_AMOUNT_INVALID'), ('overflow','TENCENT_COST_AMOUNT_INVALID'),
    ('wrong-boundary','TENCENT_COST_BOUNDARY_INVALID'), ('null-detail','TENCENT_COST_EARLY_EMPTY'),
    ('permission','TENCENT_PERMISSION_DENIED'), ('uin','TENCENT_ACCOUNT_MISMATCH'),
])
def test_incomplete_or_untrusted_collection_preserves_old_cost_and_failure_evidence(cost_http,fault,expected):
    client,sessions,account=cost_http
    enable_cost(client,account)
    assert run_job(client,sessions,account,'old')['status']=='succeeded'
    def transport(credential,action,params):
        if action=='DescribeAccountBalance':
            return json.dumps({'Response':{'Uin':20002 if fault=='uin' else 10001,'RequestId':'identity-current'}}).encode()
        if fault=='permission': return b'{"Response":{"Error":{"Code":"UnauthorizedOperation","Message":"synthetic"},"RequestId":"denied"}}'
        value=wire()['Response']
        number=params['PageNo']
        if fault in {'early-empty','changed-count','repeated-page'}:
            value['Total']=200 if fault=='repeated-page' else 101
            value['TotalDetail']['Total']=str(value['Total'])
            value['TotalDetail']['TimeDetail'][0]['Money']=str(value['Total'])
            value['Detail']=[{'Name':f'row-{i}','Total':'1.00000000','TimeDetail':[{'Time':'2026-10-01 00:00:00','Money':'1.00000000'}]} for i in range(100 if number==1 or fault=='repeated-page' else 1)]
            if number==2 and fault=='early-empty': value['Detail']=[]
            if number==2 and fault=='changed-count': value['Total']=102
        else:
            if number>1: value['Detail']=[]
            if fault=='total-mismatch':
                value['TotalDetail']['Total']='13.00000000'
                value['TotalDetail']['TimeDetail'][0]['Money']='13.00000000'
            if fault in {'precision','overflow'} and value['Detail']:
                value['Detail'][0]['Total']='12.345678901' if fault=='precision' else '10000000000000000.00000000'
            if fault=='wrong-boundary': value['Header']['HeadDetail'][0]['Name']='2026-09-01 00:00:00'
            if fault=='null-detail': value['Detail']=None
        return json.dumps({'Response':value}).encode()
    result=run_job(client,sessions,account,'broken',transport=transport)
    assert result['status']=='failed'
    assert result['attempts'][0]['error_code']==expected
    assert result['attempts'][0]['execution_input']['month']=='2026-10'
    assert result['attempts'][0]['execution_output'] is None
    current=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-periods/2026-10").json()['data']
    assert current['total']=='12.00000000'
    assert len(current['items'])==2
    assert 'synthetic-key' not in json.dumps(result)


@pytest.mark.parametrize('ready', [0,1])
def test_empty_month_only_clears_old_cost_with_same_month_ready_zero_evidence(cost_http,ready):
    client,sessions,account=cost_http
    enable_cost(client,account)
    assert run_job(client,sessions,account,'old')['status']=='succeeded'
    def transport(credential,action,params):
        if action=='DescribeAccountBalance': return b'{"Response":{"Uin":10001,"RequestId":"identity-now"}}'
        if action=='DescribeBillSummaryByProduct':
            assert params=={'BeginTime':'2026-10','EndTime':'2026-10'}
            return json.dumps({'Response':{'Ready':ready,'SummaryTotal':{'RealTotalCost':'0.00000000'},'SummaryOverview':[],'RequestId':'zero-proof'}}).encode()
        value=wire()['Response'];value['Total']=0;value['Detail']=[]
        value['TotalDetail']['Total']='0.00000000';value['TotalDetail']['TimeDetail'][0]['Money']='0.00000000'
        return json.dumps({'Response':value}).encode()
    result=run_job(client,sessions,account,'zero',transport=transport)
    current=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-periods/2026-10").json()['data']
    if ready:
        assert result['status']=='succeeded'
        assert current['total']=='0.00000000'
        assert current['items']==[]
        assert current['coverage']['zero_evidence']=='same-month-ready-product-summary-zero'
    else:
        assert result['status']=='failed'
        assert result['error_code']=='TENCENT_COST_NOT_READY'
        assert current['total']=='12.00000000'
        assert len(current['items'])==2


@pytest.mark.parametrize('change,expected', [
    ('epoch','DATASET_CHANGED'),('account','TENCENT_ACCOUNT_UNAVAILABLE'),
    ('credential','TENCENT_CREDENTIAL_CHANGED'),('config','TENCENT_COST_CONFIG_CHANGED'),
    ('actor','TENCENT_ACTOR_REVOKED'),('initialization','INITIALIZATION_INCOMPLETE'),
    ('version',None),
])
def test_current_qualification_is_rechecked_after_external_calls_without_using_org_data_version(cost_http,change,expected):
    from sqlalchemy import delete
    from app.persistence.models import DatasetState,TencentAccount,TencentSyncConfig,AdminAllowlist
    from app.tencent.cost_worker import TencentCostWorker
    from app.config import get_settings
    client,sessions,account=cost_http
    enable_cost(client,account)
    assert run_job(client,sessions,account,'old')['status']=='succeeded'
    accepted=client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs",json={'month':'2026-10','idempotency_key':'gate'})
    changed=False
    def transport(credential,action,params):
        nonlocal changed
        if action=='DescribeAccountBalance': return b'{"Response":{"Uin":10001,"RequestId":"identity-now"}}'
        if not changed:
            changed=True
            with sessions.begin() as db:
                if change=='epoch':db.get(DatasetState,1).dataset_epoch='new-epoch'
                if change=='version':db.get(DatasetState,1).data_version+=1
                if change=='initialization':db.get(DatasetState,1).initialization_status='pending'
                if change=='account':db.get(TencentAccount,int(account['id'])).is_enabled=False
                if change=='credential':db.get(TencentAccount,int(account['id'])).credential_revision+=1
                if change=='config':db.query(TencentSyncConfig).filter_by(account_id=int(account['id'])).one().is_enabled=False
                if change=='actor':db.execute(delete(AdminAllowlist))
        value=wire(single=True)
        if params['PageNo']>1:value['Response']['Detail']=[]
        return json.dumps(value).encode()
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport)
    assert worker.run_once()
    # Restore only test control plane so the original HTTP result boundary can observe the receipt.
    with sessions.begin() as db:
        db.get(DatasetState,1).initialization_status='complete'
        if change=='actor':db.add(AdminAllowlist(open_id='tencent-admin',created_at=worker.now()))
    result=client.get(accepted.headers['location']).json()['data']
    current=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-periods/2026-10").json()['data']
    if expected:
        assert result['status']=='failed'
        assert result['error_code']==expected
        assert current['total']=='12.00000000'
    else:
        assert result['status']=='succeeded'
        assert current['total']=='12.34567890'


def test_database_failure_during_replacement_rolls_back_products_total_and_success_receipt(cost_http):
    from sqlalchemy import event
    client,sessions,account=cost_http
    enable_cost(client,account)
    assert run_job(client,sessions,account,'old')['status']=='succeeded'
    engine=sessions.kw['bind'];injected=False
    def fault(connection,cursor,statement,parameters,context,executemany):
        nonlocal injected
        if not injected and statement.startswith('INSERT INTO tencent_cost_item'):
            injected=True
            raise RuntimeError('synthetic-storage-failure')
    event.listen(engine,'before_cursor_execute',fault)
    try:result=run_job(client,sessions,account,'rollback')
    finally:event.remove(engine,'before_cursor_execute',fault)
    assert injected
    assert result['status']=='failed'
    assert result['attempts'][0]['execution_output'] is None
    current=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-periods/2026-10").json()['data']
    assert current['total']=='12.00000000'
    assert len(current['items'])==2
    assert current['latest_job_id']!=result['id']


def test_same_configuration_is_serial_and_expired_execution_cannot_publish(cost_http):
    from datetime import timedelta
    from app.tencent.cost_worker import TencentCostWorker
    from app.config import get_settings
    client,sessions,account=cost_http
    enable_cost(client,account)
    urls=[]
    for key in ('first','second'):
        accepted=client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs",json={'month':'2026-10','idempotency_key':key})
        assert accepted.status_code==202
        urls.append(accepted.headers['location'])
    current=[None]
    def transport(credential,action,params):
        if action=='DescribeAccountBalance': return b'{"Response":{"Uin":10001,"RequestId":"identity-now"}}'
        value=wire()
        if params['PageNo']>1:value['Response']['Detail']=[]
        return json.dumps(value).encode()
    worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport)
    current[0]=worker.now()
    worker.now=lambda:current[0]
    claim=worker.claim()
    second=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport)
    assert second.claim() is None
    assert client.get(urls[0]).json()['data']['status']=='running'
    current[0]+=timedelta(seconds=121)
    assert worker.execute(claim) is None
    assert client.get(urls[0]).json()['data']['error_code']=='TENCENT_COST_STALE_EXECUTION'
    assert client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-periods/2026-10").status_code==404
    assert second.run_once()
    assert client.get(urls[1]).json()['data']['status']=='succeeded'


def test_complete_pagination_keeps_all_unmapped_same_name_rows(cost_http):
    client,sessions,account=cost_http
    enable_cost(client,account)
    def transport(credential,action,params):
        if action=='DescribeAccountBalance': return b'{"Response":{"Uin":10001,"RequestId":"identity-now"}}'
        value=wire()['Response'];value['Total']=101
        value['TotalDetail']['Total']='101.00000000';value['TotalDetail']['TimeDetail'][0]['Money']='101.00000000'
        n=params['PageNo']
        value['Detail']=[{'Name':'同名产品' if i<2 and n==1 else f'{n}-{i}','Total':'1.00000000','TimeDetail':[{'Time':'2026-10-01 00:00:00','Money':'1.00000000'}]} for i in range(100 if n==1 else 1 if n==2 else 0)]
        return json.dumps({'Response':value}).encode()
    result=run_job(client,sessions,account,'many',transport=transport)
    assert result['status']=='succeeded'
    current=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-periods/2026-10").json()['data']
    assert current['total']=='101.00000000'
    assert len(current['items'])==101
    assert current['items'][0]['source_name']==current['items'][1]['source_name']=='同名产品'
    assert current['items'][0]['id']!=current['items'][1]['id']
    assert current['items'][0]['business_code'] is None
    assert current['items'][0]['mapping_status']=='ambiguous'


@pytest.mark.parametrize('day,latest,rejected',[(1,'2026-09','2026-10'),(2,'2026-09','2026-10'),(3,'2026-10','2026-11')])
def test_shanghai_month_sync_day_is_enforced_by_http(cost_http,monkeypatch,day,latest,rejected):
    from datetime import datetime,timezone
    from app.tencent import cost_router
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,11,day,0,0,tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(cost_router,'datetime',Clock)
    client,sessions,account=cost_http
    enable_cost(client,account)
    config=client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-config").json()['data']
    assert config['latest_eligible_month']==latest
    result=client.post(f"/admin/api/tencent/accounts/{account['id']}/cost-jobs",json={'month':rejected,'idempotency_key':'early'})
    assert result.status_code==422
    assert result.json()['error']['code']=='TENCENT_MONTH_NOT_ELIGIBLE'


def test_independent_configuration_can_complete_while_another_configuration_is_owned(cost_http):
    from app.config import get_settings
    from app.tencent.cost_worker import TencentCostWorker
    client,sessions,account=cost_http
    enable_cost(client,account)
    app.dependency_overrides[get_tencent_transport]=lambda:lambda *_:b'{"Response":{"Uin":20002,"RequestId":"second-account"}}'
    second=client.post('/admin/api/tencent/accounts',json={'uin':'20002','alias':'第二账号','credential_ref':'finance-b'}).json()['data']
    enable_cost(client,second)
    for current,key in ((account,'a1'),(account,'a2'),(second,'b1')):
        assert client.post(f"/admin/api/tencent/accounts/{current['id']}/cost-jobs",json={'month':'2026-10','idempotency_key':key}).status_code==202
    def transport(credential,action,params):
        if action=='DescribeAccountBalance':
            return json.dumps({'Response':{'Uin':20002 if credential.secret_id.get_secret_value().endswith('-b') else 10001,'RequestId':'identity'}}).encode()
        value=wire()
        if params['PageNo']>1:value['Response']['Detail']=[]
        return json.dumps(value).encode()
    first_worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport)
    other_worker=TencentCostWorker(sessions,app.dependency_overrides[get_settings](),transport)
    first_claim=first_worker.claim()
    try:
        assert other_worker.run_once()
        assert client.get(f"/admin/api/tencent/accounts/{second['id']}/cost-periods/2026-10").json()['data']['total']=='12.00000000'
        assert client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-periods/2026-10").status_code==404
    finally:
        first_worker.execute(first_claim)
    assert first_worker.run_once()


def test_actual_cost_schema_has_chinese_comments_precise_amounts_and_no_physical_foreign_keys(cost_http):
    from sqlalchemy import inspect,text
    client,sessions,account=cost_http
    with sessions() as db:
        schema=inspect(db.bind)
        from app.persistence.schema_check import check_schema
        errors=check_schema(db.bind)['errors']
        assert not [value for value in errors if value.startswith('tencent_')], errors
        for name in ('tencent_sync_config','tencent_sync_job','tencent_sync_attempt','tencent_cost_period','tencent_cost_item'):
            assert schema.get_foreign_keys(name)==[]
            columns=schema.get_columns(name)
            assert all(column['comment'] and any('\u4e00'<=char<='\u9fff' for char in column['comment']) for column in columns)
            id_column=next(c for c in columns if c['name']=='id')
            assert str(id_column['type'])=='INTEGER' and not id_column['type'].unsigned
            table=db.execute(text('SELECT ENGINE,TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:name'),{'name':name}).one()
            assert table==('InnoDB','utf8mb4_general_ci')
        for name,column_name in (('tencent_cost_period','total'),('tencent_cost_item','amount')):
            col=next(c for c in schema.get_columns(name) if c['name']==column_name)
            assert (col['type'].precision,col['type'].scale)==(24,8)
