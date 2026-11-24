from datetime import datetime

from alembic import command
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.persistence.database import schema_snapshot
from app.persistence.models import Department, Employee, EmployeeDepartment
from app.persistence.schema_check import check_schema


PREVIOUS = '0023_remove_connection_coverage'
TARGET = '0024_organization_schema'
SYNC_TIME = datetime(2026, 11, 20, 1, 2, 3)


def test_organization_schema_preserves_existing_data_on_upgrade_and_downgrade(migration_database):
    engine, config = migration_database
    command.upgrade(config, PREVIOUS)
    with engine.begin() as db:
        db.execute(text("""
            INSERT INTO department (id, feishu_department_id, name, status, sync_quality, is_virtual_root, last_seen_at)
            VALUES ('0', '0', '组织', 'active', 'complete', 1, :seen),
                   ('shop', 'shop', '门店', 'active', 'pending_verification', 0, NULL)
        """), {'seen': SYNC_TIME})
        db.execute(text("""
            INSERT INTO employee (id, feishu_user_id, name, status, sync_quality, primary_store_status,
                                  primary_department_id, join_time, is_activated, last_seen_at)
            VALUES ('u', 'u', '员工', 'active', 'complete', 'unknown', 'shop', 0, 1, :seen)
        """), {'seen': SYNC_TIME})
        db.execute(text("""
            INSERT INTO employee_department (employee_id, department_id, is_primary, active)
            VALUES ('u', 'shop', 1, 0)
        """))
    previous_schema = schema_snapshot(engine)

    command.upgrade(config, TARGET)
    assert check_schema(engine)['errors'] == []
    with Session(engine) as db:
        root = db.get(Department, '0')
        shop = db.get(Department, 'shop')
        employee = db.get(Employee, 'u')
        relation = db.get(EmployeeDepartment, ('u', 'shop'))
        assert root.is_root is True and root.last_sync_at == SYNC_TIME
        assert shop.is_root is False and shop.last_sync_at is None and shop.sync_quality == 'pending_verification'
        assert employee.is_activated is True and employee.is_frozen is None
        assert employee.join_time == 0 and employee.last_sync_at == SYNC_TIME
        assert relation.is_primary is True and relation.is_active is False
        assert root.create_time == root.update_time
        assert employee.create_time == employee.update_time
        assert db.scalar(select(Department.id).where(Department.is_root.is_(True))) == '0'

    with engine.begin() as db:
        db.exec_driver_sql("SET timestamp = UNIX_TIMESTAMP(UTC_TIMESTAMP() + INTERVAL 1 DAY)")
        try:
            db.exec_driver_sql("UPDATE department SET sort_order = 1 WHERE id = '0'")
        finally:
            db.exec_driver_sql("SET timestamp = DEFAULT")
        seen, created, updated = db.exec_driver_sql(
            "SELECT last_sync_at, create_time, update_time FROM department WHERE id = '0'"
        ).one()
        assert seen == SYNC_TIME and updated > created

    command.downgrade(config, PREVIOUS)
    assert schema_snapshot(engine) == previous_schema
    with engine.connect() as db:
        assert db.execute(text("SELECT is_virtual_root, last_seen_at FROM department WHERE id = '0'")).one() == (1, SYNC_TIME)
        assert db.execute(text("SELECT join_time, last_seen_at FROM employee WHERE id = 'u'")).one() == (0, SYNC_TIME)
        assert db.execute(text("SELECT is_primary, active FROM employee_department")).one() == (1, 0)
