"""同步中心查询与分批发布的行为验收；可复用到独立 MySQL。"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import json

from sqlalchemy import select

from test_sync_persistence import sessions
from app.persistence.models import DatasetState, Department, Employee, SyncJob, SyncJobDetail, ChangeLog, SystemSetting, WorkerLease, SyncStaging


def assert_batches_survive_later_collection_failure(sessions):
    from app.sync.worker import Worker, utcnow
    from app.sync.collector import Collector
    from app.persistence.repositories import SqlSyncJobRepository
    now = utcnow()
    with sessions.begin() as db:
        if db.get(WorkerLease, 1) is None:
            db.add(WorkerLease(id=1, generation=0))
        db.merge(SystemSetting(key='reconcile_schedule', value=json.dumps({'enabled': False, 'local_time': '03:00', 'timezone': 'Asia/Shanghai'})))
    job, _ = SqlSyncJobRepository(sessions).submit('full', None, 'admin:operator', now)
    with sessions.begin() as db:
        db.get(SyncJob, job.id).attempt = 5
        version = db.get(DatasetState, 1).data_version
        last_full = db.get(DatasetState, 1).last_full_sync_at

    class API:
        def pages(self, resource, **params):
            if resource == 'scopes':
                yield {'department_ids': [], 'user_ids': [f'batch-user-{i:03}' for i in range(120)], 'group_ids': []}
            else:
                yield {'items': []}

        def detail(self, kind, identifier):
            if identifier == 'batch-user-060':
                with sessions() as db:
                    assert db.get(Employee, 'batch-user-001') is not None
                    assert db.get(SyncJob, job.id).status == 'running'
                    assert db.get(DatasetState, 1).data_version > version
                    assert not list(db.scalars(select(SyncStaging).where(SyncStaging.job_id == job.id)))
                raise ConnectionError('simulated interruption after a committed batch')
            return {'user_id': identifier, 'name': identifier, 'department_ids': [], 'status': {'is_resigned': False}}

    worker = Worker(sessions, Collector(API()), owner='batch-worker')
    assert worker.acquire(utcnow())
    worker.step()
    with sessions() as db:
        assert db.get(SyncJob, job.id).status == 'failed', (db.get(SyncJob, job.id).status, db.get(SyncJob, job.id).error_code)
        assert db.get(Employee, 'batch-user-001') is not None
        assert db.get(Employee, 'batch-user-059') is None
        assert db.get(DatasetState, 1).last_full_sync_at == last_full
        assert db.get(SyncJob, job.id).success_count == 50


def test_batches_survive_later_collection_failure(sessions):
    assert_batches_survive_later_collection_failure(sessions)


def assert_sync_summary_reports_actual_pending_objects_and_latest_task(sessions):
    from app.admin.sync_views import sync_summary
    from app.persistence.models import PendingFact

    now = datetime.now()
    with sessions.begin() as db:
        db.add(Department(id='shared', feishu_department_id='shared', name='待核实部门', sync_quality='pending_verification'))
        db.add(Employee(id='shared', feishu_user_id='shared', name='待核实人员', sync_quality='pending_verification'))
        db.add(Employee(id='valid', feishu_user_id='valid', name='正常人员'))
        for identifier in ('shared', 'new'):
            db.add(PendingFact(object_type='employee', source_id=identifier, normalized_data={}, error_code='PENDING_VERIFICATION', updated_at=now))
        db.add(SyncJob(id='older', type='full', requested_by='test', status='failed', created_at=now - timedelta(seconds=1), updated_at=now))
        db.add(SyncJob(id='latest', type='full', requested_by='test', status='succeeded', created_at=now, updated_at=now))
    with sessions() as db:
        assert sync_summary(db) == {'latest_job': {'job_id': 'latest', 'status': 'succeeded'}, 'pending_object_count': 3}


def test_sync_summary_reports_actual_pending_objects_and_latest_task(sessions):
    assert_sync_summary_reports_actual_pending_objects_and_latest_task(sessions)


def test_sync_preflight_keeps_legacy_field_out_of_readiness(sessions):
    from app.admin.router import sync_preflight
    from app.feishu.binding import bind_connection

    bind_connection(sessions, 'app', 'tenant')
    with sessions.begin() as db:
        state = db.get(DatasetState, 1)
        state.initialization_status = 'complete'
        state.coverage_status = 'unknown'
    result = sync_preflight(identity=None, runtime=SimpleNamespace(sessions=sessions))['data']
    assert result['ready'] is True
    assert result['checks']['coverage_accepted'] is False


def test_query_filters_before_limit_and_includes_live_progress_and_executor(sessions):
    from app.admin.router import list_sync_jobs
    now = datetime.now()
    with sessions.begin() as db:
        db.add(Employee(id='operator', feishu_user_id='operator', name='执行人员'))
        db.add(SyncJob(id='match', type='subtree', root_department_id=None, requested_by='admin:operator', trigger_source='manual', status='running', phase='employees', started_at=now, created_at=now, updated_at=now))
        db.add(SyncJob(id='latest', type='full', requested_by='schedule', status='queued', phase='queued', created_at=now+timedelta(seconds=1), updated_at=now))
        db.add(SystemSetting(key='job_progress:match', value=json.dumps({'phase': 'employees', 'observed_at': now.isoformat(), 'departments_processed': 10, 'employees_processed': 5, 'departments_total': 10, 'employees_total': 20})))
    result = list_sync_jobs(status='running', type='subtree', phase='employees', cursor=None, limit=1, identity=None, runtime=SimpleNamespace(sessions=sessions))
    assert [row['job_id'] for row in result['data']] == ['match']
    row = result['data'][0]
    assert row['processed_count'] == 15 and row['progress_total'] == 30
    assert row['executor_name'] == '执行人员' and row['trigger_label'] == '手动'
    with sessions.begin() as db:
        db.get(SyncJob, 'match').started_at = now + timedelta(seconds=2)
    row = list_sync_jobs(status='running', type=None, phase=None, cursor=None, limit=1, identity=None, runtime=SimpleNamespace(sessions=sessions))['data'][0]
    assert row['processed_count'] == 0  # 上一轮进度不能冒充本次尝试。


def test_details_distinguish_membership_only_update_from_noop_and_link_all_changes(sessions):
    from app.admin.sync_views import job_details
    now = datetime.now()
    with sessions.begin() as db:
        db.add(SyncJob(id='j', type='full', requested_by='test', status='succeeded', created_at=now, updated_at=now))
        db.flush()
        for identifier in ('new', 'relation', 'same'):
            db.add(SyncJobDetail(job_id='j', object_type='employee', object_id=identifier, status='succeeded'))
        db.add(ChangeLog(job_id='j', object_type='employee', object_id='new', source='feishu', before_data=None, after_data={'name': '新成员'}, committed_at=now))
        db.add(ChangeLog(job_id='j', object_type='membership', object_id='relation', source='feishu', before_data={'relations': []}, after_data={'relations': [['d', True, True]]}, committed_at=now))
    with sessions() as db:
        rows = {row['object_id']: row for row in job_details(db, 'j')}
    assert rows['new']['action'] == 'create'
    assert rows['relation']['action'] == 'update'
    assert rows['relation']['changes'][0]['object_type'] == 'membership'
    assert rows['same']['action'] == 'unchanged'


def test_partial_publication_keeps_lease_and_finalization_preserves_first_change_link(sessions):
    from app.sync.publisher import Publisher
    from app.sync.collector import Candidate
    now = datetime.now()
    with sessions.begin() as db:
        db.add(SyncJob(id='j', type='full', requested_by='test', status='running', lease_generation=1, lease_expires_at=now+timedelta(hours=1), created_at=now, updated_at=now))
    candidate = Candidate(departments={'d': {'id': 'd', 'feishu_department_id': 'd', 'parent_id': None, 'name': '部门', 'status': 'active', 'sync_quality': 'complete', 'is_root': False}})
    publisher = Publisher(sessions)
    publisher.publish(candidate, 'j', 1, final=False)
    with sessions() as db:
        assert db.get(SyncJob, 'j').status == 'running'
        assert db.get(SyncJob, 'j').finished_at is None
        link = db.scalar(select(SyncJobDetail.change_log_id).where(SyncJobDetail.job_id == 'j'))
        version = db.get(DatasetState, 1).data_version
    candidate.full = True
    publisher.publish(candidate, 'j', 1)
    with sessions() as db:
        assert db.get(SyncJob, 'j').status == 'succeeded'
        assert db.scalar(select(SyncJobDetail.change_log_id).where(SyncJobDetail.job_id == 'j')) == link
        assert db.get(DatasetState, 1).data_version == version
