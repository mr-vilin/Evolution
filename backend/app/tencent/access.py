"""有限动作目录；仅复用管理员准入，不把旧机器权限或通配符扩散到财务。"""
from fastapi import Depends, Request
from sqlalchemy import select
from app.dependencies import get_admin_identity, get_runtime, require_admin_write
from app.persistence.models import DatasetState, TencentAccount
from .errors import TencentError

TENCENT_ACTIONS = frozenset({'tencent.account.read', 'tencent.account.create', 'tencent.account.validate',
    'tencent.account.update', 'tencent.balance.query', 'tencent.cost.read', 'tencent.cost.export',
    'tencent.config.update', 'tencent.cost.rerun', 'tencent.job.read'})


def require_action(action, *, write=False):
    dependency = require_admin_write if write else get_admin_identity
    def authorize(request: Request, identity=Depends(dependency)):
        if action not in TENCENT_ACTIONS:
            raise TencentError('TENCENT_ACTION_FORBIDDEN', '当前动作未获授权', 403)
        actor = identity[0] if write else identity
        request.state.tencent_actor = actor.open_id
        request.state.tencent_action = action
        return actor
    return authorize


def require_dataset(db, epoch=None, *, lock=False):
    stmt = select(DatasetState).where(DatasetState.id == 1)
    if lock:
        stmt = stmt.with_for_update(read=True)
    state = db.scalar(stmt.execution_options(populate_existing=True))
    if state is None or state.initialization_status != 'complete':
        raise TencentError('INITIALIZATION_INCOMPLETE', '请由管理员完成初始化向导')
    if epoch is not None and state.dataset_epoch != epoch:
        raise TencentError('DATASET_CHANGED', '组织初始化世代已变化，请重新发起操作')
    return state.dataset_epoch


def require_account(db, account_id, *, epoch=None, revision=None, lock=False):
    require_dataset(db, epoch, lock=lock)
    stmt = select(TencentAccount).where(TencentAccount.id == account_id)
    if lock:
        stmt = stmt.with_for_update(read=True)
    account = db.scalar(stmt.execution_options(populate_existing=True))
    if account is None:
        raise TencentError('TENCENT_ACCOUNT_NOT_FOUND', '腾讯云账号不存在', 404)
    if not account.is_enabled or account.verification_status != 'verified':
        raise TencentError('TENCENT_ACCOUNT_UNAVAILABLE', '腾讯云账号已停用或未通过归属验证')
    if revision is not None and account.credential_revision != revision:
        raise TencentError('TENCENT_CREDENTIAL_CHANGED', '账号凭据已变更，请重新发起操作')
    return account


def require_actor(db, identity):
    from datetime import datetime, timezone
    from app.persistence.repositories import SqlIdentityRepository
    statement = SqlIdentityRepository.session_auth_statement(identity.token_digest, datetime.now(timezone.utc).replace(tzinfo=None))
    if db.scalar(statement.with_for_update(read=True).execution_options(populate_existing=True)) is None:
        raise TencentError('ADMIN_SESSION_REQUIRED', '管理员资格或会话已失效', 401)
