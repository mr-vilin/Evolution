from alembic import command
from sqlalchemy import text

from app.persistence.database import schema_snapshot
from app.persistence.schema_check import check_schema


def test_org_table_renames_preserve_rows_and_foreign_keys(migration_database):
    engine, config = migration_database
    command.upgrade(config, '0025_sync_schema')
    with engine.begin() as db:
        db.execute(text("INSERT INTO sync_job (id,type,requested_by,status,attempt,lease_generation) VALUES ('job','full','test','queued',1,0)"))
        db.execute(text("INSERT INTO sync_job_detail (job_id,object_type,object_id,status,attempt) VALUES ('job','employee','u','queued',1)"))
        db.execute(text("INSERT INTO sync_staging (job_id,object_type,source_id,normalized_data) VALUES ('job','employee','u','{}')"))
        db.execute(text("INSERT INTO pending_fact (object_type,source_id,normalized_data,error_code,updated_at) VALUES ('employee','pending','{}','test',UTC_TIMESTAMP())"))
    names = ('dataset_state', 'pending_fact', 'sync_job', 'sync_job_detail', 'sync_staging', 'worker_lease')
    before = schema_snapshot(engine)
    with engine.connect() as db:
        original = {name: db.execute(text(f'SELECT * FROM {name}')).all() for name in names}
    command.upgrade(config, 'head')
    assert check_schema(engine)['errors'] == []
    after = schema_snapshot(engine)
    for name in names:
        assert name not in after['tables']
        assert 'org_' + name in after['tables']
    for child in ('org_sync_job_detail', 'org_sync_staging'):
        assert after['tables'][child]['foreign_keys'][0]['referred_table'] == 'org_sync_job'
    with engine.connect() as db:
        for name, rows in original.items():
            assert db.execute(text(f'SELECT * FROM org_{name}')).all() == rows
    command.downgrade(config, '0025_sync_schema')
    assert schema_snapshot(engine) == before
    with engine.connect() as db:
        for name, rows in original.items():
            assert db.execute(text(f'SELECT * FROM {name}')).all() == rows
