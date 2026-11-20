from alembic import command
import pytest
from sqlalchemy import text

from app.persistence.database import schema_snapshot
from app.persistence.schema_check import check_schema


PREVIOUS = '0021_tencent_db_conventions'


def test_collation_upgrade_preserves_constraints_indexes_and_values(migration_database):
    engine, config = migration_database
    command.upgrade(config, PREVIOUS)
    with engine.begin() as db:
        db.execute(text("""
            INSERT INTO department (id, feishu_department_id, name, status, sync_quality, is_virtual_root)
            VALUES ('RootA','SourceA','部门甲','active','complete',0)
        """))
        db.execute(text("""
            INSERT INTO department (id, feishu_department_id, parent_id, name, status, sync_quality, is_virtual_root)
            VALUES ('ChildB','SourceB','RootA','部门乙','active','complete',0)
        """))
    before = schema_snapshot(engine)

    command.upgrade(config, 'head')
    assert check_schema(engine)['errors'] == []
    after = schema_snapshot(engine)
    changed = [
        (column, current)
        for table, info in before['tables'].items()
        for column, current in zip(info['columns'], after['tables'][table]['columns'], strict=True)
        if column['collation'] != current['collation']
    ]
    assert len(changed) == 68
    for column, current in changed:
        assert column['collation'] == 'utf8mb4_bin'
        assert current == dict(column, collation='utf8mb4_general_ci')
    for table, info in before['tables'].items():
        for key in info.keys() - {'columns'}:
            assert after['tables'][table][key] == info[key]
    with engine.connect() as db:
        assert db.scalar(text("SELECT parent_id FROM department WHERE id = 'childb'")) == 'RootA'

    command.downgrade(config, PREVIOUS)
    assert schema_snapshot(engine) == before


def test_collation_upgrade_rejects_unique_collision_before_schema_change(migration_database):
    engine, config = migration_database
    command.upgrade(config, PREVIOUS)
    with engine.begin() as db:
        db.execute(text("""
            INSERT INTO department (id, feishu_department_id, name, status, sync_quality, is_virtual_root)
            VALUES ('RootA','SourceA','部门甲','active','complete',0),
                   ('roota','SourceB','部门乙','active','complete',0)
        """))
    before = schema_snapshot(engine)

    with pytest.raises(RuntimeError, match=r'COLLATION_UNIQUE_CONFLICT: department\.PRIMARY'):
        command.upgrade(config, 'head')
    assert schema_snapshot(engine) == before
