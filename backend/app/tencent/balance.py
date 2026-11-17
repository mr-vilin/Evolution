"""即时余额查询：仅返回当前请求结果，不落财务快照。"""
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
from sqlalchemy import text, select, func
from app.persistence.models import TencentApiCall
from decimal import Decimal, localcontext
from fastapi import APIRouter, Depends, Request
from app.config import get_settings
from app.dependencies import get_runtime
from .access import require_action, require_account, require_dataset, require_actor
from .credentials import CredentialRegistry
from .errors import TencentError
from .audit import rate_window_cutoff
from .gateway import TencentGateway, get_tencent_transport

router = APIRouter(prefix='/admin/api/tencent', tags=['腾讯云'])

MONEY_FIELDS = {
    'real_balance': 'RealBalance', 'cash_account_balance': 'CashAccountBalance',
    'income_into_account_balance': 'IncomeIntoAccountBalance', 'present_account_balance': 'PresentAccountBalance',
    'freeze_amount': 'FreezeAmount', 'owe_amount': 'OweAmount', 'credit_amount': 'CreditAmount',
    'credit_balance': 'CreditBalance', 'real_credit_balance': 'RealCreditBalance',
}


def amount_yuan(value):
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise TencentError('TENCENT_UPSTREAM_INVALID', '腾讯云返回的金额无法核验', 502)
    value = Decimal(value)
    if not value.is_finite() or len(value.as_tuple().digits) > 64 or abs(value.adjusted()) > 64:
        raise TencentError('TENCENT_UPSTREAM_INVALID', '腾讯云返回的金额无法核验', 502)
    with localcontext() as context:
        context.prec = 160
        result = value / 100
        rendered = format(result, 'f') if result else '0'
    whole, _, fraction = rendered.partition('.')
    return whole + '.' + fraction.ljust(2, '0')


@router.get('/accounts/{account_id}/balance', operation_id='tencent_balance_query')
def query_balance(account_id: int, request: Request, identity=Depends(require_action('tencent.balance.query')),
    runtime=Depends(get_runtime), settings=Depends(get_settings), transport=Depends(get_tencent_transport)):
    with runtime.sessions() as db:
        epoch = require_dataset(db)
        account = require_account(db, account_id)
        uin, alias, revision, credential_ref = account.uin, account.alias, account.credential_revision, account.credential_ref
    request.state.tencent_target = uin
    credential = CredentialRegistry(settings).resolve(credential_ref)
    with balance_slot(runtime.sessions, uin):
        response = TencentGateway(transport, runtime.sessions, request.state.tencent_request_id).call(
            credential, 'DescribeAccountBalance', {}, target=uin)
    actual = response.get('Uin')
    if isinstance(actual, bool) or not isinstance(actual, (str, int)) or str(actual) != uin:
        raise TencentError('TENCENT_ACCOUNT_MISMATCH', '凭据归属与账号 UIN 不一致', 422)
    amounts = {key: amount_yuan(response.get(field)) for key, field in MONEY_FIELDS.items()}
    if response.get('TempCredit') is not None:
        amounts['temp_credit'] = amount_yuan(response['TempCredit'])
    with runtime.sessions.begin() as db:
        require_account(db, account_id, epoch=epoch, revision=revision, lock=True)
        require_actor(db, identity)
        return {'data': {'account_id': str(account_id), 'uin': uin, 'alias': alias, 'currency': 'CNY',
            'currency_source': '国内站财务账本配置', 'unit': 'yuan', 'amounts': amounts,
            'queried_at': datetime.now(timezone.utc).isoformat()}, 'meta': {}}


@contextmanager
def balance_slot(sessions, uin):
    # 连接级 advisory lock 覆盖所有应用进程，不跨出站调用持有业务行锁。
    with sessions() as db:
        engine = db.get_bind()
    with engine.connect() as connection:
        database = connection.execute(text('SELECT DATABASE()')).scalar_one()
        key = 'tencent.balance.' + hashlib.sha256(f'{database}:{uin}'.encode()).hexdigest()[:40]
        acquired = connection.execute(text('SELECT GET_LOCK(:key,0)'), {'key':key}).scalar_one()
        if acquired != 1:
            raise TencentError('TENCENT_BALANCE_BUSY', '该账号正在查询余额，请稍后刷新', 429)
        try:
            cutoff = rate_window_cutoff(datetime.now(timezone.utc).replace(tzinfo=None))
            recent = connection.execute(select(func.count()).select_from(TencentApiCall).where(
                TencentApiCall.direction=='outbound', TencentApiCall.action=='DescribeAccountBalance',
                TencentApiCall.target_id==uin, TencentApiCall.started_at>=cutoff)).scalar_one()
            if recent >= 5:
                raise TencentError('TENCENT_BALANCE_RATE_LIMITED', '余额查询过于频繁，请稍后刷新', 429)
            yield
        finally:
            try:
                released = connection.execute(text('SELECT RELEASE_LOCK(:key)'), {'key':key}).scalar_one()
                if released != 1:
                    connection.invalidate()
            except BaseException:
                connection.invalidate()
                raise