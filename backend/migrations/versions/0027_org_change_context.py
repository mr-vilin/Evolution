"""保存组织同步变更事务及来源快照。"""

from alembic import op
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
    for name in ('executor_name', 'object_name', 'sync_source', 'event_id', 'publication_id'):
        op.drop_column('change_log', name)