"""独立 MySQL 8.4 的 HTTP、持久化、事务与迁移验收。"""
from types import SimpleNamespace

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select, text

from app.dependencies import get_admin_identity, get_runtime, require_admin_write
from app.main import app
from app.persistence.database import schema_snapshot
from app.persistence.models import ChangeLog, DatasetState, Department, Employee, EmployeeDepartment, EmployeeStore, StoreProfile
from app.persistence.read_service import SqlReadService


@pytest.fixture
def organization_mysql(mysql_sessions):
    with mysql_sessions.begin() as db:
        db.add(Department(id='0', feishu_department_id='0', name='组织', is_virtual_root=True))
        db.flush()
        db.add_all([Department(id=f'd{i:03}', feishu_department_id=f'd{i:03}', parent_id='0', name=f'测试部门{i}', sort_order=i, sync_quality='complete') for i in range(501)])
        db.flush()
        db.add(Employee(id='user', feishu_user_id='user', name='测试成员', primary_department_id='d000', sync_quality='complete'))
        db.flush()
        db.add(EmployeeDepartment(employee_id='user', department_id='d000', active=True, is_primary=True))
        epoch = db.get(DatasetState, 1).dataset_epoch
    identity = SimpleNamespace(open_id='mysql-admin')
    app.dependency_overrides[get_admin_identity] = lambda: identity
    app.dependency_overrides[require_admin_write] = lambda: (identity, None)
    app.dependency_overrides[get_runtime] = lambda: SimpleNamespace(sessions=mysql_sessions, reads=SqlReadService(mysql_sessions, 'test-secret'))
    try:
        yield TestClient(app, raise_server_exceptions=False), mysql_sessions, epoch
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('failed_table', ['store_profile', 'change_log', 'employee_store'])
def test_entire_batch_audit_projection_and_version_rollback_together(organization_mysql, failed_table):
    client, sessions, epoch = organization_mysql
    from sqlalchemy.engine import Engine
    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith('insert into ' + failed_table):
            raise RuntimeError('synthetic database write failure')
    event.listen(Engine, 'before_cursor_execute', fail)
    try:
        response = client.post('/admin/api/organization/stores', json={
            'dataset_epoch': epoch, 'data_version': 1,
            'changes': [{'department_id': f'd{i:03}', 'is_store': True} for i in range(501)]})
        assert response.status_code == 500
    finally:
        event.remove(Engine, 'before_cursor_execute', fail)
    with sessions() as db:
        assert db.scalar(select(StoreProfile)) is None
        assert db.scalar(select(EmployeeStore)) is None
        assert db.scalar(select(ChangeLog).where(ChangeLog.actor == 'admin:mysql-admin')) is None
        assert db.get(DatasetState, 1).data_version == 1
        assert db.get(Employee, 'user').primary_store_status == 'unknown'


def test_large_batch_selection_shared_order_and_stale_epoch(organization_mysql):
    client, sessions, epoch = organization_mysql
    selected = client.post('/admin/api/organization/selection', json={
        'dataset_epoch': epoch, 'data_version': 1, 'selected_ids': [], 'toggle_id': '0'}).json()
    assert selected['data']['count'] == 501
    body = {'dataset_epoch': epoch, 'data_version': 1, 'department_id': 'd500', 'parent_id': '0', 'anchor_id': 'd000', 'position': 'before'}
    assert client.post('/admin/api/organization/order', json=body).status_code == 200
    assert client.post('/admin/api/organization/order', json=body).status_code == 409
    assert client.get('/admin/api/organization/departments', params={'limit': 1}).json()['data'][0]['id'] == 'd500'
    changes = [{'department_id': identifier, 'is_store': True} for identifier in selected['data']['selected_ids']]
    result = client.post('/admin/api/organization/stores', json={'dataset_epoch': epoch, 'data_version': 2, 'changes': changes})
    assert result.status_code == 200 and result.json()['data']['saved_count'] == 501
    with sessions() as db:
        assert db.get(EmployeeStore, ('user', 'd000')).is_primary is True
        assert db.get(Employee, 'user').primary_store_status == 'resolved'
    with sessions.begin() as db:
        state = db.get(DatasetState, 1)
        state.dataset_epoch = 'replacement-epoch'
        state.data_version = 3
    assert client.post('/admin/api/organization/stores', json={'dataset_epoch': epoch, 'data_version': 3, 'changes': changes}).status_code == 409


def test_0011_preserves_existing_schema_data_and_initializes_stable_sibling_order(migration_database):
    engine, config = migration_database
    command.upgrade(config, '0010_initialization_wizard')
    with engine.begin() as db:
        db.execute(text("INSERT INTO department (id,feishu_department_id,name,status,sync_quality,is_virtual_root) VALUES ('z','z','后','active','complete',0),('a','a','前','active','complete',0)"))
    before = schema_snapshot(engine)
    command.upgrade(config, '0011_organization_browser')
    after = schema_snapshot(engine)
    assert after['session']['version'].startswith('8.4.')
    assert after['session']['collation_connection'] == 'utf8mb4_general_ci'
    with engine.connect() as db:
        assert list(db.execute(text('SELECT id,sort_order FROM department ORDER BY sort_order'))) == [('a', 0), ('z', 1)]
        assert db.execute(text('SELECT COUNT(*) FROM employee WHERE is_activated IS NOT NULL')).scalar_one() == 0
    for table, old in before['tables'].items():
        current = after['tables'][table]
        assert current['foreign_keys'] == old['foreign_keys']
        for column in old['columns']:
            assert column == next(item for item in current['columns'] if item['name'] == column['name'])
    command.downgrade(config, '0010_initialization_wizard')
    assert schema_snapshot(engine) == before


def test_0012_email_preserves_schema_data_and_reverses_only_new_column(migration_database):
    engine, config = migration_database
    command.upgrade(config, '0011_organization_browser')
    with engine.begin() as db:
        db.execute(text("INSERT INTO employee (id,feishu_user_id,name,status,sync_quality,primary_store_status) VALUES ('u-email','u-email','邮箱演练','active','complete','unknown')"))
    before = schema_snapshot(engine)
    command.upgrade(config, '0012_employee_email')
    after = schema_snapshot(engine)
    email = next(column for column in after['tables']['employee']['columns'] if column['name'] == 'email')
    assert email['type'] == 'varchar(254)'
    assert email['nullable'] is True
    assert email['charset'] == 'utf8mb4'
    assert email['collation'] == 'utf8mb4_bin'
    assert email['comment'] and '邮箱' in email['comment']
    for table, old in before['tables'].items():
        current = after['tables'][table]
        assert current['foreign_keys'] == old['foreign_keys']
        assert current['indexes'] == old['indexes']
        for column in old['columns']:
            assert column == next(item for item in current['columns'] if item['name'] == column['name'])
    with engine.begin() as db:
        assert db.scalar(text("SELECT email FROM employee WHERE id='u-email'")) is None
        db.execute(text("UPDATE employee SET email='test@example.test' WHERE id='u-email'"))
    command.downgrade(config, '0011_organization_browser')
    assert schema_snapshot(engine) == before
    with engine.connect() as db:
        assert db.scalar(text("SELECT name FROM employee WHERE id='u-email'")) == '邮箱演练'


def test_0013_profile_preserves_existing_schema_data_and_roundtrips(migration_database):
    engine, config = migration_database
    command.upgrade(config, '0012_employee_email')
    with engine.begin() as db:
        db.execute(text("INSERT INTO employee (id,feishu_user_id,name,status,sync_quality,primary_store_status,email) VALUES ('u-profile','u-profile','资料演练','active','complete','unknown','test@example.test')"))
    before = schema_snapshot(engine)
    command.upgrade(config, '0013_employee_profile')
    after = schema_snapshot(engine)
    columns = {column['name']: column for column in after['tables']['employee']['columns']}
    assert columns['avatar_url']['type'] == 'varchar(2048)'
    assert columns['avatar_url']['charset'] == 'utf8mb4'
    assert columns['avatar_url']['collation'] == 'utf8mb4_bin'
    assert columns['join_time']['type'] == 'bigint'
    for name in ('avatar_url', 'join_time'):
        assert columns[name]['nullable'] and columns[name]['comment']
    for table, old in before['tables'].items():
        current = after['tables'][table]
        assert current['foreign_keys'] == old['foreign_keys']
        assert current['indexes'] == old['indexes']
        assert current['options'] == old['options']
        for column in old['columns']:
            assert column == next(item for item in current['columns'] if item['name'] == column['name'])
    with engine.begin() as db:
        assert db.execute(text("SELECT avatar_url,join_time FROM employee WHERE id='u-profile'")).one() == (None, None)
        db.execute(text("UPDATE employee SET avatar_url='https://example.test/avatar.png',join_time=1793980800 WHERE id='u-profile'"))
        assert db.execute(text("SELECT avatar_url,join_time FROM employee WHERE id='u-profile'")).one() == ('https://example.test/avatar.png', 1793980800)
    command.downgrade(config, '0012_employee_email')
    assert schema_snapshot(engine) == before
    with engine.connect() as db:
        assert db.execute(text("SELECT name,email FROM employee WHERE id='u-profile'")).one() == ('资料演练', 'test@example.test')
