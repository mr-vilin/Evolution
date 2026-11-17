"""当前费用的一致读取；查询和导出共享口径，不产生第二份费用。"""
from datetime import datetime, timezone, timedelta
import csv
import io
from decimal import Decimal, localcontext
from typing import Annotated
from types import SimpleNamespace
from collections import defaultdict
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.dependencies import get_runtime
from app.persistence.models import TencentAccount, TencentCostItem, TencentCostPeriod, TencentSyncJob, TencentSyncConfig
from app.web import utc_datetime
from .access import require_action, require_actor, require_dataset
from .errors import TencentError

router = APIRouter(prefix='/admin/api/tencent', tags=['腾讯云费用看板'])

STATUS_LABELS = {'complete': '完整月已覆盖', 'missing': '未同步 / 缺口', 'not_due': '未到同步日',
    'incomplete': '累计未完整', 'failed_retained': '采集失败，保留上次完整费用',
    'refreshing_retained': '更新中，保留上次完整费用', 'failed': '采集失败 / 缺口', 'pending': '等待采集'}


class DashboardQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start_month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    end_month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    currency: str = Field(default='CNY', pattern=r'^[A-Z]{3}$')


def shifted_month(month, delta):
    year, number = map(int, month.split('-'))
    offset = year * 12 + number - 1 + delta
    return f'{offset // 12:04d}-{offset % 12 + 1:02d}'


def month_list(start, end):
    result = []
    while start <= end:
        result.append(start)
        start = shifted_month(start, 1)
    return result


def money(value):
    return format(value, '.8f')


def read_dashboard(db, account_id, params, *, now=None):
    """读取已提交财务当前值；组织世代只约束在途资格，不使成功账期失效。"""
    instant=now or datetime.now(timezone.utc)
    current = (instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant).astimezone(ZoneInfo('Asia/Shanghai'))
    this_month = current.strftime('%Y-%m')
    if not '1970-01' <= params.start_month <= params.end_month <= this_month:
        raise TencentError('TENCENT_COST_RANGE_INVALID', '请选择1970年起且不晚于当前月的有效月份范围', 422)
    if len(month_list(params.start_month, params.end_month)) > 120:
        raise TencentError('TENCENT_COST_RANGE_TOO_LARGE', '每次查询或导出最多120个月，请分段选择', 422)
    account = db.get(TencentAccount, account_id)
    if account is None:
        raise TencentError('TENCENT_ACCOUNT_NOT_FOUND', '腾讯云账号不存在', 404)
    selected_months = month_list(params.start_month, params.end_month)
    # 额外读取同比/环比对照月，仍在同一REPEATABLE READ事务内。
    periods = db.scalars(select(TencentCostPeriod).where(
        TencentCostPeriod.account_id == account_id,
        TencentCostPeriod.currency == params.currency,
        TencentCostPeriod.month >= shifted_month(params.start_month, -12),
        TencentCostPeriod.month <= params.end_month,
    ).order_by(TencentCostPeriod.month, TencentCostPeriod.id)).all()
    # 原始日/月记录唯一保存；月总计只在当前一致读内聚合。
    by_month=defaultdict(list)
    for row in periods:by_month[row.month].append(row)
    period_by_month={}
    items = db.execute(select(TencentCostItem).join(TencentCostPeriod,
        TencentCostPeriod.id == TencentCostItem.period_id).where(
        TencentCostPeriod.account_id == account_id, TencentCostPeriod.currency == params.currency,
        TencentCostPeriod.month >= params.start_month, TencentCostPeriod.month <= params.end_month,
    ).order_by(TencentCostPeriod.month, TencentCostItem.row_no)).scalars().all()
    # 最新受理/执行状态不从last_success_month推导，不把局部成功当连续覆盖。
    config = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.account_id == account_id,
        TencentSyncConfig.business == 'cost'))
    config_id = config.id if config else None
    jobs = db.scalars(select(TencentSyncJob).where(TencentSyncJob.config_id == config_id,
        TencentSyncJob.kind=='period', TencentSyncJob.month >= shifted_month(params.start_month,-12),
        TencentSyncJob.month <= params.end_month,TencentSyncJob.snapshot['currency'].as_string()==params.currency)
        .order_by(TencentSyncJob.id)).all()
    latest_by_key={row.snapshot.get('period_key',row.month):row for row in jobs}
    latest_display={row.month:row for row in jobs}
    last_job={}
    for month,group in by_month.items():
        monthly=[p for p in group if p.granularity=='month']
        if monthly and len(group)>1:
            raise TencentError('TENCENT_COST_PERIOD_OVERLAP','费用期间存在日月重叠，请核查后重采完整月',409)
        if monthly:
            period_by_month[month]=monthly[0]
        else:
            begin=datetime.strptime(month+'-01','%Y-%m-%d').date()
            end=datetime.strptime(shifted_month(month,1)+'-01','%Y-%m-%d').date()
            expected={(begin+timedelta(days=i)).isoformat() for i in range((end-begin).days)}
            actual={p.period_key for p in group}
            basis=('bill_type','fee_type','dimensions','currency_source')
            valid=actual==expected and all(p.coverage.get('status')=='complete' for p in group)
            valid=valid and all(all(p.coverage.get(k)==group[0].coverage.get(k) for k in basis) for p in group)
            with localcontext() as ctx:
                ctx.prec=64
                total=sum((p.total for p in group),Decimal(0))
            period_by_month[month]=SimpleNamespace(month=month,total=total,
                coverage={**group[0].coverage,'status':'complete' if valid else 'incomplete'},
                granularity='day',latest_job_id=max(p.latest_job_id for p in group),
                update_time=max(p.update_time for p in group),
                covered_dates=sorted(actual),covered_through=max(actual),missing_dates=sorted(expected-actual))
        # 对每个实际日分别检查，其他日的成功不能遮住较早日的失败或待执行。
        current_by_key={p.period_key:p for p in group}
        relevant=[j for k,j in latest_by_key.items() if j.month==month and (
            j.id>monthly[0].latest_job_id if monthly else (k not in current_by_key or j.id>current_by_key[k].latest_job_id))]
        if relevant:
            last_job[month]=max(relevant,key=lambda j:(j.status in {'failed','blocked','isolated'},j.id))
    for job in jobs:
        if job.month not in by_month:last_job[job.month]=job

    def complete(period):
        return bool(period and period.coverage.get('status') == 'complete'
            and period.coverage.get('bill_type') == '1' and period.coverage.get('fee_type') == 'cost'
            and period.coverage.get('dimensions') == 'business')

    def comparison(period, target):
        other = period_by_month.get(target)
        if not complete(period) or not complete(other):
            return {'value': None, 'reason': 'incomplete_coverage'}
        for value in (period, other):
            latest = last_job.get(value.month)
            if latest:
                return {'value': None, 'reason': 'latest_collection_failed'
                    if latest.status in {'failed', 'blocked', 'isolated'} else 'latest_collection_pending'}
        keys = ('bill_type', 'fee_type', 'dimensions', 'currency_source')
        if any(period.coverage.get(key) != other.coverage.get(key) for key in keys):
            return {'value': None, 'reason': 'incomparable_basis'}
        if other.total == 0:
            return {'value': None, 'reason': 'zero_denominator'}
        return {'value': format(((period.total-other.total)/abs(other.total)*100).quantize(Decimal('.000001')), 'f'), 'reason': None}

    months = []
    products = {}
    selected_periods = {row.id: row for row in periods if row.month in selected_months}
    with localcontext() as ctx:
        ctx.prec = 64
        for month in selected_months:
            period = period_by_month.get(month)
            job = last_job.get(month)
            due = month+'-02' if config and config.frequency in {'daily','weekly'} else shifted_month(month, 1) + '-03'
            status = 'complete' if complete(period) else 'missing'
            if period:
                if not complete(period): status = 'incomplete'
                if job:
                    if job.status in {'failed', 'blocked', 'isolated'}: status = 'failed_retained'
                    elif job.status in {'pending', 'running', 'retry_wait', 'queued'}: status = 'refreshing_retained'
            elif job:
                status = 'failed' if job.status in {'failed', 'blocked', 'isolated'} else 'pending'
            elif current.strftime('%Y-%m-%d') < due:
                status = 'not_due'
            months.append({'month': month, 'total': money(period.total) if period else None,
                'status': status, 'coverage_complete': complete(period), 'source_granularity': period.granularity if period else None,
                'covered_dates':getattr(period,'covered_dates',[]) if period else [],
                'covered_through':getattr(period,'covered_through',None) if period else None,
                'missing_dates':getattr(period,'missing_dates',[]) if period else [],
                'due_date': due, 'latest_success_at': utc_datetime(period.update_time) if period else None,
                'latest_job_id': str(period.latest_job_id) if period else None,
                'latest_task_status': (job or latest_display.get(month)).status if job or month in latest_display else None, 'error_code': job.error_code if job else None,
                'mom': comparison(period, shifted_month(month, -1)), 'yoy': comparison(period, shifted_month(month, -12))})
        for item in items:
            period = selected_periods[item.period_id]
            key = 'code:' + item.business_code if item.mapping_status == 'mapped' and item.business_code else f'period:{period.id}:row:{item.row_no}'
            row = products.setdefault(key, {'key': key, 'source_name': item.source_name,
                'business_code': item.business_code, 'mapping_status': item.mapping_status, 'amounts': {}, 'total': Decimal(0)})
            row['source_name'] = item.source_name
            row['amounts'][period.month] = row['amounts'].get(period.month, Decimal(0)) + item.amount
            row['total'] += item.amount
        for row in products.values():
            row['total'] = money(row['total'])
            # 仅可靠BusinessCode有跨期身份，期间内行不能推导其他月的“产品为零”。
            row['amounts'] = {month: money(row['amounts'].get(month, Decimal(0)))
                if month in row['amounts'] or (row['mapping_status'] == 'mapped' and complete(period_by_month.get(month)))
                else None for month in selected_months}
        total = sum((row.total for row in selected_periods.values()), Decimal(0))
    all_complete = all(row['status'] == 'complete' for row in months)
    return {'account': {'id': str(account.id), 'uin': account.uin, 'alias': account.alias},
        'start_month': params.start_month, 'end_month': params.end_month, 'currency': params.currency, 'unit': 'yuan',
        'basis': {'bill_type': '1', 'fee_type': 'cost', 'dimensions': 'business'},
        'known_total': money(total), 'complete_total': money(total) if all_complete else None,
        'coverage_complete': all_complete, 'months': months, 'products': list(products.values())}


@router.get('/accounts/{account_id}/cost-dashboard', operation_id='tencent_cost_dashboard_get')
def get_dashboard(account_id: int, params: Annotated[DashboardQuery, Query()], request: Request,
    identity=Depends(require_action('tencent.cost.read')), runtime=Depends(get_runtime)):
    with runtime.sessions.begin() as db:
        require_dataset(db, lock=True)
        require_actor(db, identity)
        data = read_dashboard(db, account_id, params)
        request.state.tencent_target = data['account']['uin']
    return {'data': data, 'meta': {}}


def csv_cell(value):
    """不可信文本以电子表格文本导出；金额仅来自服务端Decimal格式化。"""
    text = '' if value is None else str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


@router.get('/accounts/{account_id}/cost-export', operation_id='tencent_cost_export',
    response_class=Response, responses={200: {'content': {'text/csv': {}}, 'description': 'UTF-8全量产品月度CSV，带BOM'}})
def export_cost(account_id: int, params: Annotated[DashboardQuery, Query()], request: Request,
    identity=Depends(require_action('tencent.cost.export')), runtime=Depends(get_runtime)):
    with runtime.sessions.begin() as db:
        require_dataset(db, lock=True)
        require_actor(db, identity)
        data = read_dashboard(db, account_id, params)
        request.state.tencent_target = data['account']['uin']
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['账号UIN', '账号别名', '账月', '币种', '费用口径', '覆盖状态', '产品名称', '产品编码（BusinessCode）', '产品映射', '费用（元）', '最近成功时间（UTC）', '来源粒度', '累计截止日期'])
    for month in data['months']:
        common = [data['account']['uin'], csv_cell(data['account']['alias']), month['month'], data['currency'],
            '费用账单 / 总费用 / 产品', STATUS_LABELS[month['status']]]
        rows = [row for row in data['products'] if row['amounts'][month['month']] is not None]
        if not rows:
            writer.writerow([*common, '有效零费用（无产品行）' if month['total'] == '0.00000000' else '',
                '', '', month['total'] or '', month['latest_success_at'] or '', month['source_granularity'] or '', month['covered_through'] or ''])
        for row in rows:
            writer.writerow([*common, csv_cell(row['source_name']), csv_cell(row['business_code']),
                {'mapped': '已映射', 'unmapped': '未映射', 'ambiguous': '同名歧义'}[row['mapping_status']],
                row['amounts'][month['month']], month['latest_success_at'] or '', month['source_granularity'] or '', month['covered_through'] or ''])
    filename = f"tencent-cost-{data['account']['uin']}-{params.start_month}-{params.end_month}.csv"
    return Response(content=('\ufeff' + output.getvalue()).encode('utf-8'), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})
