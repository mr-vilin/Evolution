"""固定月度事件与期间批次；父批次仅汇总，不拥有执行租约。"""
from datetime import datetime, timedelta, timezone
import logging
import uuid
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from app.persistence.models import TencentSyncConfig, TencentSyncJob, TencentCostPeriod, ChangeLog, DatasetState
from .access import require_account, require_dataset
from .cost_collector import CONTRACT
from .cost_policy import effective_policy
from .credentials import CredentialRegistry
from .errors import TencentError

log=logging.getLogger('organization.tencent.cost_scheduler')
SHANGHAI=ZoneInfo('Asia/Shanghai')


def shanghai(now):
    return (now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now).astimezone(SHANGHAI)


def shifted(month, delta):
    year,number=map(int,month.split('-')); offset=year*12+number-1+delta
    return f'{offset//12:04d}-{offset%12+1:02d}'


def eligible(now):
    local=shanghai(now)
    return shifted(local.strftime('%Y-%m'),-1 if local.day>=3 else -2)


def scheduled_point(now, execution_time):
    local=shanghai(now)
    hour,minute=map(int,execution_time.split(':'))
    point=local.replace(day=3,hour=hour,minute=minute,second=0,microsecond=0)
    if point>local:
        month=shifted(local.strftime('%Y-%m'),-1)
        point=point.replace(year=int(month[:4]),month=int(month[5:]))
    return point.astimezone(timezone.utc).replace(tzinfo=None)


def next_point(now,execution_time):
    point=scheduled_point(now,execution_time)
    local=shanghai(point); month=shifted(local.strftime('%Y-%m'),1)
    return local.replace(year=int(month[:4]),month=int(month[5:])).astimezone(timezone.utc).replace(tzinfo=None)


def period_snapshot(account, config, epoch, month, *, actor_id, execution_identity, reason=None, source_job_id=None):
    begin=datetime.strptime(month,'%Y-%m'); end=datetime.strptime(shifted(month,1),'%Y-%m')
    return {'handler':CONTRACT,'business':'cost','account_id':account.id,'uin':account.uin,
        'credential_ref':account.credential_ref,'credential_revision':account.credential_revision,
        'config_id':config.id,'config_revision':config.revision,'control_revision':config.control_revision,
        'frequency':config.frequency,'currency':config.currency,'dataset_epoch':epoch,
        'actor_id':actor_id,'execution_identity':execution_identity,'month':month,
        'begin':begin.isoformat()+'+08:00','end_exclusive':end.isoformat()+'+08:00',
        'policy':effective_policy(config.run_policy),'source_job_id':str(source_job_id) if source_job_id is not None else None,
        'rerun_reason':reason,'request_namespace':'manual-period-v1','upstream_params':{'BeginTime':begin.strftime('%Y-%m-%d %H:%M:%S'),
        'EndTime':(end-timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S'),'PeriodType':'month',
        'BillType':'1','FeeType':'cost','Dimensions':'business','NeedConditionValue':'1'}}


def refresh_batch(db,parent_id,now):
    if parent_id is None:return
    parent=db.scalar(select(TencentSyncJob).where(TencentSyncJob.id==parent_id).with_for_update())
    if not parent or parent.kind!='batch':return
    db.flush()
    states=list(db.scalars(select(TencentSyncJob.status).where(TencentSyncJob.parent_job_id==parent_id)))
    if not states:status='no_work'
    elif all(s=='succeeded' for s in states):status='succeeded'
    elif any(s in {'pending','running','retry_wait'} for s in states):status='partial_failed' if any(s=='failed' for s in states) else 'pending'
    else:status='partial_failed' if any(s=='succeeded' for s in states) else 'failed'
    if parent.status!=status:
        db.add(ChangeLog(object_type='tencent_batch',object_id=str(parent.id),source='tencent_worker',actor='system:tencent-monthly',
            before_data={'status':parent.status},after_data={'status':status},committed_at=now))
    parent.status=status
    parent.finished_at=now if not any(s in {'pending','running','retry_wait'} for s in states) else None


def accept_batch(db,account,config,epoch,key,now,*,actor_id,execution_identity,request_id,point=None):
    # 事件身份先于范围计算与配置解释；普通配置修订不能重新创建同一个计划点。
    existing=db.scalar(select(TencentSyncJob).where(TencentSyncJob.config_id==config.id,
        TencentSyncJob.dataset_epoch==epoch,TencentSyncJob.kind=='batch',TencentSyncJob.idempotency_key==key).with_for_update())
    if existing:return existing,False
    latest=eligible(point or now)
    recent=[latest,shifted(latest,-1)]
    complete=set(db.scalars(select(TencentCostPeriod.month).where(TencentCostPeriod.account_id==account.id,
        TencentCostPeriod.currency==config.currency)))
    start=config.schedule_start_month or recent[-1]
    gaps=[]; month=start
    while month<=latest:
        if month not in complete and month not in recent:gaps.append(month)
        month=shifted(month,1)
    # 保留锚点外已接受的失败期间；初始全历史探测由历史回补能力负责。
    failed=db.scalars(select(TencentSyncJob.month).where(TencentSyncJob.config_id==config.id,
        TencentSyncJob.kind=='period',TencentSyncJob.status=='failed',TencentSyncJob.month<=latest)).all()
    gaps=sorted(set(gaps)|{m for m in failed if m not in complete and m not in recent})
    failures=dict(db.execute(select(TencentSyncJob.month,func.count()).where(
        TencentSyncJob.config_id==config.id,TencentSyncJob.kind=='period',TencentSyncJob.parent_job_id.is_not(None),
        TencentSyncJob.dataset_epoch==epoch,TencentSyncJob.status=='failed',
        TencentSyncJob.snapshot['credential_revision'].as_integer()==account.credential_revision
    ).group_by(TencentSyncJob.month)).all())
    blocked=[{'month':m,'reason_code':'TENCENT_MONTH_AUTO_BUDGET_EXHAUSTED'} for m in gaps if failures.get(m,0)>=3]
    blocked_set={item['month'] for item in blocked}
    available_gaps=[m for m in gaps if m not in blocked_set]
    policy=effective_policy(config.run_policy)
    queued=db.scalar(select(func.count()).select_from(TencentSyncJob).where(TencentSyncJob.config_id==config.id,
        TencentSyncJob.kind=='period',TencentSyncJob.dataset_epoch==epoch,TencentSyncJob.status.in_(['pending','running','retry_wait'])))
    available=policy['queue_limit']-queued
    if available<len(recent):raise TencentError('TENCENT_COST_QUEUE_FULL','队列空间不足以受理近期复核，请等待已有任务完成',429)
    selected=recent+available_gaps[:min(12,max(0,available-len(recent)))]
    deferred=[m for m in gaps if m not in selected]
    parent=TencentSyncJob(kind='batch',config_id=config.id,account_id=account.id,dataset_epoch=epoch,
        idempotency_key=key,month=None,status='pending',request_id=request_id,
        snapshot={'business':'cost','currency':config.currency,'dataset_epoch':epoch,'config_revision':config.revision,
            'execution_identity':execution_identity,'actor_id':actor_id,'scheduled_at':point.isoformat()+'Z' if point else None,
            'months':selected,'deferred_months':deferred,'blocked_months':blocked,'latest_eligible_month':latest})
    db.add(parent);db.flush()
    for month in selected:
        snapshot=period_snapshot(account,config,epoch,month,actor_id=actor_id,execution_identity=execution_identity)
        snapshot['request_namespace']='batch-child-v1'
        db.add(TencentSyncJob(kind='period',parent_job_id=parent.id,config_id=config.id,account_id=account.id,
            dataset_epoch=epoch,idempotency_key=f'child:{parent.id}:month:{month}',month=month,status='pending',
            snapshot=snapshot,request_id=request_id,queue_deadline_at=now+timedelta(seconds=policy['queue_deadline_seconds'])))
    db.add(ChangeLog(object_type='tencent_batch',object_id=str(parent.id),source='tencent_scheduler' if point else 'admin',
        actor=actor_id if execution_identity=='system-monthly' else 'admin:'+actor_id,before_data=None,
        after_data={'status':'pending','months':selected,'deferred_count':len(gaps)-(len(selected)-2)},committed_at=now))
    return parent,True


class TencentCostScheduler:
    """与生产 worker 同进程调用；数据库配置锁与事件唯一键实现多节点去重。"""
    def __init__(self,sessions,settings,*,now=None):
        self.sessions,self.settings=sessions,settings
        self.now=now or (lambda:datetime.now(timezone.utc).replace(tzinfo=None))

    def tick(self):
        now=self.now();created=0
        with self.sessions() as db:
            state=db.get(DatasetState,1)
            if not state or state.initialization_status!='complete':return 0
            ids=list(db.scalars(select(TencentSyncConfig.id).where(TencentSyncConfig.is_enabled.is_(True),
                TencentSyncConfig.business=='cost',TencentSyncConfig.frequency=='monthly')))
        for config_id in ids:
            try:
                with self.sessions.begin() as db:
                    epoch=require_dataset(db,lock=True)
                    hint=db.get(TencentSyncConfig,config_id)
                    if hint is None:continue
                    account=require_account(db,hint.account_id,epoch=epoch,lock=True)
                    config=db.scalar(select(TencentSyncConfig).where(TencentSyncConfig.id==config_id).with_for_update().execution_options(populate_existing=True))
                    if not config or not config.is_enabled or config.frequency!='monthly':continue
                    point=scheduled_point(now,config.execution_time)
                    # 执行时刻编辑后同月仍是同一日历事件，查已有日历月标识先定位原事件。
                    key='schedule:monthly:'+shanghai(point).strftime('%Y-%m')
                    existing=db.scalar(select(TencentSyncJob.id).where(TencentSyncJob.config_id==config.id,
                        TencentSyncJob.dataset_epoch==epoch,TencentSyncJob.kind=='batch',TencentSyncJob.idempotency_key==key).with_for_update())
                    if existing is not None:continue
                    CredentialRegistry(self.settings).resolve(account.credential_ref)
                    _,new=accept_batch(db,account,config,epoch,key,now,actor_id='system:tencent-monthly',
                        execution_identity='system-monthly',request_id=str(uuid.uuid4()),point=point)
                    created+=new
            except TencentError as exc:
                log.info('tencent.monthly_deferred config_id=%s reason_code=%s',config_id,exc.code)
        return created
