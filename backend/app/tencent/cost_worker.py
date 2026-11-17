"""独立云成本worker：单配置有界单次尝试，不占组织同步租约。"""
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import logging
import signal
import threading
import uuid
import random
from sqlalchemy import delete, select, func, or_
from app.persistence.models import (AdminAllowlist, DatasetState, TencentSyncConfig, TencentSyncJob,
    TencentSyncAttempt, TencentCostPeriod, TencentCostItem, ChangeLog)
from .access import require_account
from .credentials import CredentialRegistry
from .errors import TencentError
from .gateway import TencentGateway, sdk_transport
from .cost_collector import collect_month, CONTRACT
from .cost_router import utcnow
from .cost_policy import effective_policy
from .cost_scheduler import refresh_batch, TencentCostScheduler

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
        if snapshot.get('execution_identity')=='system-monthly':
            if snapshot['actor_id']!='system:tencent-monthly':raise TencentError('TENCENT_ACTOR_REVOKED','系统执行身份无效')
        else:
            actor = db.scalar(select(AdminAllowlist.open_id).where(AdminAllowlist.open_id==snapshot['actor_id']).with_for_update(read=True))
            if actor is None:
                raise TencentError('TENCENT_ACTOR_REVOKED', '发起管理员已被撤权')
        config = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.id==snapshot['config_id']).with_for_update(skip_locked=skip_locked).execution_options(populate_existing=True))
        if config is None and skip_locked: return None
        if config is None or not config.is_enabled or config.control_revision!=snapshot.get('control_revision',snapshot['config_revision']):
            raise TencentError('TENCENT_COST_CONFIG_CHANGED', '费用配置已关闭或变更')
        if snapshot['handler']!=CONTRACT or config.currency!=snapshot['currency']:
            raise TencentError('TENCENT_COST_CONTRACT_CHANGED', '费用执行契约已变化')
        return config

    def claim(self, now=None):
        now = now or self.now()
        with self.sessions() as db:
            state=db.get(DatasetState,1)
            if state is None or state.initialization_status!='complete':return None
        self.recover(now)
        with self.sessions() as db:
            # 每个可领取配置只贡献最早一条候选；被同配置占用的积压不消耗全局候选窗口。
            candidates = list(db.scalars(select(func.min(TencentSyncJob.id)).join(
                TencentSyncConfig,TencentSyncConfig.id==TencentSyncJob.config_id).where(
                TencentSyncJob.kind=='period',TencentSyncJob.status.in_(['pending','retry_wait']),
                TencentSyncConfig.owner.is_(None),
                or_(TencentSyncConfig.active_job_id.is_(None),TencentSyncConfig.active_job_id==TencentSyncJob.id),
                or_(TencentSyncJob.next_attempt_at.is_(None),TencentSyncJob.next_attempt_at<=now)
            ).group_by(TencentSyncJob.config_id).order_by(func.min(TencentSyncJob.id)).limit(100)))
        for job_id in candidates:
            try:
                with self.sessions.begin() as db:
                    hint = db.get(TencentSyncJob, job_id)
                    if hint is None or hint.status not in {'pending','retry_wait'}: continue
                    snapshot = {**hint.snapshot,'policy':effective_policy(hint.snapshot.get('policy'))}
                    config = self._config_gate(db, snapshot, skip_locked=True)
                    if config is None or config.owner is not None or config.active_job_id not in {None,job_id}: continue
                    job = db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==job_id).with_for_update().execution_options(populate_existing=True))
                    if job.status not in {'pending','retry_wait'}: continue
                    if job.next_attempt_at and job.next_attempt_at>now:continue
                    if job.started_at is None and job.queue_deadline_at and job.queue_deadline_at<=now:
                        job.status,job.error_code,job.finished_at='failed','TENCENT_COST_QUEUE_DEADLINE',now
                        if config.active_job_id==job.id:config.active_job_id=None
                        refresh_batch(db,job.parent_job_id,now)
                        continue
                    if job.deadline_at and job.deadline_at<=now:
                        job.status,job.error_code,job.finished_at='failed','TENCENT_COST_RUN_DEADLINE',now
                        config.active_job_id=None
                        refresh_batch(db,job.parent_job_id,now)
                        continue
                    config.generation += 1
                    config.owner, config.active_job_id = self.owner, job.id
                    config.lease_expires_at = now+timedelta(seconds=effective_policy(snapshot['policy'])['lease_seconds'])
                    if job.started_at is None:
                        job.deadline_at=now+timedelta(seconds=effective_policy(snapshot['policy'])['run_deadline_seconds'])
                    job.status, job.started_at = 'running', job.started_at or now
                    job.next_attempt_at=None
                    attempt_no=(db.scalar(select(func.max(TencentSyncAttempt.attempt_no)).where(TencentSyncAttempt.job_id==job.id)) or 0)+1
                    attempt_request_id=str(uuid.uuid4())
                    attempt = TencentSyncAttempt(job_id=job.id, attempt_no=attempt_no, generation=config.generation, owner=self.owner,
                        request_id=attempt_request_id,
                        status='running', execution_input={**snapshot, 'attempt_no':attempt_no,'generation':config.generation,
                            'trigger_request_id':job.request_id,'attempt_request_id':attempt_request_id,
                            'execution_identity':snapshot.get('execution_identity','current-admin-allowlist')}, started_at=now)
                    db.add(attempt)
                    db.flush()
                    claimed = CostClaim(job.id, config.id, attempt.id, config.generation, self.owner, snapshot, attempt_request_id)
                log.info('tencent.cost_started job_id=%s attempt_id=%s generation=%s', claimed.job_id, claimed.attempt_id, claimed.generation)
                return claimed
            except TencentError as exc:
                # 被当前资格拒绝的待执行任务不启动出站，也不假称已有实际尝试。
                with self.sessions.begin() as db:
                    config = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.id==snapshot['config_id']).with_for_update())
                    job = db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==job_id).with_for_update())
                    if job and job.status in {'pending','retry_wait'}:
                        job.status, job.error_code, job.finished_at = 'failed', exc.code, now
                        if config and config.active_job_id==job.id:
                            config.active_job_id,config.owner,config.lease_expires_at=None,None,None
                        refresh_batch(db,job.parent_job_id,now)
                log.info('tencent.cost_rejected job_id=%s reason_code=%s', job_id, exc.code)
        return None

    def recover(self, now=None):
        """只读出站可在数据库栅栏后重试；未知尝试保留未知，不伪造结束时间。"""
        now=now or self.now()
        with self.sessions() as db:
            state=db.get(DatasetState,1)
            if state is None:return 0
            candidates=list(db.scalars(select(TencentSyncConfig.id).outerjoin(
                TencentSyncJob,TencentSyncJob.id==TencentSyncConfig.active_job_id).where(
                or_(
                    TencentSyncConfig.owner.is_not(None) & or_(TencentSyncConfig.lease_expires_at.is_(None),TencentSyncConfig.lease_expires_at<=now),
                    TencentSyncJob.dataset_epoch!=state.dataset_epoch
                )).order_by(TencentSyncConfig.lease_expires_at,TencentSyncConfig.id).limit(100)))
        recovered=0
        # 同事务原回执是历史权威，不拿当前期间的费用摘要冒充旧处理器返回。
        with self.sessions() as db:
            gaps=list(db.execute(select(TencentSyncJob.id,TencentSyncJob.config_id,TencentSyncAttempt.id,
                TencentSyncAttempt.generation,TencentSyncAttempt.owner,TencentSyncJob.snapshot,TencentSyncAttempt.request_id).join(
                TencentSyncAttempt,TencentSyncAttempt.job_id==TencentSyncJob.id).where(
                TencentSyncJob.status=='succeeded',TencentSyncAttempt.status=='succeeded',TencentSyncJob.commit_receipt.is_not(None),
                or_(TencentSyncAttempt.execution_output.is_(None),func.json_type(TencentSyncAttempt.execution_output)=='NULL',TencentSyncAttempt.return_state!='VALUE')
            ).order_by(TencentSyncJob.id).limit(100)))
        for row in gaps:
            if self.committed_receipt(CostClaim(*row)) is not None:recovered+=1
        for config_id in candidates:
            with self.sessions.begin() as db:
                hint=db.get(TencentSyncConfig,config_id)
                if hint is None:continue
                job_hint=db.get(TencentSyncJob,hint.active_job_id) if hint.active_job_id else None
                code=None
                if job_hint:
                    try:
                        config=self._config_gate(db,job_hint.snapshot)
                    except TencentError as exc:
                        code=exc.code
                        config=db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.id==config_id).with_for_update().execution_options(populate_existing=True))
                else:
                    # 无业务提交，仅回收无任务关联的遗留资格。
                    db.scalar(select(DatasetState).where(DatasetState.id==1).with_for_update(read=True))
                    config=db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.id==config_id).with_for_update().execution_options(populate_existing=True))
                if config is None:continue
                job=db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==config.active_job_id).with_for_update().execution_options(populate_existing=True)) if config.active_job_id else None
                expired=config.owner is not None and (not config.lease_expires_at or config.lease_expires_at<=now)
                if not expired and not code:continue
                config.generation+=1
                config.owner,config.lease_expires_at=None,None
                if job is None or job.status not in {'running','retry_wait','pending'}:
                    config.active_job_id=None
                    recovered+=1
                    continue
                attempt=db.scalar(select(TencentSyncAttempt).where(TencentSyncAttempt.job_id==job.id).order_by(TencentSyncAttempt.attempt_no.desc()).limit(1).with_for_update())
                if attempt and attempt.status=='running':
                    attempt.status,attempt.return_state,attempt.error_code='unknown','UNKNOWN',code or 'TENCENT_COST_EXECUTOR_LOST'
                    attempt.finished_at=None
                    attempt.failure_evidence={'reason_code':attempt.error_code,'observed_at':now.isoformat()+'Z','isolation_generation':config.generation}
                policy=effective_policy(job.snapshot['policy'])
                retry=not code and attempt is not None and attempt.attempt_no<policy['max_attempts'] and (not job.deadline_at or now<job.deadline_at)
                job.error_code=code or 'TENCENT_COST_EXECUTOR_LOST'
                job.status='retry_wait' if retry else 'failed'
                job.next_attempt_at=now.replace(microsecond=0) if retry else None
                job.finished_at=None if retry else now
                if not retry:config.active_job_id=None
                db.add(ChangeLog(object_type='tencent_job',object_id=str(job.id),source='tencent_worker',actor='system:tencent-recovery',
                    before_data={'status':'running'},after_data={'status':job.status,'error_code':job.error_code,'generation':config.generation},committed_at=now))
                refresh_batch(db,job.parent_job_id,now)
                recovered+=1
            log.warning('tencent.cost_recovered config_id=%s reason_code=%s',config_id,code or 'TENCENT_COST_EXECUTOR_LOST')
        return recovered

    def _owned(self, config, job, attempt, claim, now):
        if (config.owner!=claim.owner or config.generation!=claim.generation or config.active_job_id!=job.id
            or not config.lease_expires_at or config.lease_expires_at<=now or job.status!='running'
            or attempt.status!='running' or attempt.owner!=claim.owner or attempt.generation!=claim.generation):
            raise TencentError('TENCENT_COST_STALE_EXECUTION', '执行资格已过期或被替换')
        if job.deadline_at and now>=job.deadline_at:
            raise TencentError('TENCENT_COST_RUN_DEADLINE','执行轮次预算已耗尽')
        if now>=attempt.started_at+timedelta(seconds=effective_policy(claim.snapshot['policy'])['deadline_seconds']):
            raise TencentError('TENCENT_COST_DEADLINE','本次执行预算已耗尽')

    def heartbeat(self, claim):
        """仅当前合法 owner/代次可续租，单次与轮次截止不会被心跳延长。"""
        with self.sessions.begin() as db:
            config=self._config_gate(db,claim.snapshot)
            job=db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==claim.job_id).with_for_update())
            attempt=db.scalar(select(TencentSyncAttempt).where(TencentSyncAttempt.id==claim.attempt_id).with_for_update())
            now=self.now()
            self._owned(config,job,attempt,claim,now)
            policy=effective_policy(claim.snapshot['policy'])
            deadline=min(job.deadline_at,attempt.started_at+timedelta(seconds=policy['deadline_seconds']))
            if now>=deadline:raise TencentError('TENCENT_COST_DEADLINE','本次执行预算已耗尽')
            config.lease_expires_at=min(now+timedelta(seconds=policy['lease_seconds']),deadline)

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
            attempt.return_state='VALUE'
            job.status, job.finished_at, job.commit_receipt = 'succeeded', now, receipt
            config.last_success_month = max(config.last_success_month or job.month,job.month)
            config.owner, config.active_job_id, config.lease_expires_at = None, None, None
            db.add(ChangeLog(object_type='tencent_cost_period', object_id=str(period.id), source='tencent_worker', actor=claim.snapshot['actor_id'] if claim.snapshot.get('execution_identity')=='system-monthly' else 'admin:'+claim.snapshot['actor_id'],
                before_data=None, after_data={'status':'committed','job_id':str(job.id),'attempt_id':str(attempt.id),'row_count':len(candidate['rows']),'month':job.month}, committed_at=now))
            refresh_batch(db,job.parent_job_id,now)
        return receipt

    def _fail(self, claim, code, evidence=None):
        with self.sessions.begin() as db:
            config = db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.id==claim.config_id).with_for_update())
            job = db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==claim.job_id).with_for_update())
            attempt = db.scalar(select(TencentSyncAttempt).where(TencentSyncAttempt.id==claim.attempt_id).with_for_update())
            if (config is None or job is None or attempt is None or config.owner!=claim.owner
                or config.generation!=claim.generation or job.status!='running' or attempt.status!='running'):
                return
            now = self.now()
            attempt.status, attempt.error_code, attempt.finished_at = 'failed', code, now
            attempt.return_state='NOT_RETURNED'
            attempt.failure_evidence=evidence or {'reason_code':code}
            policy=effective_policy(claim.snapshot['policy'])
            delay=min(policy['retry_max_seconds'],policy['retry_base_seconds']*2**(attempt.attempt_no-1))+random.uniform(0,policy['retry_jitter_seconds'])
            retry=(code in {'TENCENT_TIMEOUT','TENCENT_RATE_LIMITED','TENCENT_COST_NOT_READY','TENCENT_UNAVAILABLE'}
                and attempt.attempt_no<policy['max_attempts']
                and (not job.deadline_at or now+timedelta(seconds=delay)<job.deadline_at))
            job.status, job.error_code, job.finished_at = ('retry_wait',code,None) if retry else ('failed',code,now)
            job.next_attempt_at=now+timedelta(seconds=delay) if retry else None
            config.owner, config.lease_expires_at = None, None
            if not retry:config.active_job_id=None
            db.add(ChangeLog(object_type='tencent_job', object_id=str(job.id), source='tencent_worker', actor=claim.snapshot['actor_id'] if claim.snapshot.get('execution_identity')=='system-monthly' else 'admin:'+claim.snapshot['actor_id'],
                before_data={'status':'running'}, after_data={'status':job.status,'error_code':code}, committed_at=now))

            refresh_batch(db,job.parent_job_id,now)

    def committed_receipt(self, claim):
        """只核实原任务原尝试；原始回执同事务存档，缺口仅修归档。"""
        with self.sessions.begin() as db:
            job=db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==claim.job_id).with_for_update())
            attempt=db.scalar(select(TencentSyncAttempt).where(TencentSyncAttempt.id==claim.attempt_id).with_for_update())
            if not (job and attempt and job.status=='succeeded' and attempt.status=='succeeded'
                and attempt.job_id==job.id and attempt.generation==claim.generation):return None
            receipt=job.commit_receipt or attempt.execution_output
            if not receipt or receipt.get('attempt_id')!=str(attempt.id) or receipt.get('job_id')!=str(job.id):return None
            if attempt.execution_output is None or attempt.return_state!='VALUE':
                attempt.execution_output,attempt.return_state=receipt,'VALUE'
                attempt.failure_evidence={**(attempt.failure_evidence or {}),'archive_repaired':True,
                    'archive_repaired_at':self.now().isoformat()+'Z','source':'original-transaction-receipt'}
                log.warning('tencent.cost_archive_repaired job_id=%s attempt_id=%s',job.id,attempt.id)
            return receipt

    def execute(self, claim):
        receipt=self.committed_receipt(claim)
        if receipt is not None:return receipt
        try:
            with self.sessions.begin() as db:
                config = self._config_gate(db, claim.snapshot)
                job = db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==claim.job_id).with_for_update())
                attempt = db.scalar(select(TencentSyncAttempt).where(TencentSyncAttempt.id==claim.attempt_id).with_for_update())
                self._owned(config,job,attempt,claim,self.now())
            credential = CredentialRegistry(self.settings).resolve(claim.snapshot['credential_ref'])
            gateway = TencentGateway(self.transport, self.sessions, claim.request_id)
            heartbeat_stop=threading.Event()
            heartbeat_error=[]
            def keep_alive():
                while not heartbeat_stop.wait(effective_policy(claim.snapshot['policy'])['heartbeat_seconds']):
                    try:self.heartbeat(claim)
                    except Exception as exc:
                        heartbeat_error.append(exc.code if isinstance(exc,TencentError) else 'TENCENT_COST_HEARTBEAT_FAILED')
                        return
            def check():
                if heartbeat_error:raise TencentError(heartbeat_error[0],'执行资格或预算已失效')
                self.heartbeat(claim)
            gateway.check=check
            pulse=threading.Thread(target=keep_alive,name='tencent-cost-heartbeat',daemon=True)
            pulse.start()
            try:candidate = collect_month(gateway, credential, claim.snapshot,check=check)
            finally:
                heartbeat_stop.set()
                pulse.join()

            result = self._publish(claim, candidate)
        except Exception as exc:
            # 提交确认丢失时先用独立连接核实，不把已提交任务转为失败或再次采集。
            receipt=self.committed_receipt(claim)
            if receipt is not None:
                log.warning('tencent.cost_commit_verified job_id=%s attempt_id=%s',claim.job_id,claim.attempt_id)
                return receipt
            code = exc.code if isinstance(exc,TencentError) else 'TENCENT_COST_EXECUTION_FAILED'
            # 不记录SQL参数、任意上游异常原文或密钥；失败证据独立提交。
            self._fail(claim, code, {'reason_code':code,'upstream_request_id':getattr(exc,'upstream_request_id',None),
                'upstream_response_state':getattr(exc,'upstream_response_state','NOT_OBSERVED')})
            log.warning('tencent.cost_failed job_id=%s attempt_id=%s reason_code=%s',claim.job_id,claim.attempt_id,code)
            return None
        log.info('tencent.cost_committed job_id=%s attempt_id=%s row_count=%s',claim.job_id,claim.attempt_id,result['row_count'])
        return result

    def run(self, stop, *, max_concurrency=2, poll_seconds=2):
        """生产循环：跨配置有界并发；停机先停止领取，再等待有界执行收尾。"""
        if not isinstance(max_concurrency,int) or not 1<=max_concurrency<=8:
            raise ValueError('max_concurrency must be between 1 and 8')
        with ThreadPoolExecutor(max_workers=max_concurrency,thread_name_prefix='tencent-cost') as pool:
            active=set()
            scheduler=TencentCostScheduler(self.sessions,self.settings,now=self.now)
            while not stop.is_set():
                try:scheduler.tick()
                except Exception:log.error('tencent.monthly_schedule_unavailable')
                for future in list(active):
                    if future.done():
                        active.remove(future)
                        try:future.result()
                        except Exception:
                            # 持久化故障留给租约恢复；不输出包含参数的异常原文。
                            log.error('tencent.cost_executor_unavailable')
                while len(active)<max_concurrency and not stop.is_set():
                    try:claim=self.claim()
                    except Exception:
                        log.error('tencent.cost_claim_unavailable')
                        break
                    if claim is None:break
                    active.add(pool.submit(self.execute,claim))
                stop.wait(poll_seconds)
            for future in active:
                try:future.result()
                except Exception:log.error('tencent.cost_shutdown_pending_recovery')

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
        worker.run(stop)
    finally:
        log.info('tencent.cost_worker_stopped')


if __name__=='__main__': main()
