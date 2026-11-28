"""保存组织同步变更事务及来源快照。"""

from alembic import context, op
from alembic.script import ScriptDirectory
import sqlalchemy as sa

revision = '0027_org_change_context'
down_revision = '0026_org_table_names'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('change_log', sa.Column('publication_id', sa.String(32), nullable=True, comment='组织同步事务发布标识，用于合并同一对象的变更'))
    op.add_column('change_log', sa.Column('event_id', sa.String(191), nullable=True, comment='组织变更关联的飞书订阅事件标识'))
    op.add_column('change_log', sa.Column('sync_source', sa.String(32), nullable=True, comment='组织变更来源：initialize、full、subtree、reconcile 或 event'))
    op.add_column('change_log', sa.Column('object_name', sa.String(255), nullable=True, comment='组织对象变更时的名称快照'))
    op.add_column('change_log', sa.Column('executor_name', sa.String(255), nullable=True, comment='组织变更执行人名称快照'))


def downgrade():
    if not context.is_offline_mode():
        target = context.get_revision_argument()
        if target not in {down_revision, '0025_sync_schema', '0024_organization_schema',
                          '0023_remove_connection_coverage', '0022_mysql_general_ci',
                          '0021_tencent_db_conventions', '0020_tencent_history',
                          '-1', '-2', '-3', '-4', '-5', '-6', '-7'}:
            # 跨版本回退必须在删除组织变更字段前执行既有财务证据保护。
            history = ScriptDirectory.from_config(context.config).get_revision('0020_tencent_history')
            history.module.check_downgrade(target)
    for name in ('executor_name', 'object_name', 'sync_source', 'event_id', 'publication_id'):
        op.drop_column('change_log', name)