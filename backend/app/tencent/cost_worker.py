"""独立云成本worker：单配置有界单次尝试，不占组织同步租约。"""
from dataclasses import dataclass
from datetime import timedelta
import logging
import signal
import threading
import uuid
from sqlalchemy import delete, select
from app.persistence.models import (AdminAllowlist, TencentSyncConfig, TencentSyncJob,
    TencentSyncAttempt, TencentCostPeriod, TencentCostItem, ChangeLog)
from .access import require_account
from .credentials import CredentialRegistry
from .errors import TencentError
from .gateway import TencentGateway, sdk_transport
from .cost_collector import collect_month, CONTRACT
from .cost_router import utcnow

log = logging.getLogger('organization.tencent.cost_worker')


@dataclass(frozen=True)
class CostClaim:
    job_id: int
    config_id: int
    attempt_id: int
    generation: int
    owner: str
    snapshot: dict
    request_id: str


class TencentCostWorker:
    """claim(now)与execute(claim)分离，后续治理可复用固定资格而不重造业务处理。"""
    def __init__(self, sessions, settings, transport=sdk_transport, *, now=utcnow, owner=None):
        self.sessions, self.settings, self.transport = sessions, settings, transport
        self.now, self.owner = now, owner or str(uuid.uuid4())

    def _config_gate(self, db, snapshot, *, skip_locked=False):
        require_account(db, snapshot['account_id'], epoch=snapshot['dataset_epoch'], revision=snapshot['credential_revision'], lock=True)
        # 异步执行使用可信open_id与当前管理员资格，不冻结HTTP会话有效期。
        actor = db.scalar(select(AdminAllowlist.open_id).where(AdminAllowlist.open_id==snapshot['actor_id']).with_for_update(read=True))
        if actor is None:
            raise TencentError('TENCENT_ACTOR_REVOKED', '发起管理员已被撤权')
        config = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.id==snapshot['config_id']).with_for_update(skip_locked=skip_locked).execution_options(populate_existing=True))
        if config is None and skip_locked: return None
        if config is None or not config.is_enabled or config.revision!=snapshot['config_revision']:
            raise TencentError('TENCENT_COST_CONFIG_CHANGED', '费用配置已关闭或变更')
        if snapshot['handler']!=CONTRACT or config.frequency!='manual' or config.currency!=snapshot['currency']:
            raise TencentError('TENCENT_COST_CONTRACT_CHANGED', '费用执行契约已变化')
        return config

    def claim(self, now=None):
        now = now or self.now()
        with self.sessions() as db:
            candidates = list(db.scalars(select(TencentSyncJob.id).where(TencentSyncJob.status=='pending').order_by(TencentSyncJob.id).limit(100)))
        for job_id in candidates:
            try:
                with self.sessions.begin() as db:
                    hint = db.get(TencentSyncJob, job_id)
                    if hint is None or hint.status!='pending': continue
                    snapshot = hint.snapshot
                    config = self._config_gate(db, snapshot, skip_locked=True)
                    if config is None or config.owner is not None: continue
                    job = db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==job_id).with_for_update().execution_options(populate_existing=True))
                    if job.status!='pending': continue
                    config.generation += 1
                    config.owner, config.active_job_id = self.owner, job.id
                    config.lease_expires_at = now+timedelta(seconds=120)
                    job.status, job.started_at = 'running', now
                    attempt = TencentSyncAttempt(job_id=job.id, attempt_no=1, generation=config.generation, owner=self.owner,
                        status='running', execution_input={**snapshot, 'attempt_no':1,'generation':config.generation,
                            'execution_identity':'current-admin-allowlist'}, started_at=now)
                    db.add(attempt)
                    db.flush()
                    claimed = CostClaim(job.id, config.id, attempt.id, config.generation, self.owner, snapshot, job.request_id)
                log.info('tencent.cost_started job_id=%s attempt_id=%s generation=%s', claimed.job_id, claimed.attempt_id, claimed.generation)
                return claimed
            except TencentError as exc:
                # 被当前资格拒绝的待执行任务不启动出站，也不假称已有实际尝试。
                with self.sessions.begin() as db:
                    config = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.id==snapshot['config_id']).with_for_update())
                    job = db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==job_id).with_for_update())
                    if job and job.status=='pending':
                        job.status, job.error_code, job.finished_at = 'failed', exc.code, now
                log.info('tencent.cost_rejected job_id=%s reason_code=%s', job_id, exc.code)
        return None

    def _owned(self, config, job, attempt, claim, now):
        if (config.owner!=claim.owner or config.generation!=claim.generation or config.active_job_id!=job.id
            or not config.lease_expires_at or config.lease_expires_at<=now or job.status!='running'
            or attempt.status!='running' or attempt.owner!=claim.owner or attempt.generation!=claim.generation):
            raise TencentError('TENCENT_COST_STALE_EXECUTION', '执行资格已过期或被替换')

    def _publish(self, claim, candidate):
        with self.sessions.begin() as db:
            config = self._config_gate(db, claim.snapshot)
            job = db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==claim.job_id).with_for_update())
            attempt = db.scalar(select(TencentSyncAttempt).where(TencentSyncAttempt.id==claim.attempt_id).with_for_update())
            now = self.now()
            self._owned(config, job, attempt, claim, now)
            period = db.scalar(select(TencentCostPeriod).where(TencentCostPeriod.account_id==job.account_id,
                TencentCostPeriod.month==job.month, TencentCostPeriod.currency==claim.snapshot['currency']).with_for_update())
            if period is None:
                period = TencentCostPeriod(account_id=job.account_id, month=job.month, currency=claim.snapshot['currency'],
                    total=candidate['total'], coverage=candidate['coverage'], latest_job_id=job.id, latest_attempt_id=attempt.id)
                db.add(period)
                db.flush()
            else:
                period.total, period.coverage = candidate['total'], candidate['coverage']
                period.latest_job_id, period.latest_attempt_id = job.id, attempt.id
                db.execute(delete(TencentCostItem).where(TencentCostItem.period_id==period.id))
            for index, row in enumerate(candidate['rows'], 1):
                db.add(TencentCostItem(period_id=period.id, row_no=index, **row))
            receipt = {'contract':CONTRACT, 'status':'committed', 'period_id':str(period.id), 'job_id':str(job.id),
                'attempt_id':str(attempt.id), 'month':job.month, 'row_count':len(candidate['rows']),
                'total':format(candidate['total'],'.8f'), 'currency':period.currency, 'request_ids':candidate['request_ids'],
                'coverage':candidate['coverage'], 'committed_at':now.isoformat()+'Z'}
            # 处理器真实返回就是同事务提交回执；不在事务后补写成功历史。
            attempt.execution_output, attempt.status, attempt.finished_at = receipt, 'succeeded', now
            job.status, job.finished_at = 'succeeded', now
            config.last_success_month = job.month
            config.owner, config.active_job_id, config.lease_expires_at = None, None, None
            db.add(ChangeLog(object_type='tencent_cost_period', object_id=str(period.id), source='tencent_worker', actor='admin:'+claim.snapshot['actor_id'],
                before_data=None, after_data={'status':'committed','job_id':str(job.id),'attempt_id':str(attempt.id),'row_count':len(candidate['rows']),'month':job.month}, committed_at=now))
        return receipt

    def _fail(self, claim, code):
        with self.sessions.begin() as db:
            config = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.id==claim.config_id).with_for_update())
            job = db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==claim.job_id).with_for_update())
            attempt = db.scalar(select(TencentSyncAttempt).where(TencentSyncAttempt.id==claim.attempt_id).with_for_update())
            if (config is None or job is None or attempt is None or config.owner!=claim.owner
                or config.generation!=claim.generation or job.status!='running' or attempt.status!='running'):
                return
            now = self.now()
            attempt.status, attempt.error_code, attempt.finished_at = 'failed', code, now
            job.status, job.error_code, job.finished_at = 'failed', code, now
            config.owner, config.active_job_id, config.lease_expires_at = None, None, None
            db.add(ChangeLog(object_type='tencent_job', object_id=str(job.id), source='tencent_worker', actor='admin:'+claim.snapshot['actor_id'],
                before_data={'status':'running'}, after_data={'status':'failed','error_code':code}, committed_at=now))

    def execute(self, claim):
        try:
            with self.sessions.begin() as db:
                config = self._config_gate(db, claim.snapshot)
                job = db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==claim.job_id).with_for_update())
                attempt = db.scalar(select(TencentSyncAttempt).where(TencentSyncAttempt.id==claim.attempt_id).with_for_update())
                self._owned(config,job,attempt,claim,self.now())
            credential = CredentialRegistry(self.settings).resolve(claim.snapshot['credential_ref'])
            gateway = TencentGateway(self.transport, self.sessions, claim.request_id)
            candidate = collect_month(gateway, credential, claim.snapshot)
            result = self._publish(claim, candidate)
        except Exception as exc:
            code = exc.code if isinstance(exc,TencentError) else 'TENCENT_COST_EXECUTION_FAILED'
            # 不记录SQL参数、任意上游异常原文或密钥；失败证据独立提交。
            self._fail(claim, code)
            log.warning('tencent.cost_failed job_id=%s attempt_id=%s reason_code=%s',claim.job_id,claim.attempt_id,code)
            return None
        log.info('tencent.cost_committed job_id=%s attempt_id=%s row_count=%s',claim.job_id,claim.attempt_id,result['row_count'])
        return result

    def run_once(self, now=None):
        claim = self.claim(now)
        if claim is None: return False
        self.execute(claim)
        return True


def main():
    from app.config import get_settings
    from app.dependencies import get_runtime
    runtime, settings = get_runtime(), get_settings()
    if runtime is None: raise SystemExit('云成本worker需要已配置数据库和会话密钥')
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    worker = TencentCostWorker(runtime.sessions, settings)
    log.info('tencent.cost_worker_started')
    try:
        while not stop.is_set():
            if not worker.run_once(): stop.wait(2)
    finally:
        log.info('tencent.cost_worker_stopped')


if __name__=='__main__': main()
