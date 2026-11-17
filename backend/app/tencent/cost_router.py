"""腾讯云手动完整月的可靠受理和一致查询接口。"""
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.config import get_settings
from app.dependencies import get_runtime
from app.persistence.models import (TencentAccount, TencentSyncConfig, TencentSyncJob,
    TencentSyncAttempt, TencentCostPeriod, TencentCostItem, ChangeLog)
from app.web import utc_datetime
from .access import require_action, require_dataset, require_account, require_actor
from .errors import TencentError
from .cost_collector import CONTRACT
from .credentials import CredentialRegistry

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
    frequency: Literal['manual']
    currency: Literal['CNY']


class CostJobBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$', strict=True)
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$', strict=True)


def config_data(row):
    return {'id': str(row.id) if row else None, 'revision': row.revision if row else 0,
        'is_enabled': bool(row.is_enabled) if row else False, 'frequency': row.frequency if row else 'manual',
        'currency': row.currency if row else 'CNY', 'latest_eligible_month': latest_month(),
        'last_success_month': row.last_success_month if row else None}


def readable_account(db, account_id):
    require_dataset(db)
    if db.get(TencentAccount, account_id) is None:
        raise TencentError('TENCENT_ACCOUNT_NOT_FOUND', '腾讯云账号不存在', 404)


@router.get('/accounts/{account_id}/cost-config', operation_id='tencent_cost_config_get')
def get_config(account_id: int, identity=Depends(require_action('tencent.cost.read')), runtime=Depends(get_runtime)):
    with runtime.sessions() as db:
        readable_account(db, account_id)
        row = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.account_id==account_id, TencentSyncConfig.business=='cost'))
        return {'data': config_data(row), 'meta': {}}


@router.put('/accounts/{account_id}/cost-config', operation_id='tencent_cost_config_update')
def update_config(account_id: int, body: CostConfigBody, identity=Depends(require_action('tencent.config.update', write=True)), runtime=Depends(get_runtime), settings=Depends(get_settings)):
    try:
        with runtime.sessions.begin() as db:
            require_dataset(db, lock=True)
            account = db.scalar(select(TencentAccount).where(TencentAccount.id==account_id).with_for_update())
            if account is None: raise TencentError('TENCENT_ACCOUNT_NOT_FOUND', '腾讯云账号不存在', 404)
            require_actor(db, identity)
            if body.is_enabled and (not account.is_enabled or account.verification_status!='verified'):
                raise TencentError('TENCENT_ACCOUNT_UNAVAILABLE', '请先启用账号并验证归属')
            row = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.account_id==account_id, TencentSyncConfig.business=='cost').with_for_update())
            if body.revision != (row.revision if row else 0):
                raise TencentError('TENCENT_CONFIG_CONFLICT', '配置已变更，请刷新后重试', 409)
            if body.is_enabled:
                CredentialRegistry(settings).resolve(account.credential_ref)
            before = config_data(row)
            if row is None:
                row = TencentSyncConfig(account_id=account_id, business='cost', revision=1, generation=0)
                db.add(row)
            elif row.is_enabled != body.is_enabled:
                row.revision += 1
            row.is_enabled, row.frequency, row.currency = body.is_enabled, body.frequency, body.currency
            db.flush()
            result = config_data(row)
            db.add(ChangeLog(object_type='tencent_config', object_id=str(row.id), source='admin', actor='admin:'+identity.open_id,
                before_data=before, after_data=result, committed_at=utcnow()))
    except IntegrityError:
        raise TencentError('TENCENT_CONFIG_CONFLICT', '配置已变更，请刷新后重试', 409) from None
    return {'data': result, 'meta': {}}


def job_data(job):
    return {'id': str(job.id), 'account_id': str(job.account_id), 'config_id': str(job.config_id), 'month': job.month,
        'status': job.status, 'error_code': job.error_code, 'create_time': utc_datetime(job.create_time),
        'started_at': utc_datetime(job.started_at), 'finished_at': utc_datetime(job.finished_at)}


@router.post('/accounts/{account_id}/cost-jobs', status_code=202, operation_id='tencent_cost_job_create')
def create_job(account_id: int, body: CostJobBody, request: Request, response: Response,
    identity=Depends(require_action('tencent.cost.rerun', write=True)), runtime=Depends(get_runtime)):
    begin, end = month_scope(body.month)
    with runtime.sessions.begin() as db:
        epoch = require_dataset(db, lock=True)
        account = require_account(db, account_id, epoch=epoch, lock=True)
        require_actor(db, identity)
        config = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.account_id==account_id, TencentSyncConfig.business=='cost').with_for_update())
        if config is None or not config.is_enabled or config.frequency!='manual' or config.currency!='CNY':
            raise TencentError('TENCENT_COST_DISABLED', '请先启用有效的手动月成本配置')
        existing = db.scalar(select(TencentSyncJob).where(TencentSyncJob.config_id==config.id, TencentSyncJob.idempotency_key==body.idempotency_key))
        if existing:
            if existing.month != body.month:
                raise TencentError('TENCENT_IDEMPOTENCY_CONFLICT', '该请求标识已用于不同账月', 409)
            result = job_data(existing)
        else:
            snapshot = {'handler': CONTRACT, 'business': 'cost', 'account_id': account.id, 'uin': account.uin,
                'credential_ref': account.credential_ref, 'credential_revision': account.credential_revision,
                'config_id': config.id, 'config_revision': config.revision, 'frequency': config.frequency,
                'currency': config.currency, 'dataset_epoch': epoch,
                'actor_id': identity.open_id, 'execution_identity': 'current-admin-allowlist',
                'month': body.month, 'begin': begin.isoformat()+'+08:00', 'end_exclusive': end.isoformat()+'+08:00',
                'policy': {'max_attempts': 1, 'deadline_seconds': 90, 'max_rows': 10000},
                'upstream_params': {'BeginTime': begin.strftime('%Y-%m-%d %H:%M:%S'),
                    'EndTime': (end-timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S'),
                    'PeriodType': 'month', 'BillType': '1', 'FeeType': 'cost', 'Dimensions': 'business', 'NeedConditionValue': '1'}}
            job = TencentSyncJob(config_id=config.id, account_id=account.id, idempotency_key=body.idempotency_key,
                month=body.month, status='pending', snapshot=snapshot, request_id=request.state.tencent_request_id)
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
def get_job(job_id: int, identity=Depends(require_action('tencent.job.read')), runtime=Depends(get_runtime)):
    with runtime.sessions() as db:
        require_dataset(db)
        job = db.get(TencentSyncJob, job_id)
        if job is None: raise TencentError('TENCENT_JOB_NOT_FOUND', '费用任务不存在', 404)
        attempts = db.scalars(select(TencentSyncAttempt).where(TencentSyncAttempt.job_id==job.id).order_by(TencentSyncAttempt.attempt_no)).all()
        return {'data': {**job_data(job), 'attempts': [{'id':str(row.id), 'attempt_no':row.attempt_no,
            'status':row.status, 'execution_input':row.execution_input, 'execution_output':row.execution_output,
            'error_code':row.error_code, 'started_at':utc_datetime(row.started_at), 'finished_at':utc_datetime(row.finished_at)} for row in attempts]}, 'meta': {}}


@router.get('/accounts/{account_id}/cost-jobs', operation_id='tencent_cost_job_list')
def list_jobs(account_id: int, identity=Depends(require_action('tencent.job.read')), runtime=Depends(get_runtime)):
    with runtime.sessions() as db:
        readable_account(db, account_id)
        rows = db.scalars(select(TencentSyncJob).where(TencentSyncJob.account_id==account_id).order_by(TencentSyncJob.id.desc()).limit(100)).all()
        return {'data':[job_data(row) for row in rows], 'meta':{'limit':100}}


@router.get('/accounts/{account_id}/cost-periods/{month}', operation_id='tencent_cost_period_get')
def get_period(account_id: int, month: str, identity=Depends(require_action('tencent.cost.read')), runtime=Depends(get_runtime)):
    # 同一REPEATABLE READ事务读取期间、完整产品和覆盖，禁止拆到独立连接。
    with runtime.sessions() as db:
        readable_account(db, account_id)
        row = db.scalar(select(TencentCostPeriod).where(TencentCostPeriod.account_id==account_id, TencentCostPeriod.month==month, TencentCostPeriod.currency=='CNY'))
        if row is None: raise TencentError('TENCENT_PERIOD_NOT_FOUND', '该月尚无完整费用结果', 404)
        items = db.scalars(select(TencentCostItem).where(TencentCostItem.period_id==row.id).order_by(TencentCostItem.row_no)).all()
        return {'data': {'id':str(row.id),'month':row.month,'currency':row.currency,'total':format(row.total,'.8f'),
            'coverage':row.coverage, 'latest_job_id':str(row.latest_job_id),'latest_attempt_id':str(row.latest_attempt_id),
            'items':[{'id':str(item.id),'row_no':item.row_no,'source_name':item.source_name,
                'business_code':item.business_code,'mapping_status':item.mapping_status,'amount':format(item.amount,'.8f')} for item in items]}, 'meta': {}}
