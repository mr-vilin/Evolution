from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from app.sync.change_records import organization_changes
from app.dependencies import get_admin_identity, get_runtime
from app.main import app
from app.persistence.models import ChangeLog, SyncJob


def test_organization_changes_aggregates_membership_and_excludes_other_audits(sqlite_sessions):
    now = datetime(2026, 11, 27, 1)
    with sqlite_sessions.begin() as db:
        db.add(SyncJob(id='j1', type='reconcile', requested_by='schedule', status='succeeded'))
        db.flush()
        for index in range(7):
            db.add(ChangeLog(object_type='employee', object_id='u1', object_name='张三', source='feishu',
                             job_id='j1', publication_id=str(index), sync_source='reconcile',
                             before_data={'job_title': str(index)}, after_data={'job_title': str(index + 1)},
                             committed_at=now + timedelta(seconds=index)))
        db.add(ChangeLog(object_type='employee', object_id='u1', object_name='张三', source='feishu',
                         job_id='j1', publication_id='7', sync_source='reconcile',
                         before_data={'status': 'active'}, after_data={'status': 'inactive'},
                         committed_at=now + timedelta(seconds=7)))
        db.add(ChangeLog(object_type='membership', object_id='u1', source='feishu', job_id='j1',
                         publication_id='7', sync_source='reconcile',
                         before_data={'relations': [['d1', True, True]]},
                         after_data={'relations': [['d1', True, False]]},
                         committed_at=now + timedelta(seconds=7)))
        db.add(ChangeLog(object_type='employee', object_id='u2', source='feishu', sync_source='event',
                         event_id='e1', publication_id='event1', executor_name='系统',
                         before_data={'status': 'inactive'}, after_data={'status': 'active'},
                         committed_at=now + timedelta(seconds=8)))
        db.add(ChangeLog(object_type='employee', object_id='u2', source='feishu', sync_source='event',
                         before_data={'sync_quality': 'complete'}, after_data={'sync_quality': 'pending_verification'},
                         committed_at=now + timedelta(seconds=9)))
        db.add(ChangeLog(object_type='store', object_id='d1', source='admin', before_data={}, after_data={'is_store': True}, committed_at=now))
        db.add(ChangeLog(object_type='employee', object_id='u3', source='admin', before_data={}, after_data={'name': '本地操作'}, committed_at=now))
        db.add(ChangeLog(object_type='department', object_id='d1', source='feishu', job_id='j1',
                         before_data=None, after_data={'name': '运营部'}, committed_at=now))

    with sqlite_sessions() as db:
        all_rows = organization_changes(db, object_type='employee')
        assert all_rows['meta']['total'] == 9
        assert all_rows['data'][0]['action'] == 'reactivate'
        assert all_rows['data'][0]['event_id'] == 'e1'
        assert all_rows['data'][1]['action'] == 'deactivate'
        assert {item['field'] for item in all_rows['data'][1]['changes']} == {'status', 'membership:d1'}
        groups = organization_changes(db, object_type='employee', view='grouped')
        assert [row['object_id'] for row in groups['data']] == ['u2', 'u1']
        assert groups['data'][1]['total'] == 8
        assert len(groups['data'][1]['records']) == 5
        history = organization_changes(db, object_type='employee', object_id='u1', page=2, page_size=5)
        assert history['meta']['total'] == 8
        assert len(history['data']) == 3
        filtered = organization_changes(db, object_type='employee', source='reconcile', action='deactivate')
        assert len(filtered['data']) == 1
        assert filtered['data'][0]['actor'] == '系统'
        assert organization_changes(db, object_type='department')['meta']['total'] == 1


def test_organization_changes_endpoint_restricts_enums(sqlite_sessions):
    app.dependency_overrides[get_admin_identity] = lambda: SimpleNamespace(open_id='admin')
    app.dependency_overrides[get_runtime] = lambda: SimpleNamespace(sessions=sqlite_sessions)
    try:
        client = TestClient(app)
        for params in ({'object_type': 'store'}, {'source': 'admin'}, {'action': 'delete'}, {'view': 'unknown'}):
            assert client.get('/admin/api/organization-changes', params=params).status_code == 422
        response = client.get('/admin/api/organization-changes')
        assert response.status_code == 200
        assert response.json()['meta']['total'] == 0
    finally:
        app.dependency_overrides.clear()

def test_event_publication_records_source_and_merges_new_employee_relationship(sqlite_sessions):
    from app.persistence.models import EventInbox
    from app.sync.collector import Candidate
    from app.sync.publisher import Publisher

    with sqlite_sessions.begin() as db:
        db.add(EventInbox(event_id='evt', event_type='contact.user.created_v3', object_id='u',
                          status='queued', payload={}, received_at=datetime(2026, 11, 27, 1)))

    candidate = Candidate(
        departments={'d': {'id': 'd', 'feishu_department_id': 'd', 'parent_id': None,
                           'name': '运营部', 'status': 'active', 'sync_quality': 'complete', 'is_root': False}},
        employees={'u': {'id': 'u', 'feishu_user_id': 'u', 'name': '新员工', 'status': 'active',
                         'sync_quality': 'complete', 'primary_department_id': 'd', 'department_ids': ['d']}},
    )
    Publisher(sqlite_sessions).publish(candidate, event_id='evt')
    with sqlite_sessions() as db:
        records = organization_changes(db, object_type='employee')
        assert records['meta']['total'] == 1
        record = records['data'][0]
        assert record['source'] == 'event'
        assert record['event_id'] == 'evt'
        assert record['object_name'] == '新员工'
        assert record['action'] == 'create'
        assert record['actor'] == '系统'
        assert any(change['field'] == 'membership:d' for change in record['changes'])
        assert record['department_change']['before'] == []
        assert record['department_change']['after'] == [{'id': 'd', 'name': '运营部', 'primary': True}]
        assert any(log['object_type'] == 'membership' for log in record['raw_records'])
def test_department_before_after_preserves_all_memberships_and_primary(sqlite_sessions):
    from app.persistence.models import Department, Employee

    now = datetime(2026, 11, 27, 1)
    with sqlite_sessions.begin() as db:
        for identifier, name in [('d1', '原主门店'), ('d2', '其他门店'), ('d3', '新主门店')]:
            db.add(Department(id=identifier, feishu_department_id=identifier, name=name))
        db.add(Employee(id='actor', feishu_user_id='actor', name='操作人',
                        avatar_url='https://example.test/avatar.png'))
        db.add(SyncJob(id='job', type='full', requested_by='admin:actor', status='succeeded'))
        db.flush()
        db.add(ChangeLog(object_type='employee', object_id='u1', source='feishu',
                         publication_id='p1', job_id='job', sync_source='full',
                         before_data={'primary_department_id': 'd1'}, after_data={'primary_department_id': 'd3'},
                         committed_at=now))
        db.add(ChangeLog(object_type='membership', object_id='u1', source='feishu',
                         publication_id='p1', job_id='job', sync_source='full',
                         before_data={'relations': [['d1', True, True], ['d2', False, True]]},
                         after_data={'relations': [['d3', True, True]]}, committed_at=now))
    with sqlite_sessions() as db:
        row = organization_changes(db, object_type='employee')['data'][0]
        assert row['department_change']['before'] == [
            {'id': 'd1', 'name': '原主门店', 'primary': True},
            {'id': 'd2', 'name': '其他门店', 'primary': False},
        ]
        assert row['department_change']['after'] == [{'id': 'd3', 'name': '新主门店', 'primary': True}]
        assert row['actor'] == '操作人'
        assert row['actor_is_user'] is True
        assert row['actor_avatar_url'] == 'https://example.test/avatar.png'
        assert len(row['raw_records']) == 2
