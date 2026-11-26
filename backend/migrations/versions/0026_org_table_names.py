"""为组织同步数据表统一增加 org_ 前缀。"""

from alembic import context, op
from alembic.script import ScriptDirectory
import sqlalchemy as sa

revision = '0026_org_table_names'
down_revision = '0025_sync_schema'
branch_labels = None
depends_on = None

_TABLES = (
    'dataset_state', 'pending_fact', 'sync_job', 'sync_job_detail',
    'sync_staging', 'worker_lease',
)


def _existing_tables():
    if context.is_offline_mode():
        return None
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for name in _TABLES:
        if (name in tables) == ('org_' + name in tables):
            raise RuntimeError(f'ORG_TABLE_RENAME_CONFLICT: {name}')
    return tables


def upgrade():
    tables = _existing_tables()
    if tables is None or 'dataset_state' in tables:
        op.rename_table('dataset_state', 'org_dataset_state')
    if tables is None or 'pending_fact' in tables:
        op.rename_table('pending_fact', 'org_pending_fact')
    if tables is None or 'sync_job' in tables:
        op.rename_table('sync_job', 'org_sync_job')
    if tables is None or 'sync_job_detail' in tables:
        op.rename_table('sync_job_detail', 'org_sync_job_detail')
    if tables is None or 'sync_staging' in tables:
        op.rename_table('sync_staging', 'org_sync_staging')
    if tables is None or 'worker_lease' in tables:
        op.rename_table('worker_lease', 'org_worker_lease')


def downgrade():
    if not context.is_offline_mode():
        target = context.get_revision_argument()
        if target not in {down_revision, '0024_organization_schema', '0023_remove_connection_coverage',
                          '0022_mysql_general_ci', '0021_tencent_db_conventions', '0020_tencent_history',
                          '-1', '-2', '-3', '-4', '-5'}:
            history = ScriptDirectory.from_config(context.config).get_revision('0020_tencent_history')
            history.module.check_downgrade(target)
    tables = _existing_tables()
    if tables is None or 'org_worker_lease' in tables:
        op.rename_table('org_worker_lease', 'worker_lease')
    if tables is None or 'org_sync_staging' in tables:
        op.rename_table('org_sync_staging', 'sync_staging')
    if tables is None or 'org_sync_job_detail' in tables:
        op.rename_table('org_sync_job_detail', 'sync_job_detail')
    if tables is None or 'org_sync_job' in tables:
        op.rename_table('org_sync_job', 'sync_job')
    if tables is None or 'org_pending_fact' in tables:
        op.rename_table('org_pending_fact', 'pending_fact')
    if tables is None or 'org_dataset_state' in tables:
        op.rename_table('org_dataset_state', 'dataset_state')
