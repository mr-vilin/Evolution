from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.config import get_settings
from app.dependencies import get_runtime
from app.persistence.models import ChangeLog, TencentAccount, TencentSyncConfig
from app.web import utc_datetime
from .access import require_action, require_dataset, require_actor
from .credentials import CredentialRegistry
from .errors import TencentError
from .gateway import TencentGateway, get_tencent_transport

router = APIRouter(prefix='/admin/api/tencent', tags=['腾讯云'])


class AccountBinding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    uin: Annotated[str, Field(pattern=r'^[1-9][0-9]{0,31}$', strict=True)]
    credential_ref: Annotated[str, Field(pattern=r'^[a-z][a-z0-9-]{0,63}$', strict=True)]


class AccountCreate(AccountBinding):
    alias: str = Field(min_length=1, max_length=128, strict=True)

    @field_validator('alias')
    @classmethod
    def normalize_alias(cls, value):
        if not value.strip():
            raise ValueError('账号别名不能为空')
        return value.strip()


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1, strict=True)
    alias: str | None = Field(default=None, min_length=1, max_length=128, strict=True)
    is_enabled: bool | None = Field(default=None, strict=True)
    credential_ref: str | None = Field(default=None, pattern=r'^[a-z][a-z0-9-]{0,63}$', strict=True)

    @field_validator('alias')
    @classmethod
    def normalize_alias(cls, value):
        if value is not None and not value.strip():
            raise ValueError('账号别名不能为空')
        return value.strip() if value is not None else None

    @model_validator(mode='after')
    def validate_changes(self):
        supplied = self.model_fields_set - {'revision'}
        if not supplied or any(getattr(self, name) is None for name in supplied):
            raise ValueError('请提供非空的维护字段')
        return self


def account_data(row):
    return {'id': str(row.id), 'uin': row.uin, 'alias': row.alias, 'credential_ref': row.credential_ref,
            'revision': row.revision, 'credential_revision': row.credential_revision, 'is_enabled': bool(row.is_enabled),
            'verification_status': row.verification_status, 'verified_at': utc_datetime(row.verified_at),
            'create_time': utc_datetime(row.create_time), 'update_time': utc_datetime(row.update_time)}


@router.get('/credential-options', operation_id='tencent_credential_options')
def credential_options(identity=Depends(require_action('tencent.account.read')), settings=Depends(get_settings), runtime=Depends(get_runtime)):
    with runtime.sessions() as db:
        require_dataset(db)
    return {'data': CredentialRegistry(settings).options(), 'meta': {}}


@router.get('/accounts', operation_id='tencent_account_list')
def list_accounts(identity=Depends(require_action('tencent.account.read')), runtime=Depends(get_runtime)):
    with runtime.sessions() as db:
        require_dataset(db)
        rows = db.scalars(select(TencentAccount).order_by(TencentAccount.id)).all()
        return {'data': [account_data(row) for row in rows], 'meta': {}}


def _verify(body, request, runtime, settings, transport):
    request.state.tencent_target = body.uin
    registry = CredentialRegistry(settings)
    credential = registry.resolve(body.credential_ref)
    with runtime.sessions() as db:
        epoch = require_dataset(db)
    gateway = TencentGateway(transport, runtime.sessions, request.state.tencent_request_id)
    gateway.verify_uin(credential, body.uin)
    return epoch


@router.post('/accounts/validate', operation_id='tencent_account_validate')
def validate_account(body: AccountBinding, request: Request, identity=Depends(require_action('tencent.account.validate', write=True)),
    runtime=Depends(get_runtime), settings=Depends(get_settings), transport=Depends(get_tencent_transport)):
    epoch = _verify(body, request, runtime, settings, transport)
    with runtime.sessions.begin() as db:
        require_dataset(db, epoch, lock=True)
        require_actor(db, identity)
    return {'data': {'uin': body.uin, 'verification_status': 'verified'}, 'meta': {}}


@router.post('/accounts', status_code=201, operation_id='tencent_account_create')
def create_account(body: AccountCreate, request: Request, response: Response,
    identity=Depends(require_action('tencent.account.create', write=True)), runtime=Depends(get_runtime),
    settings=Depends(get_settings), transport=Depends(get_tencent_transport)):
    with runtime.sessions() as db:
        require_dataset(db)
        if db.scalar(select(TencentAccount.id).where(TencentAccount.uin == body.uin)) is not None:
            raise TencentError('TENCENT_ACCOUNT_EXISTS', '该腾讯云账号已登记', 409)
    epoch = _verify(body, request, runtime, settings, transport)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        with runtime.sessions.begin() as db:
            require_dataset(db, epoch, lock=True)
            require_actor(db, identity)
            row = TencentAccount(uin=body.uin, alias=body.alias, credential_ref=body.credential_ref,
                credential_revision=1, is_enabled=True, verification_status='verified', verified_at=now)
            db.add(row)
            db.flush()
            db.refresh(row)
            db.add(ChangeLog(object_type='tencent_account', object_id=str(row.id), source='admin', actor=f'admin:{identity.open_id}',
                before_data=None, after_data={'uin':row.uin,'alias':row.alias,'credential_ref':row.credential_ref,'verification_status':'verified'}, committed_at=now))
            value = account_data(row)
    except IntegrityError:
        raise TencentError('TENCENT_ACCOUNT_EXISTS', '该腾讯云账号已登记', 409) from None
    response.headers['Location'] = '/admin/api/tencent/accounts'
    return {'data': value, 'meta': {}}


@router.patch('/accounts/{account_id}', operation_id='tencent_account_update')
def update_account(account_id: int, body: AccountUpdate, request: Request,
    identity=Depends(require_action('tencent.account.update', write=True)), runtime=Depends(get_runtime),
    settings=Depends(get_settings), transport=Depends(get_tencent_transport)):
    with runtime.sessions() as db:
        epoch = require_dataset(db)
        initial = db.get(TencentAccount, account_id)
        if initial is None:
            raise TencentError('TENCENT_ACCOUNT_NOT_FOUND', '腾讯云账号不存在', 404)
        request.state.tencent_target = initial.uin
        if initial.revision != body.revision:
            raise TencentError('TENCENT_ACCOUNT_CONFLICT', '账号已变更，请刷新后重试', 409)
        uin = initial.uin
        cost = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.account_id == account_id, TencentSyncConfig.business == 'cost'))
        cost_enabled = bool(cost and cost.is_enabled)
        cost_version = _cost_capability_version(cost)
    verification = {}
    # 外部验证不持有业务行锁；同一个不可变内存凭据用于本次所有验证。
    if body.credential_ref is not None:
        credential = CredentialRegistry(settings).resolve(body.credential_ref)
        gateway = TencentGateway(transport, runtime.sessions, request.state.tencent_request_id)
        gateway.verify_uin(credential, uin)
        if cost_enabled:
            verification = _verify_cost_capability(gateway, credential, uin)
    with runtime.sessions.begin() as db:
        require_dataset(db, epoch, lock=True)
        require_actor(db, identity)
        row = db.scalar(select(TencentAccount).where(TencentAccount.id == account_id).with_for_update())
        if row is None:
            raise TencentError('TENCENT_ACCOUNT_NOT_FOUND', '腾讯云账号不存在', 404)
        request.state.tencent_target = row.uin
        if row.revision != body.revision:
            raise TencentError('TENCENT_ACCOUNT_CONFLICT', '账号已变更，请刷新后重试', 409)
        if body.credential_ref is not None:
            current_cost = db.scalar(select(TencentSyncConfig).where(
                TencentSyncConfig.account_id == account_id, TencentSyncConfig.business == 'cost').with_for_update(read=True))
            if _cost_capability_version(current_cost) != cost_version:
                raise TencentError('TENCENT_CAPABILITY_CHANGED', '账号成本能力已变更，请重新验证凭据', 409)
        before = jsonable_encoder(account_data(row))
        changed = False
        if body.alias is not None and row.alias != body.alias:
            row.alias = body.alias
            changed = True
        if body.credential_ref is not None:
            row.credential_ref = body.credential_ref
            row.verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
            row.verification_status = 'verified'
            row.credential_revision += 1
            changed = True
        if body.is_enabled is not None and row.is_enabled != body.is_enabled:
            row.is_enabled = body.is_enabled
            row.credential_revision += 1
            changed = True
        if changed:
            row.revision += 1
            db.flush()
            db.refresh(row)
            db.add(ChangeLog(object_type='tencent_account', object_id=str(row.id), source='admin', actor='admin:'+identity.open_id,
                before_data=before, after_data={**jsonable_encoder(account_data(row)), 'request_id':request.state.tencent_request_id}, committed_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        result = account_data(row)
    return {'data': result, 'meta': {'verification': verification}}


def _verify_cost_capability(gateway, credential, uin):
    """只核验当前成本处理器实际使用的动作；不采集完整账月，不持久化财务正文。"""
    from .cost_router import latest_month, month_scope
    month = latest_month()
    begin, end = month_scope(month)
    response = gateway.call(credential, 'DescribeCostExplorerSummary', {
        'BeginTime': begin.strftime('%Y-%m-%d %H:%M:%S'),
        'EndTime': (end-timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S'),
        'PeriodType': 'month', 'BillType': '1', 'FeeType': 'cost', 'Dimensions': 'business',
        'NeedConditionValue': '1', 'PageNo': 1, 'PageSize': 100}, target=uin)
    if type(response.get('Total')) is not int or response['Total'] < 0 or not isinstance(response.get('Detail'), list):
        raise TencentError('TENCENT_UPSTREAM_INVALID', '腾讯云成本权限返回无法核验', 502)
    auxiliary = gateway.call(credential, 'DescribeBillSummaryByProduct', {'BeginTime': month, 'EndTime': month}, target=uin)
    if type(auxiliary.get('Ready')) is not int or auxiliary['Ready'] not in {0, 1}:
        raise TencentError('TENCENT_UPSTREAM_INVALID', '腾讯云辅助对账权限返回无法核验', 502)
    return {'auxiliary_readiness': 'ready' if auxiliary['Ready'] else 'not_ready'}


def _cost_capability_version(config):
    return (config.id, bool(config.is_enabled), config.control_revision) if config is not None else None
