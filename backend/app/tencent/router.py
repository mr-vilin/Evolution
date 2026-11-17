from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.config import get_settings
from app.dependencies import get_runtime
from app.persistence.models import ChangeLog, TencentAccount
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


def account_data(row):
    return {'id': str(row.id), 'uin': row.uin, 'alias': row.alias, 'credential_ref': row.credential_ref,
            'credential_revision': row.credential_revision, 'is_enabled': bool(row.is_enabled),
            'verification_status': row.verification_status, 'verified_at': utc_datetime(row.verified_at),
            'create_time': utc_datetime(row.create_time), 'update_time': utc_datetime(row.update_time)}


@router.get('/credential-options', operation_id='tencent_credential_options')
def credential_options(identity=Depends(require_action('tencent.account.read')), settings=Depends(get_settings)):
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
