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
        db.merge(SystemSetting(setting_key='reconcile_schedule', value=json.dumps({'enabled': False, 'local_time': '03:00', 'timezone': 'Asia/Shanghai'})))
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
            return {'user_id': identifier, 'name': identifier, 'mobile': '+8613800000000', 'department_ids': [], 'status': {'is_resigned': False}}

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
        db.add(SyncJob(id='older', type='full', requested_by='test', status='failed', create_time=now - timedelta(seconds=1), update_time=now))
        db.add(SyncJob(id='latest', type='full', requested_by='test', status='succeeded', create_time=now, update_time=now))
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
        db.add(SyncJob(id='match', type='subtree', root_department_id=None, requested_by='admin:operator', trigger_source='manual', status='running', phase='employees', started_at=now, create_time=now, update_time=now))
        db.add(SyncJob(id='latest', type='full', requested_by='schedule', status='queued', phase='queued', create_time=now+timedelta(seconds=1), update_time=now))
        db.add(SystemSetting(setting_key='job_progress:match', value=json.dumps({'phase': 'employees', 'observed_at': now.isoformat(), 'departments_processed': 10, 'employees_processed': 5, 'departments_total': 10, 'employees_total': 20})))
    result = list_sync_jobs(status='running', type='subtree', phase='employees', cursor=None, limit=1, identity=None, runtime=SimpleNamespace(sessions=sessions))
    assert [row['job_id'] for row in result['data']] == ['match']
    row = result['data'][0]
    assert row['processed_count'] == 15 and row['progress_total'] == 30
    assert row['create_time'] and row['update_time']
    assert 'created_at' not in row and 'updated_at' not in row
    assert row['executor_name'] == '执行人员' and row['trigger_label'] == '手动'
    with sessions.begin() as db:
        db.get(SyncJob, 'match').started_at = now + timedelta(seconds=2)
    row = list_sync_jobs(status='running', type=None, phase=None, cursor=None, limit=1, identity=None, runtime=SimpleNamespace(sessions=sessions))['data'][0]
    assert row['processed_count'] == 0  # 上一轮进度不能冒充本次尝试。


def test_details_distinguish_membership_only_update_from_noop_and_link_all_changes(sessions):
    from app.admin.sync_views import job_details
    now = datetime.now()
    with sessions.begin() as db:
        db.add(SyncJob(id='j', type='full', requested_by='test', status='succeeded', create_time=now, update_time=now))
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
        db.add(SyncJob(id='j', type='full', requested_by='test', status='running', lease_generation=1, lease_expires_at=now+timedelta(hours=1), create_time=now, update_time=now))
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

def test_retry_rejects_active_same_scope_and_preserves_failed_job(sessions):
    from fastapi import HTTPException
    import pytest
    from app.admin.router import retry_sync_job
    from app.persistence.repositories import SqlSyncJobRepository
    now = datetime.now()
    with sessions.begin() as db:
        db.add(SyncJob(id='failed', type='full', requested_by='test', status='failed', create_time=now))
        db.add(SyncJob(id='active', type='full', requested_by='test', status='running', create_time=now))
    runtime = SimpleNamespace(sessions=sessions, jobs=SqlSyncJobRepository(sessions))
    authorization = (SimpleNamespace(open_id='operator'), None)
    with pytest.raises(HTTPException) as error:
        retry_sync_job('failed', authorization=authorization, runtime=runtime)
    assert error.value.status_code == 409
    with sessions() as db:
        assert db.get(SyncJob, 'failed').status == 'failed'
        assert db.get(SyncJob, 'failed').attempt == 1


def test_unique_object_total_and_required_mobile_with_lifecycle_exemptions(sessions):
    from app.sync.collector import normalize_user, Candidate
    from app.sync.publisher import Publisher
    from app.admin.sync_views import pending_object_rows, sync_summary
    from app.persistence.models import PendingFact

    now = datetime.now()
    with sessions.begin() as db:
        db.add(SyncJob(id='unique', type='reconcile', requested_by='test', status='running',
                       lease_generation=1, lease_expires_at=now+timedelta(hours=1)))
    mappings = {'permission_role': 'role', 'store_attribute': 'store'}
    valid = normalize_user({'user_id': 'valid', 'name': '离职', 'mobile': '+8613800000000',
                            'status': {'is_resigned': True}}, mappings)
    invalid = normalize_user({'user_id': 'invalid', 'name': '未激活', 'status': {
        'is_resigned': False, 'is_activated': False}}, mappings)
    Publisher(sessions).publish(Candidate(employees={'valid': valid, 'invalid': invalid}), 'unique', 1)
    with sessions() as db:
        job = db.get(SyncJob, 'unique')
        assert (job.total_count, job.success_count, job.failure_count) == (2, 1, 1)
        assert db.get(Employee, 'valid').sync_quality == 'complete'
        assert db.get(PendingFact, ('employee', 'valid')) is None
        assert db.get(Employee, 'invalid').sync_quality == 'pending_verification'
        assert sync_summary(db)['pending_object_count'] == 1
        assert sync_summary(db)['latest_job']['status'] == 'completed_with_errors'
        assert pending_object_rows(db)[0]['reason_code'] == 'MOBILE_REQUIRED'
    corrected = normalize_user({'user_id': 'invalid', 'name': '未激活', 'mobile': '+8613800000000',
                                'status': {'is_resigned': False, 'is_activated': False}}, mappings)
    Publisher(sessions).publish(Candidate(employees={'invalid': corrected}))
    with sessions() as db:
        assert sync_summary(db)['pending_object_count'] == 0


def test_historical_duplicate_total_is_corrected_only_with_final_collection_evidence():
    from app.admin.sync_views import job_progress
    now = datetime.now()
    row = SimpleNamespace(status='succeeded', started_at=now, success_count=991, failure_count=0, total_count=992)
    progress = {'phase': 'publishing', 'observed_at': now.isoformat(), 'departments_total': 945, 'employees_total': 46}
    assert job_progress(row, progress)['progress_total'] == 991
    assert job_progress(row, {**progress, 'employees_total': 47})['progress_total'] == 992
