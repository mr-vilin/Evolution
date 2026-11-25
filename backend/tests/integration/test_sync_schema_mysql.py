from datetime import datetime

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.persistence.database import schema_snapshot
from app.persistence.schema_check import check_schema


def test_sync_schema_preserves_times_and_enforces_active_scope(migration_database):
    engine, config = migration_database
    command.upgrade(config, '0024_organization_schema')
    ts = datetime(2026, 11, 1, 2, 3, 4)
    with engine.begin() as db:
        db.execute(text("INSERT INTO sync_job (id,type,requested_by,status,attempt,lease_generation,created_at,updated_at) VALUES ('old','full','test','queued',1,0,:ts,:ts)"), {'ts': ts})
    before = schema_snapshot(engine)
    command.upgrade(config, 'head')
    assert check_schema(engine)['errors'] == []
    with engine.begin() as db:
        assert db.execute(text("SELECT create_time,update_time FROM sync_job WHERE id='old'")).one() == (ts, ts)
        assert db.scalar(text("SELECT COUNT(*) FROM system_setting WHERE setting_key='task_queue_lock'")) == 1
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(text("INSERT INTO sync_job (id,type,requested_by,status,attempt,lease_generation) VALUES ('duplicate','full','test','running',1,0)"))
        db.execute(text("UPDATE sync_job SET status='succeeded' WHERE id='old'"))
        db.execute(text("INSERT INTO sync_job (id,type,requested_by,status,attempt,lease_generation) VALUES ('new','full','test','queued',1,0)"))
        assert db.scalar(text("SELECT update_time FROM sync_job WHERE id='old'")) > ts
    command.downgrade(config, '0024_organization_schema')
    assert schema_snapshot(engine) == before
    with engine.connect() as db:
        assert db.scalar(text("SELECT created_at FROM sync_job WHERE id='old'")) == ts
