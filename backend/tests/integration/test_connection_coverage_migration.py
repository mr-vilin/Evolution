from alembic import command
from sqlalchemy import text

from app.persistence.database import schema_snapshot
from test_sync_center import assert_sync_summary_reports_actual_pending_objects_and_latest_task


def test_drop_and_restore_connection_coverage_preserves_binding(migration_database):
    engine, config = migration_database
    previous = '0022_mysql_general_ci'
    command.upgrade(config, previous)
    with engine.begin() as db:
        db.execute(text("""
            INSERT INTO feishu_connection (id, app_id, tenant_key, status, coverage_status, custom_attrs)
            VALUES (1, 'app-test', 'tenant-test', 'degraded', 'unknown', JSON_OBJECT('permission_role', 'field'))
        """))
    before = schema_snapshot(engine)
    binding = text('SELECT app_id, tenant_key, status, custom_attrs FROM feishu_connection WHERE id = 1')
    with engine.connect() as db:
        before_binding = db.execute(binding).one()
        before_dataset = db.execute(text('SELECT * FROM dataset_state WHERE id = 1')).one()

    target = '0023_remove_connection_coverage'
    command.upgrade(config, target)
    after = schema_snapshot(engine)
    expected_tables = before['tables']
    connection = expected_tables['feishu_connection']
    original_columns = connection['columns']
    connection['columns'] = [column for column in original_columns if column['name'] != 'coverage_status']
    assert after['tables'] == expected_tables
    assert after['versions'] == [target]
    with engine.connect() as db:
        assert db.execute(binding).one() == before_binding
        assert db.execute(text('SELECT * FROM dataset_state WHERE id = 1')).one() == before_dataset

    command.downgrade(config, previous)
    restored = schema_snapshot(engine)
    assert restored['versions'] == [previous]
    assert sorted(restored['tables']['feishu_connection']['columns'], key=lambda column: column['name']) == sorted(original_columns, key=lambda column: column['name'])
    with engine.connect() as db:
        assert db.scalar(text('SELECT coverage_status FROM feishu_connection WHERE id = 1')) == 'unknown'
        assert db.execute(binding).one() == before_binding


def test_sync_summary_uses_mysql_object_identity(mysql_sessions):
    assert_sync_summary_reports_actual_pending_objects_and_latest_task(mysql_sessions)
