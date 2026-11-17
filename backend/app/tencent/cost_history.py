"""历史发现检查点与实际日/月范围；历史起点保持未知，费用事实是覆盖权威。"""
from datetime import datetime, timedelta, timezone
from collections import Counter
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, func
from app.persistence.models import TencentSyncJob, TencentCostPeriod, TencentSyncAttempt, ChangeLog
from .cost_policy import effective_policy
from .errors import TencentError

ACTIVE={'pending','running','retry_wait'}
SYSTEM={'system-monthly','system-daily','system-weekly'}

class HistoryProgress(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_version: Literal[1]=1
    origin_status: Literal['unknown']='unknown'
    first_bill_period: None=None
    earlier_history_unknown: Literal[True]=True
    sequence: int=Field(default=0,ge=0,le=2147483647)
    last_batch_id: str | None=Field(default=None,pattern=r'^[1-9][0-9]{0,19}$')
    target_begin: str | None=Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    target_end_exclusive: str | None=Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    source_basis: Literal['cost-analysis-public-window-v1']='cost-analysis-public-window-v1'

    @model_validator(mode='after')
    def valid_target(self):
        if bool(self.target_begin)!=bool(self.target_end_exclusive):raise ValueError('发现目标起止须同时存在')
        if self.target_begin:
            begin=datetime.strptime(self.target_begin,'%Y-%m-%d');end=datetime.strptime(self.target_end_exclusive,'%Y-%m-%d')
            if begin>=end or self.target_begin<'1970-01-01':raise ValueError('发现目标须是有效有序期间')
        return self

    @model_validator(mode='after')
    def valid_bounds(self):
        if (self.target_begin is None)!=(self.target_end_exclusive is None):raise ValueError('历史目标边界必须成对')
        if self.target_begin:
            begin=datetime.strptime(self.target_begin,'%Y-%m-%d').date()
            end=datetime.strptime(self.target_end_exclusive,'%Y-%m-%d').date()
            if begin>=end or begin.isoformat()!=self.target_begin or end.isoformat()!=self.target_end_exclusive:
                raise ValueError('历史目标边界无效')
        return self


def checkpoint(config,**changes):
    progress=HistoryProgress.model_validate(config.history_progress or {})
    config.history_progress=HistoryProgress.model_validate({**progress.model_dump(),**changes}).model_dump()
    return config.history_progress


def window(now):
    from .cost_scheduler import shanghai,shifted,eligible
    local=shanghai(now)
    # 完整旧月保留月粒度；边界月也按月查，避免把月额拆成日额。
    return {'day_start':shifted(local.strftime('%Y-%m'),-5)+'-01',
        'month_start':shifted(local.strftime('%Y-%m'),-12),
        'end_exclusive':local.date().isoformat(),'latest_month':eligible(now),
        'basis':'cost-analysis-public-window-v1',
        'limitation':'官方日6个月/月12个月为来源能力，不是账号起点；日边界月用原月粒度探测，更早历史未知'}


def scope(key):
    return {'period_key':key,'granularity':'month' if len(key)==7 else 'day','month':key[:7]}


def automatic_reference(db,config,now):
    """发现目标沿用实际受理的计划点；poll及普通时刻编辑不产生新周期。"""
    if config.frequency not in {'daily','weekly','monthly'}:return now
    scheduled=db.scalar(select(TencentSyncJob).where(TencentSyncJob.config_id==config.id,
        TencentSyncJob.kind=='batch',TencentSyncJob.idempotency_key.like('schedule:'+config.frequency+':%'))
        .order_by(TencentSyncJob.id.desc()).limit(1))
    if scheduled and scheduled.snapshot.get('scheduled_at'):
        return datetime.fromisoformat(scheduled.snapshot['scheduled_at'].replace('Z','+00:00'))
    from .cost_scheduler import scheduled_point
    return scheduled_point(now,config.execution_time,config.frequency)


def targets(config,now):
    from .cost_scheduler import shifted
    w=window(now);keys=[]
    if config.frequency in {'daily','weekly'}:
        day=datetime.fromisoformat(w['day_start']).date();end=datetime.fromisoformat(w['end_exclusive']).date()
        while day<end:keys.append(day.isoformat());day+=timedelta(days=1)
        month=w['month_start']
        while month<w['day_start'][:7]:keys.append(month);month=shifted(month,1)
    else:
        month=w['month_start']
        while month<=w['latest_month']:keys.append(month);month=shifted(month,1)
    return sorted(keys,reverse=True)


def facts(db,config,account,now,*,lock=False):
    query=select(TencentCostPeriod).where(TencentCostPeriod.account_id==account.id,TencentCostPeriod.currency==config.currency)
    periods=list(db.scalars(query.with_for_update(read=True) if lock else query))
    valid=[p for p in periods if p.coverage.get('status')=='complete' and p.coverage.get('bill_type')=='1'
        and p.coverage.get('fee_type')=='cost' and p.coverage.get('dimensions')=='business']
    query=select(TencentSyncJob).where(TencentSyncJob.config_id==config.id,TencentSyncJob.kind=='period').order_by(TencentSyncJob.id)
    jobs=list(db.scalars(query.with_for_update(read=True) if lock else query))
    successes={p.period_key for p in valid};months={p.month for p in valid if p.granularity=='month'}
    def covered(k):
        if k in successes or k[:7] in months:return True
        if len(k)==7:
            from .cost_scheduler import shifted
            d=datetime.fromisoformat(k+'-01').date();end=datetime.fromisoformat(shifted(k,1)+'-01').date()
            return all((d+timedelta(days=i)).isoformat() in successes for i in range((end-d).days))
        return False
    latest={j.snapshot.get('period_key',j.month):j for j in jobs}
    # 原 epoch 不改变历史自动失败证据，人工失败不扣自动预算。
    counts=Counter((j.snapshot.get('period_key',j.month)) for j in jobs if j.status=='failed'
        and j.snapshot.get('execution_identity') in SYSTEM
        and j.snapshot.get('credential_revision')==account.credential_revision
        and j.error_code not in {'DATASET_CHANGED','TENCENT_EPOCH_CHANGED','TENCENT_COST_CONFIG_CHANGED','INITIALIZATION_INCOMPLETE','TENCENT_CREDENTIAL_CHANGED','TENCENT_ACCOUNT_UNAVAILABLE','TENCENT_ACTOR_REVOKED','TENCENT_COST_CONTRACT_CHANGED'})
    pending={j.snapshot.get('period_key',j.month) for j in jobs if j.status in ACTIVE and j.dataset_epoch==account._history_epoch} if hasattr(account,'_history_epoch') else set()
    return valid,jobs,covered,latest,counts,pending


def category(code):
    if code=='TENCENT_COST_NOT_READY':return 'not_ready'
    if code=='TENCENT_COST_ZERO_UNCONFIRMED':return 'zero_unconfirmed'
    if code in {'TENCENT_PERMISSION_DENIED','TENCENT_FORBIDDEN'}:return 'permission_denied'
    if code in {'TENCENT_TIMEOUT','TENCENT_RATE_LIMITED','TENCENT_UNAVAILABLE'}:return 'transient'
    if code in {'TENCENT_INVALID_PARAMETER','TENCENT_PARAMETER_INVALID'}:return 'parameter_invalid'
    return 'upstream_failed'


def history_data(db,config,account,now):
    reference=automatic_reference(db,config,now) if config else now
    w=window(reference)
    if config is None:
        return {'origin_status':'unknown','first_bill_period':None,'earlier_history_unknown':True,'source_window':w,
            'target_period_count':0,'covered_period_count':0,'earliest_success_period':None,'last_success_at':None,
            'continuous_coverage':None,'recent':{'required_count':0,'covered_count':0},'gaps':[],'unexplored':[],
            'pending_count':0,'discovery_status':'pending'}
    HistoryProgress.model_validate(config.history_progress or {})
    periods,jobs,covered,latest,counts,_=facts(db,config,account,now)
    full_months={p.month for p in periods if p.granularity=='month'}
    wanted=sorted({k[:7] if k[:7] in full_months else k for k in targets(config,reference)},reverse=True);gaps=[];unexplored=[]
    # 也展示人工探测过的窗口外失败；不冒充已确认不可查询。
    for k in sorted(set(wanted)|set(latest),reverse=True):
        if covered(k):continue
        job=latest.get(k)
        if job is None:
            if k in wanted:unexplored.append(scope(k))
        elif job.status=='failed':
            gaps.append({**scope(k),'reason_code':job.error_code,'category':category(job.error_code),
                'last_attempt_at':job.finished_at.isoformat()+'Z' if job.finished_at else None,
                'automatic_failures':counts[k],'automatic_paused':counts[k]>=3,
                'outside_known_source_window':k<w['month_start']})
        elif job.status in ACTIVE and job.dataset_epoch!=getattr(account,'_history_epoch',job.dataset_epoch):
            if k in wanted:unexplored.append(scope(k))
    intervals=[]
    from .cost_scheduler import shifted,shanghai
    for p in periods:
        begin=p.period_key+'-01' if p.granularity=='month' else p.period_key
        end=shifted(p.month,1)+'-01' if p.granularity=='month' else (datetime.fromisoformat(begin)+timedelta(days=1)).date().isoformat()
        intervals.append((begin,end))
    merged=[]
    for begin,end in sorted(intervals):
        if merged and begin<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((begin,end))
    cutoff=(shifted(w['latest_month'],1)+'-01') if config.frequency not in {'daily','weekly'} else w['end_exclusive']
    continuous=next(({'begin':b,'end_exclusive':cutoff} for b,e in reversed(merged) if b<cutoff<=e),None)
    if config.frequency in {'daily','weekly'}:
        recent_begin=shifted(shanghai(reference).strftime('%Y-%m'),-1)+'-01';recent=[k for k in wanted if k[:7]>=recent_begin[:7]]
    else:recent=wanted[:2]
    last=max((j.finished_at for j in jobs if j.status=='succeeded' and j.finished_at),default=None)
    return {'origin_status':'unknown','first_bill_period':None,'earlier_history_unknown':True,'source_window':w,
        'target_period_count':len(wanted),'covered_period_count':sum(covered(k) for k in wanted),
        'earliest_success_period':min((p.period_key for p in periods),default=None),'last_success_at':last.isoformat()+'Z' if last else None,
        'continuous_coverage':continuous,'recent':{'required_count':len(recent),'covered_count':sum(covered(k) for k in recent)},
        'gaps':gaps,'unexplored':unexplored,'pending_count':sum(j.status in ACTIVE and j.dataset_epoch==getattr(account,'_history_epoch',j.dataset_epoch) for j in jobs),
        'discovery_status':'known_window_probed' if not unexplored and not any(j.status in ACTIVE and j.dataset_epoch==getattr(account,'_history_epoch',j.dataset_epoch) for j in jobs) else 'partial' if periods else 'pending'}


def history_capacity(config,queued=0,*,policy=None,frequency=None):
    policy=policy or effective_policy(config.run_policy)
    limit=min(policy['queue_limit'],effective_policy(config.run_policy)['queue_limit'])
    reserve=min(62 if (frequency or config.frequency) in {'daily','weekly'} else 2,limit//2)
    return max(0,limit-queued-reserve)


def frozen_period(template,key):
    from .cost_scheduler import shifted
    begin=datetime.fromisoformat(key+'-01' if len(key)==7 else key)
    end=datetime.fromisoformat(shifted(key,1)+'-01') if len(key)==7 else begin+timedelta(days=1)
    return {**template,'month':key[:7],'period_key':key,'granularity':'month' if len(key)==7 else 'day',
        'begin':begin.isoformat()+'+08:00','end_exclusive':end.isoformat()+'+08:00',
        'month_zero_eligible':key[:7]>=template['source_window']['month_start'],
        'upstream_params':{**template['upstream_params'],'BeginTime':begin.strftime('%Y-%m-%d %H:%M:%S'),
            'EndTime':(end-timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S'),'PeriodType':'month' if len(key)==7 else 'day'}}


def append_children(db,parent,account,config,epoch,keys,now,*,purpose):
    from .cost_scheduler import period_snapshot,shifted,shanghai,eligible
    template=parent.snapshot.get('execution_template')
    policy=template['policy'] if template else effective_policy(config.run_policy)
    for k in keys:
        s=scope(k)
        if template:snapshot=frozen_period(template,k)
        else:
            snapshot=period_snapshot(account,config,epoch,s['month'],actor_id=parent.snapshot['actor_id'],
                execution_identity=parent.snapshot['execution_identity'],granularity=s['granularity'],period_key=k)
            snapshot.update(source_window=window(now),month_zero_eligible=k[:7]>=window(now)['month_start'])
        recent_begin=(shifted(shanghai(now).strftime('%Y-%m'),-1)+'-01') if config.frequency in {'daily','weekly'} else shifted(eligible(now),-1)
        old=k<recent_begin
        snapshot.update(request_namespace='batch-child-v1',purpose=purpose)
        db.add(TencentSyncJob(kind='period',parent_job_id=parent.id,config_id=config.id,account_id=account.id,
            dataset_epoch=epoch,idempotency_key=f"child:{parent.id}:{s['granularity']}:{k}",month=s['month'],status='pending',
            priority=20 if old else 0,snapshot=snapshot,request_id=parent.request_id,
            queue_deadline_at=now+timedelta(seconds=policy['queue_deadline_seconds'])))


def continue_history(db,account,config,epoch,now,request_id,*,allow_discovery=True):
    """配置锁内持久事件；一片结束才推进，不以poll次数绕过失败预算。"""
    from .cost_scheduler import refresh_batch
    account._history_epoch=epoch
    active=db.scalar(select(TencentSyncJob.id).where(TencentSyncJob.config_id==config.id,TencentSyncJob.dataset_epoch==epoch,
        TencentSyncJob.kind=='period',TencentSyncJob.status.in_(ACTIVE)).limit(1).with_for_update(read=True))
    if active is not None:return False
    # 人工全范围的延期片是原父事件，范围和授权身份均不改变。
    manual=db.scalar(select(TencentSyncJob).where(TencentSyncJob.config_id==config.id,TencentSyncJob.dataset_epoch==epoch,
        TencentSyncJob.kind=='batch',TencentSyncJob.snapshot['request_namespace'].as_string().in_(['manual-range-v1','recent-review-v1']),
        TencentSyncJob.finished_at.is_(None)).order_by(TencentSyncJob.id).with_for_update())
    if manual and manual.snapshot.get('deferred_periods'):
        remaining=manual.snapshot['deferred_periods'];template=manual.snapshot['execution_template']
        budget=history_capacity(config,policy=template['policy'],frequency=template['frequency'])
        if not budget:return False
        keys=remaining[:min(31,budget)]
        append_children(db,manual,account,config,epoch,keys,now,purpose='manual-range' if manual.snapshot['request_namespace']=='manual-range-v1' else 'recent-review')
        admitted=manual.snapshot['periods']+[scope(k) for k in keys]
        manual.snapshot={**manual.snapshot,'periods':admitted,
            'months':sorted({p['month'] for p in admitted}),'deferred_periods':remaining[len(keys):]}
        if 'deferred_months' in manual.snapshot:
            manual.snapshot={**manual.snapshot,'deferred_months':remaining[len(keys):]}
        refresh_batch(db,manual.id,now)
        return True
    if not allow_discovery:return False
    periods,jobs,covered,latest,counts,_=facts(db,config,account,now,lock=True)
    reference=automatic_reference(db,config,now)
    wanted=targets(config,reference)
    missing=[k for k in wanted if not covered(k)]
    # 首次探测优先于重试旧洞。自动总预算跨epoch/重启保留，手动可明确重探。
    fresh=[k for k in missing if k not in latest or latest[k].dataset_epoch!=epoch and latest[k].status in ACTIVE]
    retries=[k for k in missing if k not in fresh and latest[k].status=='failed' and counts[k]<3]
    policy=effective_policy(config.run_policy)
    budget=min(31 if config.frequency in {'daily','weekly'} else 12,history_capacity(config))
    keys=(fresh+retries)[:budget]
    if not keys:return False
    state=checkpoint(config);sequence=state['sequence']+1
    identity='system-'+(config.frequency if config.frequency in {'daily','weekly','monthly'} else 'monthly')
    parent=TencentSyncJob(kind='batch',config_id=config.id,account_id=account.id,dataset_epoch=epoch,
        idempotency_key=f'history:{epoch}:{sequence}',status='pending',request_id=request_id,
        snapshot={'business':'cost','currency':config.currency,'execution_identity':identity,'actor_id':'system:tencent-'+identity.removeprefix('system-'),
            'request_namespace':'history-discovery-v1','purpose':'history-discovery','periods':[scope(k) for k in keys],
            'months':sorted({k[:7] for k in keys}),'deferred_periods':[k for k in missing if k not in keys],
            'source_window':window(reference)})
    db.add(parent);db.flush()
    append_children(db,parent,account,config,epoch,keys,now,purpose='history-discovery')
    checkpoint(config,sequence=sequence,last_batch_id=str(parent.id),target_begin=window(reference)['month_start']+'-01',target_end_exclusive=window(reference)['end_exclusive'])
    db.add(ChangeLog(object_type='tencent_batch',object_id=str(parent.id),source='tencent_scheduler',actor=parent.snapshot['actor_id'],
        after_data={'status':'pending','purpose':'history-discovery','period_count':len(keys)},committed_at=now))
    return True


class RangeBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scope: Literal['range','all']
    start_date: str | None=Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    end_date: str | None=Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    idempotency_key: str=Field(min_length=1,max_length=112,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$',strict=True)
    preview_token: str | None=Field(default=None,min_length=64,max_length=64)

    @model_validator(mode='after')
    def valid_range(self):
        if self.scope=='all':
            if self.start_date is not None or self.end_date is not None:raise ValueError('全部历史不接受自定义日期')
        else:
            if not self.start_date or not self.end_date:raise ValueError('请选择开始与结束日期')
            start=datetime.strptime(self.start_date,'%Y-%m-%d').date();end=datetime.strptime(self.end_date,'%Y-%m-%d').date()
            if start.isoformat()!=self.start_date or end.isoformat()!=self.end_date or self.start_date<'1970-01-01' or start>end or (end-start).days>3660:
                raise ValueError('指定期间最多十年且起止日期须有效')
        return self


def request_intent(body):
    return {'scope':body.scope,'start_date':body.start_date,'end_date':body.end_date}


def range_preview(db,account,config,epoch,body,now):
    from .cost_scheduler import shifted
    w=window(now);months=set(db.scalars(select(TencentCostPeriod.month).where(TencentCostPeriod.account_id==account.id,
        TencentCostPeriod.currency==config.currency,TencentCostPeriod.granularity=='month')))
    expanded=False;reasons=[];not_due=[];keys=set()
    if body.scope=='all':keys=set(targets(config,now))
    else:
        day=datetime.fromisoformat(body.start_date).date();end=datetime.fromisoformat(body.end_date).date()
        while day<=end:
            k=day.isoformat();m=k[:7]
            if config.frequency not in {'daily','weekly'} or m in months or k<w['day_start']:
                target=m
                if k!=m+'-01' or body.end_date<shifted(m,1)+'-01':expanded=True
                reason='existing_complete_month' if m in months else 'outside_daily_source_window' if k<w['day_start'] else 'monthly_mode'
                if reason not in reasons:reasons.append(reason)
                if m>w['latest_month']:
                    if m not in not_due:not_due.append(m)
                else:keys.add(target)
            elif k>=w['end_exclusive']:
                not_due.append(k)
            else:keys.add(k)
            day+=timedelta(days=1)
    # all也必须把已存整月合并，不能拆日重复计费。
    keys={k[:7] if k[:7] in months else k for k in keys}
    ordered=sorted(keys,reverse=True)
    queued=db.scalar(select(func.count()).select_from(TencentSyncJob).where(TencentSyncJob.config_id==config.id,
        TencentSyncJob.dataset_epoch==epoch,TencentSyncJob.kind=='period',TencentSyncJob.status.in_(ACTIVE)))
    capacity=history_capacity(config,queued)
    count=min(31,capacity,len(ordered))
    ranges=[]
    for k in ordered:
        begin=k+'-01' if len(k)==7 else k
        end=shifted(k,1)+'-01' if len(k)==7 else (datetime.fromisoformat(k)+timedelta(days=1)).date().isoformat()
        reason='stored_month' if k[:7] in months else 'source_month_only' if len(k)==7 and config.frequency in {'daily','weekly'} else None
        ranges.append({**scope(k),'begin':begin+'T00:00:00+08:00','end_exclusive':end+'T00:00:00+08:00','expansion_reason':reason})
    if body.scope=='range':
        requested_end=(datetime.fromisoformat(body.end_date)+timedelta(days=1)).date().isoformat()
        expanded=any(r['begin'][:10]<body.start_date or r['end_exclusive'][:10]>requested_end for r in ranges)
    payload={'periods':ranges,'requested_scope':request_intent(body),'expanded':expanded,
        'expansion_reasons':reasons,'not_due':not_due,'outside_known_source_window':[k for k in ordered if k[:7]<w['month_start']],
        'total_count':len(ordered),'accepted_count':count,'deferred_periods':ordered[count:],
        'source_window':w,'origin_status':'unknown','earlier_history_unknown':True}
    # 这是公开范围一致性标识，不含身份/凭据，也不是访问令牌。
    token=hashlib.sha256(json.dumps({'preview':payload,'epoch':epoch,'revision':config.revision,
        'credential_revision':account.credential_revision},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {**payload,'preview_token':token}


def accept_range(db,account,config,epoch,body,now,*,actor_id,request_id):
    from .cost_scheduler import refresh_batch
    key='manual-range:'+hashlib.sha256(body.idempotency_key.encode()).hexdigest()
    existing=db.scalar(select(TencentSyncJob).where(TencentSyncJob.config_id==config.id,
        TencentSyncJob.dataset_epoch==epoch,TencentSyncJob.kind=='batch',TencentSyncJob.idempotency_key==key).with_for_update())
    if existing:
        if existing.snapshot.get('requested_scope')!=request_intent(body):
            raise TencentError('TENCENT_IDEMPOTENCY_CONFLICT','该请求标识已用于其他重拉范围',409)
        return existing
    preview=range_preview(db,account,config,epoch,body,now)
    if body.preview_token and body.preview_token!=preview['preview_token']:
        raise TencentError('TENCENT_RANGE_PREVIEW_CHANGED','配置、世代或实际范围已变化，请重新预览',409)
    keys=[p['period_key'] for p in preview['periods']];selected=keys[:preview['accepted_count']]
    if keys and not selected:raise TencentError('TENCENT_COST_QUEUE_FULL','请等待队列空间后重新预览，已为近期复核保留容量',429)
    from .cost_scheduler import period_snapshot
    template=period_snapshot(account,config,epoch,keys[0][:7] if keys else window(now)['latest_month'],actor_id=actor_id,execution_identity='current-admin-allowlist')
    template.update(source_window=preview['source_window'])
    parent=TencentSyncJob(kind='batch',config_id=config.id,account_id=account.id,dataset_epoch=epoch,
        idempotency_key=key,status='pending' if keys else 'no_work',request_id=request_id,finished_at=None if keys else now,
        snapshot={**preview,'execution_template':template,'request_namespace':'manual-range-v1','business':'cost','currency':config.currency,
            'actor_id':actor_id,'execution_identity':'current-admin-allowlist','requested_periods':preview['periods'],
            'periods':[scope(k) for k in selected],'deferred_periods':keys[len(selected):],
            'months':sorted({k[:7] for k in selected})})
    db.add(parent);db.flush()
    append_children(db,parent,account,config,epoch,selected,now,purpose='manual-range')
    db.add(ChangeLog(object_type='tencent_batch',object_id=str(parent.id),source='admin',actor='admin:'+actor_id,
        after_data={'status':parent.status,'purpose':'manual-range','period_count':len(keys),'accepted_count':len(selected)},committed_at=now))
    return parent
