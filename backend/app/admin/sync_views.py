"""同步中心只读视图：采集进度与已提交对象变更分别呈现。"""
import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, literal, select, union

from app.persistence.models import ChangeLog, Department, Employee, LoginIdentity, PendingFact, SyncJob, SyncJobDetail, SystemSetting
from app.web import utc_datetime


def sync_summary(db):
    latest_job = db.execute(
        select(SyncJob.id, SyncJob.status).order_by(SyncJob.create_time.desc(), SyncJob.id.desc()).limit(1)
    ).one_or_none()
    pending_objects = union(
        select(PendingFact.object_type, PendingFact.source_id),
        select(literal('department'), Department.id).where(Department.sync_quality == 'pending_verification'),
        select(literal('employee'), Employee.id).where(Employee.sync_quality == 'pending_verification'),
    ).subquery()
    return {
        'latest_job': {'job_id': latest_job.id, 'status': latest_job.status} if latest_job else None,
        'pending_object_count': db.scalar(select(func.count()).select_from(pending_objects)),
    }


def progress_records(db, jobs):
    keys = ['job_progress:' + job.id for job in jobs]
    if not keys:
        return {}
    return {row.setting_key.removeprefix('job_progress:'): json.loads(row.value)
            for row in db.scalars(select(SystemSetting).where(SystemSetting.setting_key.in_(keys)))}


def job_progress(row, observation=None):
    # 重试前的计数不能冒充本次采集；仅使用本次开始之后保存的快照。
    progress = observation or {}
    observed = progress.get('observed_at')
    if not row.started_at or not observed or datetime.fromisoformat(observed) < row.started_at.replace(tzinfo=None):
        progress = {}
    if row.status == 'succeeded':
        processed = (row.success_count or 0) + (row.failure_count or 0)
        total = row.total_count
        kind = 'published'
    else:
        processed = progress.get('departments_processed', 0) + progress.get('employees_processed', 0)
        totals = (progress.get('departments_total'), progress.get('employees_total'))
        total = sum(totals) if all(value is not None for value in totals) else None
        kind = 'collection'
    return {'processed_count': processed, 'progress_total': total, 'progress_known': total is not None,
            'progress_kind': kind, 'collection_progress': progress or None}


def add_job_context(db, rows, summaries):
    records = progress_records(db, rows)
    roots = {row.root_department_id for row in rows if row.root_department_id}
    names = dict(db.execute(select(Department.id, Department.name).where(Department.id.in_(roots))).all()) if roots else {}
    actors = {row.requested_by.removeprefix('admin:') for row in rows}
    identities = dict(db.execute(select(LoginIdentity.open_id, LoginIdentity.user_id).where(LoginIdentity.open_id.in_(actors))).all()) if actors else {}
    user_ids = actors | set(identities.values())
    people = list(db.scalars(select(Employee).where((Employee.id.in_(user_ids)) | (Employee.open_id.in_(actors))))) if actors else []
    person_names = {identifier: person.name for person in people for identifier in (person.id, person.feishu_user_id, person.open_id) if identifier}
    for row, summary in zip(rows, summaries):
        summary.update(job_progress(row, records.get(row.id)))
        summary['root_department_id'] = row.root_department_id
        summary['root_department_name'] = names.get(row.root_department_id)
        source = row.trigger_source or row.requested_by
        automatic = row.requested_by in ('schedule', 'listener:startup', 'listener:reconnected', 'system', 'startup')
        summary['trigger_label'] = {'schedule': '每日定时', 'listener:startup': '系统启动',
            'listener:reconnected': '连接恢复', 'system': '系统触发', 'startup': '系统启动',
            'agent': '智能体调用', 'mcp': '智能体调用', 'human_agent': '智能体调用', 'ci_agent': '流水线调用',
            'coverage': '覆盖范围重新确认', 'api': 'API 调用', 'manual': '手动', 'admin': '手动'}.get(source, '手动' if row.requested_by.startswith('admin:') or row.type == 'initialize' else '其他触发')
        if row.retry_count and row.requested_by.startswith('admin:'):
            summary['trigger_label'] = '手动重试'
        actor = row.requested_by.removeprefix('admin:')
        summary['executor_name'] = '系统' if automatic else person_names.get(identities.get(actor, actor), person_names.get(actor, actor))
    return summaries


def job_details(db, job_id):
    details = list(db.scalars(select(SyncJobDetail).where(SyncJobDetail.job_id == job_id).order_by(SyncJobDetail.id)))
    changes = defaultdict(list)
    for log in db.scalars(select(ChangeLog).where(ChangeLog.job_id == job_id,
                            ChangeLog.object_type.in_(['employee', 'department', 'membership'])).order_by(ChangeLog.id)):
        key = ('employee' if log.object_type == 'membership' else log.object_type, log.object_id)
        changes[key].append({'id': log.id, 'object_type': log.object_type,
                             'action': 'create' if log.before_data is None else 'delete' if log.after_data is None else 'update',
                             'before': log.before_data, 'after': log.after_data, 'committed_at': utc_datetime(log.committed_at)})
    result = []
    for detail in details:
        logs = changes.pop((detail.object_type, detail.object_id), [])
        own_logs = [log for log in logs if log['object_type'] == detail.object_type]
        action = ('failed' if detail.status == 'failed' else
                  'create' if any(log['action'] == 'create' for log in own_logs) else
                  'delete' if any(log['action'] == 'delete' for log in own_logs) else
                  'update' if logs else 'unchanged' if detail.status == 'succeeded' else 'pending')
        result.append({'id': detail.id, 'object_type': detail.object_type, 'object_id': detail.object_id,
                       'object_name': detail.object_name, 'status': detail.status, 'action': action,
                       'error_code': detail.error_code, 'error_message': detail.error_message,
                       'attempt': detail.attempt, 'started_at': utc_datetime(detail.started_at),
                       'finished_at': utc_datetime(detail.finished_at), 'change_log_id': detail.change_log_id,
                       'changes': logs})
    # 覆盖降级、关系失效等也可能仅产生日志，不丢弃这些与任务关联的变更。
    for (kind, identifier), logs in changes.items():
        result.append({'id': f'log-{logs[0]["id"]}', 'object_type': kind, 'object_id': identifier,
                       'object_name': next((log['after'].get('name') for log in logs if isinstance(log['after'], dict) and log['after'].get('name')), None),
                       'status': 'succeeded', 'action': 'update', 'changes': logs})
    return result


def initialization_date(db):
    from app.initialization.service import load_flow
    completed = load_flow(db).get('completed_at')
    if completed:
        return utc_datetime(datetime.fromisoformat(completed))
    finished = db.scalar(select(SyncJob.finished_at).where(SyncJob.type == 'initialize',
                         SyncJob.status == 'succeeded').order_by(SyncJob.finished_at).limit(1))
    return utc_datetime(finished)
