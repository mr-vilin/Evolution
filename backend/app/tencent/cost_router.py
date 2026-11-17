"""腾讯云日/月期间的可靠受理和一致查询接口。"""
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, and_, or_
from sqlalchemy.exc import IntegrityError
from app.config import get_settings
from app.dependencies import get_runtime
from app.persistence.models import (TencentAccount, TencentSyncConfig, TencentSyncJob,
    TencentSyncAttempt, TencentCostPeriod, TencentCostItem, ChangeLog)
from app.web import utc_datetime
from .access import require_action, require_dataset, require_account, require_actor
from .errors import TencentError
from .credentials import CredentialRegistry
from .cost_policy import CostRunPolicy, effective_policy
from .cost_scheduler import period_snapshot, accept_batch, shifted, next_point

router = APIRouter(prefix='/admin/api/tencent', tags=['腾讯云成本'])


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def latest_month(now=None):
    current = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('Asia/Shanghai'))
    month_start = current.date().replace(day=1)
    end = month_start - timedelta(days=1)
    if current.day < 3:
        end = end.replace(day=1)-timedelta(days=1)
    return end.strftime('%Y-%m')


def month_scope(month):
    try:
        begin = datetime.strptime(month, '%Y-%m')
    except ValueError:
        raise TencentError('TENCENT_MONTH_INVALID', '请选择有效完整账月', 422) from None
    if month < '1970-01' or month > latest_month():
        raise TencentError('TENCENT_MONTH_NOT_ELIGIBLE', '该账月尚未到同步日或超出支持日期', 422)
    end = begin.replace(year=begin.year+1, month=1) if begin.month == 12 else begin.replace(month=begin.month+1)
    return begin, end


class CostConfigBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0, strict=True)
    is_enabled: bool = Field(strict=True)
    frequency: Literal['manual','monthly','daily','weekly']
    execution_time: str = Field(default='13:30',pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$',strict=True)
    currency: Literal['CNY']
    run_policy: CostRunPolicy | None = None


class CostJobBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    day: str | None = Field(default=None,pattern=r'^\d{4}-(0[1-9]|1[0-2])-([012][0-9]|3[01])$',strict=True)
    month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$', strict=True)
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$', strict=True)


def config_data(row,db=None):
    latest=db.scalar(select(TencentSyncJob).where(TencentSyncJob.config_id==row.id,TencentSyncJob.kind=='period',
        TencentSyncJob.status=='succeeded').order_by(TencentSyncJob.finished_at.desc(),TencentSyncJob.id.desc()).limit(1)) if row and db else None
    last_success=db.scalar(select(func.max(TencentSyncJob.finished_at)).where(TencentSyncJob.account_id==row.account_id,
        TencentSyncJob.kind=='period',TencentSyncJob.status=='succeeded')) if row and db else None
    return {'id': str(row.id) if row else None, 'revision': row.revision if row else 0,
        'is_enabled': bool(row.is_enabled) if row else False, 'frequency': row.frequency if row else 'manual',
        'currency': row.currency if row else 'CNY', 'latest_eligible_month': latest_month(),
        'execution_time':row.execution_time if row else '13:30','timezone':'Asia/Shanghai',
        'schedule_start_month':row.schedule_start_month if row else None,
        'latest_eligible_date':(utcnow().replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).date()-timedelta(days=1)).isoformat(),
        'next_execution_at':utc_datetime(next_point(utcnow(),row.execution_time,row.frequency)).isoformat() if row and row.is_enabled and row.frequency in {'monthly','daily','weekly'} else None,
        'run_policy': effective_policy(row.run_policy if row else None),
        'last_success_month': row.last_success_month if row else None,
        'last_success_period':latest.snapshot.get('period_key',latest.month) if latest else None,
        'last_success_granularity':latest.snapshot.get('granularity','month') if latest else None,
        'last_success_at':utc_datetime(last_success).isoformat() if last_success else None}


def readable_account(db, account_id):
    require_dataset(db)
    account=db.get(TencentAccount, account_id)
    if account is None:
        raise TencentError('TENCENT_ACCOUNT_NOT_FOUND', '腾讯云账号不存在', 404)
    return account


@router.get('/accounts/{account_id}/cost-config', operation_id='tencent_cost_config_get')
def get_config(account_id: int, request: Request, identity=Depends(require_action('tencent.cost.read')), runtime=Depends(get_runtime)):
    with runtime.sessions() as db:
        request.state.tencent_target=readable_account(db, account_id).uin
        row = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.account_id==account_id, TencentSyncConfig.business=='cost'))
        return {'data': config_data(row,db), 'meta': {}}


@router.put('/accounts/{account_id}/cost-config', operation_id='tencent_cost_config_update')
def update_config(account_id: int, body: CostConfigBody, request: Request, identity=Depends(require_action('tencent.config.update', write=True)), runtime=Depends(get_runtime), settings=Depends(get_settings)):
    try:
        with runtime.sessions.begin() as db:
            require_dataset(db, lock=True)
            account = db.scalar(select(TencentAccount).where(TencentAccount.id==account_id).with_for_update())
            if account is None: raise TencentError('TENCENT_ACCOUNT_NOT_FOUND', '腾讯云账号不存在', 404)
            request.state.tencent_target=account.uin
            require_actor(db, identity)
            if body.is_enabled and (not account.is_enabled or account.verification_status!='verified'):
                raise TencentError('TENCENT_ACCOUNT_UNAVAILABLE', '请先启用账号并验证归属')
            row = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.account_id==account_id, TencentSyncConfig.business=='cost').with_for_update())
            if body.revision != (row.revision if row else 0):
                raise TencentError('TENCENT_CONFIG_CONFLICT', '配置已变更，请刷新后重试', 409)
            if body.is_enabled:
                CredentialRegistry(settings).resolve(account.credential_ref)
            before = config_data(row)
            policy = body.run_policy.model_dump() if body.run_policy else effective_policy(row.run_policy if row else None)
            if row is None:
                row = TencentSyncConfig(account_id=account_id, business='cost', revision=1, control_revision=1, generation=0)
                db.add(row)
            else:
                if row.is_enabled != body.is_enabled:
                    row.control_revision += 1
                if row.is_enabled != body.is_enabled or effective_policy(row.run_policy)!=policy or row.frequency!=body.frequency or row.execution_time!=body.execution_time:
                    row.revision += 1
            row.is_enabled, row.frequency, row.currency = body.is_enabled, body.frequency, body.currency
            row.execution_time=body.execution_time
            if body.is_enabled and body.frequency=='monthly' and not row.schedule_start_month:
                row.schedule_start_month=shifted(latest_month(),-1)
            if body.is_enabled and body.frequency in {'daily','weekly'} and not row.schedule_start_date:
                local=utcnow().replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Shanghai'))
                row.schedule_start_date=shifted(local.strftime('%Y-%m'),-1)+'-01'
            row.run_policy=policy
            db.flush()
            result = config_data(row)
            db.add(ChangeLog(object_type='tencent_config', object_id=str(row.id), source='admin', actor='admin:'+identity.open_id,
                before_data=before, after_data=result, committed_at=utcnow()))
    except IntegrityError:
        raise TencentError('TENCENT_CONFIG_CONFLICT', '配置已变更，请刷新后重试', 409) from None
    return {'data': result, 'meta': {}}


def job_data(job):
    return {'kind':job.kind,'parent_job_id':str(job.parent_job_id) if job.parent_job_id else None,
        'periods':job.snapshot.get('periods'), 'period_key':job.snapshot.get('period_key',job.month), 'granularity':job.snapshot.get('granularity','month'),
        'deferred_periods':job.snapshot.get('deferred_periods',[]), 'blocked_periods':job.snapshot.get('blocked_periods',[]),
        'months':job.snapshot.get('months') if job.kind=='batch' else None,
        'deferred_months':job.snapshot.get('deferred_months') if job.kind=='batch' else None,
        'scheduled_at':job.snapshot.get('scheduled_at') if job.kind=='batch' else None,
        'blocked_months':job.snapshot.get('blocked_months',[]) if job.kind=='batch' else None,
        'id': str(job.id), 'account_id': str(job.account_id), 'config_id': str(job.config_id), 'month': job.month,
        'status': job.status, 'error_code': job.error_code, 'create_time': utc_datetime(job.create_time),
        'started_at': utc_datetime(job.started_at), 'finished_at': utc_datetime(job.finished_at),
        'next_attempt_at':utc_datetime(job.next_attempt_at),'deadline_at':utc_datetime(job.deadline_at),
        'queue_deadline_at':utc_datetime(job.queue_deadline_at),
        'source_job_id':str(job.source_job_id) if job.source_job_id is not None else None}


@router.post('/accounts/{account_id}/cost-jobs', status_code=202, operation_id='tencent_cost_job_create')
def create_job(account_id: int, body: CostJobBody, request: Request, response: Response,
    identity=Depends(require_action('tencent.cost.rerun', write=True)), runtime=Depends(get_runtime)):
    return accept_job(account_id,body,request,response,identity,runtime)


class CostRerunBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    idempotency_key: str = Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$',strict=True)
    reason: Literal['after_fix','refresh_result']


@router.post('/cost-jobs/{job_id}/rerun',status_code=202,operation_id='tencent_cost_job_rerun')
def rerun_job(job_id: int,body: CostRerunBody,request: Request,response: Response,
    identity=Depends(require_action('tencent.cost.rerun',write=True)),runtime=Depends(get_runtime)):
    with runtime.sessions() as db:
        require_dataset(db)
        source=db.get(TencentSyncJob,job_id)
        if source is None:raise TencentError('TENCENT_JOB_NOT_FOUND','费用任务不存在',404)
        if source.kind=='batch':raise TencentError('TENCENT_BATCH_RERUN_PERIOD','请分别重跑失败账月或新建立即执行批次',422)
        account_id,month=source.account_id,source.month
        day=source.snapshot.get('period_key') if source.snapshot.get('granularity')=='day' else None
    return accept_job(account_id,CostJobBody(month=month,day=day,idempotency_key=body.idempotency_key),request,response,identity,runtime,
        source_job_id=job_id,reason=body.reason)


def accept_job(account_id,body,request,response,identity,runtime,*,source_job_id=None,reason=None):
    if body.day:
        try:day=datetime.strptime(body.day,'%Y-%m-%d').date()
        except ValueError:raise TencentError('TENCENT_DAY_INVALID','请选择有效自然日',422) from None
        cutoff=utcnow().replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).date()-timedelta(days=1)
        if body.day[:7]!=body.month or not '1970-01-01'<=body.day<=cutoff.isoformat():
            raise TencentError('TENCENT_DAY_NOT_ELIGIBLE','只能采集所属月份截至北京时间昨日的自然日',422)
    else:month_scope(body.month)
    with runtime.sessions.begin() as db:
        epoch = require_dataset(db, lock=True)
        account = require_account(db, account_id, epoch=epoch, lock=True)
        require_actor(db, identity)
        request.state.tencent_target=account.uin
        if source_job_id is not None:
            source=db.get(TencentSyncJob,source_job_id)
            if source is None or source.account_id!=account_id or source.month!=body.month:
                raise TencentError('TENCENT_JOB_NOT_FOUND','原费用任务不存在',404)
            if source.status not in {'succeeded','failed'}:
                raise TencentError('TENCENT_JOB_NOT_TERMINAL','请等待原任务结束后重跑',409)
        config = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.account_id==account_id, TencentSyncConfig.business=='cost').with_for_update())
        if config is None or not config.is_enabled or config.frequency not in {'manual','monthly','daily','weekly'} or config.currency!='CNY':
            raise TencentError('TENCENT_COST_DISABLED', '请先启用有效的成本配置')
        # 先定位原意图，再解释当前范围；已受理日不会在重试中扩大成整月。
        target=body.day or body.month
        granularity='day' if body.day else 'month'
        existing = db.scalar(select(TencentSyncJob).where(TencentSyncJob.config_id==config.id, TencentSyncJob.dataset_epoch==epoch, TencentSyncJob.kind=='period',or_(TencentSyncJob.idempotency_key=='manual-period:'+hashlib.sha256(body.idempotency_key.encode()).hexdigest(),
            and_(TencentSyncJob.idempotency_key==body.idempotency_key,TencentSyncJob.snapshot['request_namespace'].as_string().is_(None)))).with_for_update())
        if existing:
            if existing.snapshot.get('requested_period_key',existing.snapshot.get('period_key',existing.month))!=target or existing.source_job_id!=source_job_id:
                raise TencentError('TENCENT_IDEMPOTENCY_CONFLICT', '该请求标识已用于不同账月', 409)
            result = job_data(existing)
        else:
            policy=effective_policy(config.run_policy)
            queued=db.scalar(select(func.count()).select_from(TencentSyncJob).where(
                TencentSyncJob.config_id==config.id,TencentSyncJob.dataset_epoch==epoch,
                TencentSyncJob.status.in_(['pending','running','retry_wait'])))
            if queued>=policy['queue_limit']:
                raise TencentError('TENCENT_COST_QUEUE_FULL','本配置待处理任务已达上限，请等待任务完成',429)
            requested=target
            if granularity=='day' and db.scalar(select(TencentCostPeriod.id).where(TencentCostPeriod.account_id==account_id,
                TencentCostPeriod.month==body.month,TencentCostPeriod.currency==config.currency,TencentCostPeriod.granularity=='month').with_for_update(read=True)) is not None:
                granularity,target='month',body.month
            snapshot=period_snapshot(account,config,epoch,body.month,granularity=granularity,period_key=target,actor_id=identity.open_id,
                execution_identity='current-admin-allowlist',source_job_id=source_job_id,reason=reason)
            snapshot['requested_period_key']=requested
            job = TencentSyncJob(config_id=config.id, account_id=account.id, dataset_epoch=epoch, idempotency_key='manual-period:'+hashlib.sha256(body.idempotency_key.encode()).hexdigest(),
                month=body.month, source_job_id=source_job_id, status='pending', snapshot=snapshot, request_id=request.state.tencent_request_id,
                queue_deadline_at=utcnow()+timedelta(seconds=snapshot['policy']['queue_deadline_seconds']))
            db.add(job)
            db.flush()
            db.refresh(job)
            result = job_data(job)
            db.add(ChangeLog(object_type='tencent_job', object_id=str(job.id), source='admin', actor='admin:'+identity.open_id,
                before_data=None, after_data={'status':'pending','month':job.month,'config_id':str(config.id)}, committed_at=utcnow()))
    location = '/admin/api/tencent/cost-jobs/'+result['id']
    response.headers['Location'] = location
    return {'data': {**result, 'status_url': location}, 'meta': {}}


@router.get('/cost-jobs/{job_id}', operation_id='tencent_cost_job_get')
def get_job(job_id: int, request: Request, identity=Depends(require_action('tencent.job.read')), runtime=Depends(get_runtime)):
    with runtime.sessions() as db:
        require_dataset(db)
        job = db.get(TencentSyncJob, job_id)
        if job is None: raise TencentError('TENCENT_JOB_NOT_FOUND', '费用任务不存在', 404)
        request.state.tencent_target=readable_account(db,job.account_id).uin
        attempts = db.scalars(select(TencentSyncAttempt).where(TencentSyncAttempt.job_id==job.id).order_by(TencentSyncAttempt.attempt_no)).all()
        return {'data': {**job_data(job), 'children':[job_data(row) for row in db.scalars(select(TencentSyncJob).where(TencentSyncJob.parent_job_id==job.id).order_by(TencentSyncJob.id))] if job.kind=='batch' else [], 'attempts': [{'id':str(row.id), 'attempt_no':row.attempt_no,
            'status':row.status, 'execution_input':row.execution_input, 'execution_output':row.execution_output,
            'return_state':row.return_state,
            'input_capture_status':'CAPTURED',
            'output_capture_status':('CAPTURED' if row.execution_output is not None else 'FAILED') if row.return_state=='VALUE' else 'NO_CONTENT' if row.return_state=='NOT_RETURNED' else 'UNAVAILABLE',
            'request_id':row.request_id, 'failure_evidence':row.failure_evidence,
            'error_code':row.error_code, 'started_at':utc_datetime(row.started_at), 'finished_at':utc_datetime(row.finished_at)} for row in attempts]}, 'meta': {}}


@router.get('/accounts/{account_id}/cost-jobs', operation_id='tencent_cost_job_list')
def list_jobs(account_id: int, request: Request, identity=Depends(require_action('tencent.job.read')), runtime=Depends(get_runtime)):
    with runtime.sessions() as db:
        request.state.tencent_target=readable_account(db, account_id).uin
        rows = db.scalars(select(TencentSyncJob).where(TencentSyncJob.account_id==account_id).order_by(TencentSyncJob.id.desc()).limit(100)).all()
        return {'data':[job_data(row) for row in rows], 'meta':{'limit':100}}


@router.get('/accounts/{account_id}/cost-periods/{month}', operation_id='tencent_cost_period_get')
def get_period(account_id: int, month: str, request: Request, identity=Depends(require_action('tencent.cost.read')), runtime=Depends(get_runtime)):
    # 同一REPEATABLE READ事务读取期间、完整产品和覆盖，禁止拆到独立连接。
    with runtime.sessions() as db:
        request.state.tencent_target=readable_account(db, account_id).uin
        row = db.scalar(select(TencentCostPeriod).where(TencentCostPeriod.account_id==account_id, TencentCostPeriod.period_key==month, TencentCostPeriod.currency=='CNY'))
        if row is None and len(month)==7:
            # 保留旧月份 URL：从原始日费用按同一看板口径聚合，不另存月副本。
            sources=db.scalars(select(TencentCostPeriod).where(TencentCostPeriod.account_id==account_id,
                TencentCostPeriod.month==month,TencentCostPeriod.currency=='CNY',TencentCostPeriod.granularity=='day')
                .order_by(TencentCostPeriod.period_key)).all()
            if sources:
                from .cost_dashboard import DashboardQuery,read_dashboard
                view=read_dashboard(db,account_id,DashboardQuery(start_month=month,end_month=month),now=utcnow())
                summary=view['months'][0]
                return {'data':{'id':'daily:'+month,'month':month,'period_key':month,'granularity':'day',
                    'currency':'CNY','total':summary['total'],
                    'coverage':{**view['basis'],'status':'complete' if summary['coverage_complete'] else 'incomplete',
                        'month':month,'granularity':'day','period_key':month,'aggregation':'query','timezone':'Asia/Shanghai',
                        'currency_source':sources[0].coverage.get('currency_source'),'source_period_count':len(sources),
                        'covered_dates':summary['covered_dates'],'missing_dates':summary['missing_dates']},
                    'covered_dates':summary['covered_dates'],'covered_through':summary['covered_through'],
                    'missing_dates':summary['missing_dates'],'latest_job_id':summary['latest_job_id'],
                    'latest_attempt_id':str(max(p.latest_attempt_id for p in sources)),
                    'items':[{'id':item['key'],'row_no':i+1,'source_name':item['source_name'],
                        'business_code':item['business_code'],'mapping_status':item['mapping_status'],
                        'amount':item['amounts'][month]} for i,item in enumerate(view['products'])]},'meta':{}}
        if row is None: raise TencentError('TENCENT_PERIOD_NOT_FOUND', '该期间尚无费用结果', 404)
        items = db.scalars(select(TencentCostItem).where(TencentCostItem.period_id==row.id).order_by(TencentCostItem.row_no)).all()
        return {'data': {'id':str(row.id),'month':row.month,'period_key':row.period_key,'granularity':row.granularity,'currency':row.currency,'total':format(row.total,'.8f'),
            'coverage':row.coverage, 'latest_job_id':str(row.latest_job_id),'latest_attempt_id':str(row.latest_attempt_id),
            'items':[{'id':str(item.id),'row_no':item.row_no,'source_name':item.source_name,
                'business_code':item.business_code,'mapping_status':item.mapping_status,'amount':format(item.amount,'.8f')} for item in items]}, 'meta': {}}


class CostBatchBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    idempotency_key: str = Field(min_length=1,max_length=112,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$',strict=True)


@router.post('/accounts/{account_id}/cost-batches',status_code=202,operation_id='tencent_cost_batch_create')
def create_batch(account_id: int,body: CostBatchBody,request: Request,response: Response,
    identity=Depends(require_action('tencent.cost.rerun',write=True)),runtime=Depends(get_runtime)):
    with runtime.sessions.begin() as db:
        epoch=require_dataset(db,lock=True)
        account=require_account(db,account_id,epoch=epoch,lock=True)
        require_actor(db,identity)
        request.state.tencent_target=account.uin
        config=db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.account_id==account_id,TencentSyncConfig.business=='cost').with_for_update())
        if not config or not config.is_enabled or config.frequency not in {'monthly','daily','weekly'}:
            raise TencentError('TENCENT_MONTHLY_DISABLED','请先启用自动成本配置')
        job,_=accept_batch(db,account,config,epoch,'manual-batch:'+body.idempotency_key,utcnow(),
            actor_id=identity.open_id,execution_identity='current-admin-allowlist',request_id=request.state.tencent_request_id)
        result=job_data(job)
    location='/admin/api/tencent/cost-jobs/'+result['id']
    response.headers['Location']=location
    return {'data':{**result,'status_url':location},'meta':{}}
