"""规范腾讯云索引命名及补漏日期类型；业务库执行须另行授权。"""
from datetime import date

from alembic import context, op
from alembic.script import ScriptDirectory
from sqlalchemy import text

revision = '0021_tencent_db_conventions'
down_revision = '0020_tencent_history'
branch_labels = None
depends_on = None

RENAMES = {
    'tencent_api_call': ('ix_tencent_api_call_request_id', 'ix_tencent_api_call_rate_window'),
    'tencent_sync_job': ('ix_tencent_sync_job_parent_job_id', 'ix_tencent_job_priority'),
    'tencent_cost_period': ('ix_tencent_period_month',),
}
ANCHOR_COMMENT = '首次日周计划的补漏日期锚点，不代表已核验历史起点'


def _rename_indexes(*, reverse=False):
    for table, names in RENAMES.items():
        clauses = []
        for old in names:
            new = 'idx_' + old.removeprefix('ix_')
            source, target = (new, old) if reverse else (old, new)
            clauses.append(f'RENAME INDEX {source} TO {target}')
        op.execute(f"ALTER TABLE {table} {', '.join(clauses)}")


def _check_anchors():
    rows = op.get_bind().execute(text("""
        SELECT id, CAST(schedule_start_date AS CHAR) FROM tencent_sync_config
        WHERE schedule_start_date IS NOT NULL
    """))
    for config_id, value in rows:
        try:
            parsed = date.fromisoformat(value)
            valid = parsed.year >= 1000 and parsed.isoformat() == value
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise RuntimeError(f'TENCENT_INVALID_SCHEDULE_ANCHOR: config_id={config_id}')


def upgrade():
    if not context.is_offline_mode():
        _check_anchors()
    op.execute(f"ALTER TABLE tencent_sync_config MODIFY COLUMN schedule_start_date DATE NULL COMMENT '{ANCHOR_COMMENT}'")
    _rename_indexes()


def downgrade():
    if not context.is_offline_mode():
        target = context.get_revision_argument()
        if target not in {down_revision, '-1'}:
            # 必须在任何 MySQL DDL 前复用旧迁移的证据保护，而不是等下一跳才拒绝。
            previous = ScriptDirectory.from_config(context.config).get_revision(down_revision)
            previous.module.check_downgrade(target)
        _check_anchors()
    op.execute(
        "ALTER TABLE tencent_sync_config MODIFY COLUMN schedule_start_date "
        f"VARCHAR(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '{ANCHOR_COMMENT}'"
    )
    _rename_indexes(reverse=True)
