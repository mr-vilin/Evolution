"""在随机隔离库检验日期转换、索引等价及历史值保留。"""
from datetime import date

from alembic import command
import pytest
from sqlalchemy import inspect, select, text

from app.persistence.database import CURRENT_SCHEMA_HEAD
from app.persistence.models import TencentSyncConfig
from app.persistence.schema_check import check_schema

PREVIOUS = '0020_tencent_history'
INDEXES = {
    'tencent_api_call': ('tencent_api_call_request_id', 'tencent_api_call_rate_window'),
    'tencent_sync_job': ('tencent_sync_job_parent_job_id', 'tencent_job_priority'),
    'tencent_cost_period': ('tencent_period_month',),
}


def _indexes(engine, prefix):
    inspector = inspect(engine)
    return {
        (table, idx['name'].removeprefix(prefix)): (idx['column_names'], idx['unique'])
        for table, names in INDEXES.items()
        for idx in inspector.get_indexes(table)
        if idx['name'] in {prefix + name for name in names}
    }


def _seed(engine, anchor):
    with engine.begin() as db:
        db.execute(text("""
            INSERT INTO tencent_account (id, uin, alias, credential_ref, verification_status, verified_at)
            VALUES (1, '101', '测试账号甲', 'fixture', 'verified', CURRENT_TIMESTAMP),
                   (2, '102', '测试账号乙', 'fixture', 'verified', CURRENT_TIMESTAMP)
        """))
        db.execute(text("""
            INSERT INTO tencent_sync_config (account_id, business, frequency, currency, schedule_start_date)
            VALUES (1, 'cost', 'daily', 'CNY', :anchor), (2, 'cost', 'manual', 'CNY', NULL)
        """), {'anchor': anchor})


def _anchors(engine):
    with engine.connect() as db:
        return list(db.scalars(select(TencentSyncConfig.schedule_start_date).order_by(TencentSyncConfig.id)))


def test_date_and_index_rename_roundtrip(migration_database):
    engine, config = migration_database
    command.upgrade(config, PREVIOUS)
    _seed(engine, '2024-02-29')
    before = _indexes(engine, 'ix_')
    assert len(before) == 5
    with engine.connect() as db:
        timestamps = db.execute(text('SELECT update_time FROM tencent_sync_config ORDER BY id')).all()

    command.upgrade(config, 'head')
    assert _anchors(engine) == [date(2024, 2, 29), None]
    assert _indexes(engine, 'idx_') == before and not _indexes(engine, 'ix_')
    assert check_schema(engine)['errors'] == []
    with engine.connect() as db:
        assert db.execute(text('SELECT update_time FROM tencent_sync_config ORDER BY id')).all() == timestamps

    command.downgrade(config, PREVIOUS)
    assert _anchors(engine) == ['2024-02-29', None]
    assert _indexes(engine, 'ix_') == before and not _indexes(engine, 'idx_')
    command.upgrade(config, 'head')
    assert _anchors(engine) == [date(2024, 2, 29), None]


@pytest.mark.parametrize('invalid', ['2026-02-29', '2026-1-01', '0000-00-00', '0999-12-31', ''])
def test_invalid_anchor_rejected_before_any_ddl(migration_database, invalid):
    engine, config = migration_database
    command.upgrade(config, PREVIOUS)
    _seed(engine, invalid)
    before = _indexes(engine, 'ix_')

    with pytest.raises(RuntimeError, match='TENCENT_INVALID_SCHEDULE_ANCHOR: config_id=1'):
        command.upgrade(config, CURRENT_SCHEMA_HEAD)

    assert _anchors(engine) == [invalid, None]
    assert _indexes(engine, 'ix_') == before and not _indexes(engine, 'idx_')
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == PREVIOUS
