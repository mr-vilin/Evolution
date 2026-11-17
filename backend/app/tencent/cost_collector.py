"""费用账单/总费用/产品维度的日/月完整期间采集；完整性不能降级为空零。"""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from datetime import datetime, timezone
import hashlib
import json
import time
from .errors import TencentError

CONTRACT = 'tencent-cost-month-v1'  # 仅兼容已受理月快照
PERIOD_CONTRACT = 'tencent-cost-period-v2'
MAX_ROWS = 10000
PAGE_SIZE = 100


def invalid(code='TENCENT_COST_INVALID'):
    raise TencentError(code, '费用结果不完整、未就绪或无法核验，已保留原完整费用', 502)


def money(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 80:
        invalid('TENCENT_COST_AMOUNT_INVALID')
    try:
        with localcontext() as ctx:
            ctx.prec = 64
            value = Decimal(raw)
            if not value.is_finite() or abs(value) >= Decimal('10000000000000000') or value != value.quantize(Decimal('.00000001')):
                invalid('TENCENT_COST_AMOUNT_INVALID')
            return value
    except InvalidOperation:
        invalid('TENCENT_COST_AMOUNT_INVALID')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(',', ':')).encode()).hexdigest()


def require_month_zero_window(snapshot, now):
    """零值证据依赖实际查询时仍可取的窗口；冻结快照不能延长源能力。"""
    from .cost_history import window
    if snapshot.get('month_zero_eligible') is False or snapshot['month'] < window(now)['month_start']:
        invalid('TENCENT_COST_ZERO_UNCONFIRMED')


def collect_period(gateway, credential, snapshot, *, clock=time.monotonic, check=None, now=None):
    """有界单次完整采集。成功只返回内存候选，发布另有当前资格事务。"""
    current = now or (lambda: datetime.now(timezone.utc))
    started = clock()
    policy=snapshot.get('policy') or {}
    deadline=policy.get('deadline_seconds',90)
    max_rows=policy.get('max_rows',MAX_ROWS)
    request_ids = []
    month = snapshot['month']
    daily=snapshot.get('granularity')=='day'
    key=snapshot.get('period_key',month)
    labels = {key,key+' 00:00:00'} if daily else {month, month+'-01', month+'-01 00:00:00'}
    params = dict(snapshot['upstream_params'])

    def call(action, values):
        if check:check()
        if clock() - started >= deadline:
            invalid('TENCENT_COST_DEADLINE')
        result = gateway.call(credential, action, values, target=snapshot['uin'])
        if check:check()
        if clock()-started>=deadline:invalid('TENCENT_COST_DEADLINE')
        request_ids.append(result['RequestId'])
        return result

    # 主响应不带UIN；同一个不可变凭据快照用于身份核验及所有费用请求。
    identity = call('DescribeAccountBalance', {})
    if isinstance(identity.get('Uin'), bool) or str(identity.get('Uin')) != snapshot['uin']:
        invalid('TENCENT_ACCOUNT_MISMATCH')

    def page(number):
        response = call('DescribeCostExplorerSummary', {**params, 'PageNo': number, 'PageSize': PAGE_SIZE})
        count = response.get('Total')
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= max_rows:
            invalid('TENCENT_COST_COUNT_INVALID')
        if not isinstance(response.get('Detail'), list):
            invalid('TENCENT_COST_EARLY_EMPTY')
        if not isinstance(response.get('Header'), dict) or not isinstance(response.get('TotalDetail'), dict):
            invalid()
        return response

    first = page(1)
    header = first['Header'].get('HeadDetail')
    if not isinstance(header, list) or len(header) != 1 or not isinstance(header[0], dict) or header[0].get('Name') not in labels:
        invalid('TENCENT_COST_BOUNDARY_INVALID')
    label = header[0]['Name']

    def amount(row):
        if not isinstance(row, dict): invalid()
        times = row.get('TimeDetail')
        if not isinstance(times, list) or len(times) != 1 or not isinstance(times[0], dict) or times[0].get('Time') != label:
            invalid('TENCENT_COST_BOUNDARY_INVALID')
        value = money(row.get('Total'))
        if value != money(times[0].get('Money')):
            invalid('TENCENT_COST_TOTAL_MISMATCH')
        return value

    count = first['Total']
    total = amount(first['TotalDetail'])
    metadata = digest({key: first.get(key) for key in ('Total', 'Header', 'TotalDetail', 'ConditionValue')})
    rows, fingerprints = [], set()
    pages = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)
    for number in range(1, pages + 1):
        response = first if number == 1 else page(number)
        if digest({key: response.get(key) for key in ('Total', 'Header', 'TotalDetail', 'ConditionValue')}) != metadata:
            invalid('TENCENT_COST_SOURCE_CHANGED')
        values = response['Detail']
        expected = min(PAGE_SIZE, max(0, count - (number-1)*PAGE_SIZE))
        if len(values) != expected:
            invalid('TENCENT_COST_EARLY_EMPTY')
        fingerprint = digest(values)
        if values and fingerprint in fingerprints:
            invalid('TENCENT_COST_REPEATED_PAGE')
        fingerprints.add(fingerprint)
        for value in values:
            name = value.get('Name') if isinstance(value, dict) else None
            if not isinstance(name, str) or not name or len(name) > 255:
                invalid()
            rows.append({'source_name': name, 'amount': amount(value)})
    if count:
        tail = page(pages+1)
        if tail['Detail']:
            invalid('TENCENT_COST_EXCESS_ROWS')
        if digest({key: tail.get(key) for key in ('Total','Header','TotalDetail','ConditionValue')}) != metadata:
            invalid('TENCENT_COST_SOURCE_CHANGED')
    # 源接口无快照token；重读完整首证据只能降低变化风险，不能声称上游事务快照。
    again = page(1)
    if digest({k:v for k,v in first.items() if k!='RequestId'}) != digest({k:v for k,v in again.items() if k!='RequestId'}):
        invalid('TENCENT_COST_SOURCE_CHANGED')
    with localcontext() as ctx:
        ctx.prec = 64
        if sum((r['amount'] for r in rows), Decimal(0)) != total:
            invalid('TENCENT_COST_TOTAL_MISMATCH')
    zero_evidence = None
    if daily and (not rows or all(row['amount']==0 for row in rows)):
        invalid('TENCENT_COST_ZERO_UNCONFIRMED')
    if count == 0:
        require_month_zero_window(snapshot,current())
        auxiliary = call('DescribeBillSummaryByProduct', {'BeginTime': month, 'EndTime': month})
        values, summary = auxiliary.get('SummaryOverview'), auxiliary.get('SummaryTotal')
        if type(auxiliary.get('Ready')) is not int or auxiliary['Ready'] != 1 or not isinstance(values, list) or not isinstance(summary, dict):
            invalid('TENCENT_COST_NOT_READY')
        if total != 0 or money(summary.get('RealTotalCost')) != 0:
            invalid('TENCENT_COST_TOTAL_MISMATCH')
        for value in values:
            if not isinstance(value, dict) or value.get('BillMonth') != month or money(value.get('RealTotalCost')) != 0:
                invalid('TENCENT_COST_ZERO_UNCONFIRMED')
        require_month_zero_window(snapshot,current())
        zero_evidence = 'same-month-ready-product-summary-zero'
    candidates = (first.get('ConditionValue') or {}).get('Business', [])
    by_name, by_code = defaultdict(set), defaultdict(set)
    if not isinstance(candidates, list): invalid()
    for value in candidates:
        if not isinstance(value, dict): invalid()
        code, name = value.get('BusinessCode'), value.get('BusinessCodeName')
        if isinstance(code,str) and 0 < len(code) <= 191 and isinstance(name,str) and name:
            by_name[name].add(code)
            by_code[code].add(name)
    counts = Counter(row['source_name'] for row in rows)
    for row in rows:
        name = row['source_name']
        codes = by_name[name]
        mapped = len(codes)==1 and len(by_code[next(iter(codes))])==1 and counts[name]==1
        row['business_code'] = next(iter(codes)) if mapped else None
        row['mapping_status'] = 'mapped' if mapped else 'ambiguous' if codes or counts[name]>1 else 'unmapped'
    return {'rows': rows, 'total': total, 'request_ids': request_ids,
        'coverage': {'status': 'complete', 'month': month, 'granularity':snapshot.get('granularity','month'), 'period_key':key, 'timezone': 'Asia/Shanghai',
            'begin': snapshot['begin'], 'end_exclusive': snapshot['end_exclusive'],
            'bill_type': '1', 'fee_type': 'cost', 'dimensions': 'business',
            'currency_source': 'declared-domestic-CNY', 'row_count': len(rows),
            'source_snapshot': False, 'stability_check': 'first-page-reread', 'zero_evidence': zero_evidence}}


# 保留旧 Python 入口，不改变已受理月任务的契约身份。
collect_month = collect_period
