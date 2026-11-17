"""T05 seam：管理端HTTP查询/导出 ← 实际worker写入的当前费用，真实隔离MySQL。"""
import json
import csv
import io

from app.main import app
from app.tencent.gateway import get_tencent_transport
from test_tencent_accounts_mysql import tencent_http
from test_tencent_cost_mysql import cost_http, enable_cost, run_job, wire


def test_dashboard_sums_local_current_months_without_cloud_requests_and_keeps_missing_null(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    assert run_job(client, sessions, account, 'august', month='2026-08')['status'] == 'succeeded'
    assert run_job(client, sessions, account, 'october', month='2026-10')['status'] == 'succeeded'
    def forbidden(*args):
        raise AssertionError('浏览本地看板不能调用腾讯云')
    app.dependency_overrides[get_tencent_transport] = lambda: forbidden
    response = client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-dashboard?start_month=2026-08&end_month=2026-11")
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['known_total'] == '24.00000000'
    assert data['complete_total'] is None
    assert data['currency'] == 'CNY'
    months = {row['month']: row for row in data['months']}
    assert months['2026-08']['status'] == 'complete'
    assert months['2026-08']['total'] == '12.00000000'
    assert months['2026-09']['total'] is None
    assert months['2026-09']['status'] == 'missing'
    assert months['2026-11']['status'] == 'not_due'
    assert len(data['products']) == 2
    assert data['products'][0]['amounts']['2026-09'] is None
    assert {row['total'] for row in data['products']} == {'24.69135780', '-0.69135780'}
    assert response.headers['cache-control'] == 'no-store'
    assert 'synthetic-key' not in response.text


def test_export_contains_all_products_and_neutralizes_untrusted_spreadsheet_formulas(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    def transport(credential, action, params):
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"export-identity"}}'
        result = wire()['Response']
        result['Total'] = 12
        result['TotalDetail']['Total'] = '12.00000000'
        result['TotalDetail']['TimeDetail'][0]['Money'] = '12.00000000'
        result['Detail'] = [{'Name': '=HYPERLINK("malicious")' if i == 0 else f'产品{i}',
            'Total': '1.00000000', 'TimeDetail': [{'Time': '2026-10-01 00:00:00', 'Money': '1.00000000'}]} for i in range(12)] if params['PageNo'] == 1 else []
        return json.dumps({'Response': result}).encode()
    assert run_job(client, sessions, account, 'full-export', transport=transport)['status'] == 'succeeded'
    response = client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-export?start_month=2026-10&end_month=2026-10")
    assert response.status_code == 200, response.text
    assert response.headers['content-type'].startswith('text/csv')
    assert response.headers['cache-control'] == 'no-store'
    rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert len(rows) == 12
    assert {row['产品名称'] for row in rows} >= {"'=HYPERLINK(\"malicious\")", '产品11'}
    assert {row['费用（元）'] for row in rows} == {'1.00000000'}
    assert {row['覆盖状态'] for row in rows} == {'完整月已覆盖'}


def test_unmapped_or_ambiguous_names_never_merge_across_months_or_imply_absence_elsewhere(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    def transport(credential, action, params):
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"ambiguous-identity"}}'
        month = params['BeginTime'][:7]
        result = wire(month)['Response']
        for row in result['Detail']: row['Name'] = '同名产品'
        result['ConditionValue'] = {'Business': [{'BusinessCode': 'a', 'BusinessCodeName': '同名产品'}, {'BusinessCode': 'b', 'BusinessCodeName': '同名产品'}]}
        if params['PageNo'] > 1: result['Detail'] = []
        return json.dumps({'Response': result}).encode()
    for month in ('2026-09', '2026-10'):
        assert run_job(client, sessions, account, month, month=month, transport=transport)['status'] == 'succeeded'
    response = client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-dashboard?start_month=2026-09&end_month=2026-10")
    assert response.status_code == 200
    products = response.json()['data']['products']
    assert len(products) == 4
    assert {row['mapping_status'] for row in products} == {'ambiguous'}
    assert all(sum(value is not None for value in row['amounts'].values()) == 1 for row in products)


def test_failed_refresh_retains_complete_values_but_does_not_claim_current_comparable_change(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    assert run_job(client, sessions, account, 'september', month='2026-09')['status'] == 'succeeded'
    assert run_job(client, sessions, account, 'october')['status'] == 'succeeded'
    def denied(credential, action, params):
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"failure-identity"}}'
        return b'{"Response":{"Error":{"Code":"UnauthorizedOperation","Message":"synthetic"},"RequestId":"denied"}}'
    assert run_job(client, sessions, account, 'failed-refresh', transport=denied)['status'] == 'failed'
    response = client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-dashboard?start_month=2026-09&end_month=2026-10")
    assert response.status_code == 200
    assert response.json()['data']['complete_total'] is None
    month = response.json()['data']['months'][-1]
    assert month['total'] == '12.00000000'
    assert month['status'] == 'failed_retained'
    assert month['mom'] == {'value': None, 'reason': 'latest_collection_failed'}


def test_confirmed_zero_and_missing_month_stay_distinct_in_dashboard_export_and_comparison(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    def zero(credential, action, params):
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"zero-identity"}}'
        if action == 'DescribeBillSummaryByProduct':
            return b'{"Response":{"Ready":1,"SummaryTotal":{"RealTotalCost":"0.00000000"},"SummaryOverview":[],"RequestId":"ready-zero"}}'
        result = wire('2026-08')['Response']
        result['Total'] = 0
        result['Detail'] = []
        result['TotalDetail']['Total'] = '0.00000000'
        result['TotalDetail']['TimeDetail'][0]['Money'] = '0.00000000'
        return json.dumps({'Response': result}).encode()
    assert run_job(client, sessions, account, 'zero-august', month='2026-08', transport=zero)['status'] == 'succeeded'
    assert run_job(client, sessions, account, 'nonzero-september', month='2026-09')['status'] == 'succeeded'
    path = f"/admin/api/tencent/accounts/{account['id']}"
    data = client.get(path + '/cost-dashboard?start_month=2026-08&end_month=2026-10').json()['data']
    assert data['months'][0]['total'] == '0.00000000'
    assert data['months'][1]['mom'] == {'value': None, 'reason': 'zero_denominator'}
    assert data['months'][2]['total'] is None
    response = client.get(path + '/cost-export?start_month=2026-08&end_month=2026-10')
    rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    august = [row for row in rows if row['账月'] == '2026-08']
    october = [row for row in rows if row['账月'] == '2026-10']
    assert august and {row['费用（元）'] for row in august} == {'0.00000000'}
    assert len(october) == 1 and october[0]['费用（元）'] == ''
    assert october[0]['覆盖状态'] == '未同步 / 缺口'


import pytest
from sqlalchemy import delete, select
from app.persistence.models import AdminAllowlist, DatasetState, TencentApiCall, TencentAccount


@pytest.mark.parametrize('endpoint,action', [('cost-dashboard','tencent.cost.read'),('cost-export','tencent.cost.export')])
def test_dashboard_and_export_enforce_gates_and_audit_trusted_target(cost_http, endpoint, action):
    client, sessions, account = cost_http
    path = f"/admin/api/tencent/accounts/{account['id']}/{endpoint}?start_month=2026-10&end_month=2026-10"
    response = client.get(path)
    assert response.status_code == 200
    with sessions() as db:
        audit = db.scalar(select(TencentApiCall).where(TencentApiCall.request_id == response.headers['x-request-id']))
        assert audit.action == action and audit.permission_code == action
        assert audit.target_id == '10001' and audit.actor_id == 'tencent-admin'
        assert audit.status_code == 200 and audit.outcome == 'succeeded'
    with sessions.begin() as db:
        db.get(DatasetState, 1).initialization_status = 'pending'
    assert client.get(path).json()['error']['code'] == 'INITIALIZATION_INCOMPLETE'
    with sessions.begin() as db:
        db.get(DatasetState, 1).initialization_status = 'complete'
        db.execute(delete(AdminAllowlist))
    assert client.get(path).status_code == 401
    client.cookies.clear()
    assert client.get(path).status_code == 401
    client.headers['Authorization'] = 'Bearer machine.synthetic'
    response = client.get(path)
    assert response.status_code == 401 and response.headers['cache-control'] == 'no-store'


def test_dashboard_comparison_currency_account_and_range_filters(cost_http):
    client, sessions, account = cost_http
    enable_cost(client, account)
    def scaled(credential, action, params):
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"scaled-identity"}}'
        result = wire(params['BeginTime'][:7])['Response']
        if params['BeginTime'][:7] == '2026-10':
            result['TotalDetail']['Total'] = '18.00000000'
            result['TotalDetail']['TimeDetail'][0]['Money'] = '18.00000000'
            result['Detail'][0]['Total'] = '18.34567890'
            result['Detail'][0]['TimeDetail'][0]['Money'] = '18.34567890'
        if params['PageNo'] > 1: result['Detail'] = []
        return json.dumps({'Response': result}).encode()
    for month in ('2025-10','2026-09','2026-10'):
        assert run_job(client, sessions, account, month, month=month, transport=scaled)['status'] == 'succeeded'
    base = f"/admin/api/tencent/accounts/{account['id']}/cost-dashboard"
    params = '?start_month=2026-10&end_month=2026-10'
    data = client.get(base + params).json()['data']
    assert data['known_total'] == data['complete_total'] == '18.00000000'
    assert data['months'][0]['mom'] == data['months'][0]['yoy'] == {'value':'50.000000','reason':None}
    other = client.get(base + params + '&currency=USD').json()['data']
    assert other['known_total'] == '0.00000000' and other['complete_total'] is None
    assert other['products'] == [] and other['months'][0]['total'] is None
    assert client.get(base.replace(str(account['id']), '999999') + params).status_code == 404
    with sessions.begin() as db:
        db.get(TencentAccount, int(account['id'])).is_enabled = False
    assert client.get(base + params).json()['data']['complete_total'] == '18.00000000'
    for query in ('?start_month=2026-11&end_month=2026-10', '?start_month=2026-10&end_month=9999-01',
        '?start_month=1969-12&end_month=2026-10', '?start_month=1970-01&end_month=2026-10', params+'&extra=true'):
        assert client.get(base + query).status_code == 422


def test_query_keeps_total_and_all_products_from_one_mysql_snapshot_during_replacement(cost_http):
    from threading import Event
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import event
    client, sessions, account = cost_http
    enable_cost(client, account)
    assert run_job(client, sessions, account, 'old')['status'] == 'succeeded'
    paused, replaced = Event(), Event()
    engine = sessions.kw['bind']
    def barrier(connection, cursor, statement, parameters, context, many):
        if ('FROM tencent_cost_period' in statement and 'JOIN' not in statement and not paused.is_set()):
            paused.set()
            assert replaced.wait(10), '并发替换未完成'
    def read():
        return client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-dashboard?start_month=2026-10&end_month=2026-10")
    def replacement(credential, action, params):
        if action == 'DescribeAccountBalance':
            return b'{"Response":{"Uin":10001,"RequestId":"replacement-identity"}}'
        result = wire(single=True)
        if params['PageNo'] > 1: result['Response']['Detail'] = []
        return json.dumps(result).encode()
    event.listen(engine, 'after_cursor_execute', barrier)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(read)
            assert paused.wait(5), '查询未到达期间读取屏障'
            try:
                assert run_job(client, sessions, account, 'new', transport=replacement)['status'] == 'succeeded'
            finally:
                replaced.set()
            response = pending.result(timeout=10)
    finally:
        event.remove(engine, 'after_cursor_execute', barrier)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['known_total'] == '12.00000000' and len(data['products']) == 2
    latest = client.get(f"/admin/api/tencent/accounts/{account['id']}/cost-dashboard?start_month=2026-10&end_month=2026-10").json()['data']
    assert latest['known_total'] == '12.34567890' and len(latest['products']) == 1


def test_committed_complete_costs_remain_comparable_after_organization_epoch_changes(cost_http):
    from app.persistence.models import TencentSyncJob, TencentCostPeriod
    client, sessions, account = cost_http
    enable_cost(client, account)
    jobs = [run_job(client, sessions, account, 'retained-' + month, month=month)
        for month in ('2025-10', '2026-09', '2026-10')]
    assert all(job['status'] == 'succeeded' for job in jobs)
    base = f"/admin/api/tencent/accounts/{account['id']}"
    query = '?start_month=2026-09&end_month=2026-10'
    before = client.get(base + '/cost-dashboard' + query).json()['data']
    assert before['complete_total'] == '24.00000000'
    assert before['months'][-1]['mom'] == before['months'][-1]['yoy'] == {'value':'0.000000','reason':None}
    with sessions.begin() as db:
        state = db.get(DatasetState, 1)
        old_epoch = state.dataset_epoch
        state.dataset_epoch = 'organization-reinitialized'
        state.initialization_status = 'pending'
    # 初始化仍是当前请求门槛；保留费用并不绕过门禁。
    for endpoint in ('cost-dashboard', 'cost-export'):
        response = client.get(base + '/' + endpoint + query)
        assert response.status_code == 409
        assert response.json()['error']['code'] == 'INITIALIZATION_INCOMPLETE'
    with sessions.begin() as db:
        db.get(DatasetState, 1).initialization_status = 'complete'
    def no_cloud(*args):
        raise AssertionError('重开组织初始化后读取已提交费用不能触发云端重采')
    app.dependency_overrides[get_tencent_transport] = lambda: no_cloud
    response = client.get(base + '/cost-dashboard' + query)
    assert response.status_code == 200, response.text
    after = response.json()['data']
    assert after == before
    assert after['coverage_complete'] is True
    assert {month['status'] for month in after['months']} == {'complete'}
    exported = client.get(base + '/cost-export' + query)
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert len(rows) == 4 and {row['覆盖状态'] for row in rows} == {'完整月已覆盖'}
    with sessions() as db:
        assert db.query(TencentCostPeriod).count() == 3
        assert {db.get(TencentSyncJob, int(job['id'])).snapshot['dataset_epoch'] for job in jobs} == {old_epoch}
