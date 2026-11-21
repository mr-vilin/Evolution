"""移除飞书连接上只有初始赋值的覆盖状态列。"""

import sqlalchemy as sa
from alembic import context, op
from alembic.script import ScriptDirectory


revision = '0023_remove_connection_coverage'
down_revision = '0022_mysql_general_ci'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('feishu_connection', 'coverage_status')


def downgrade():
    if not context.is_offline_mode():
        target = context.get_revision_argument()
        if target not in {down_revision, '0021_tencent_db_conventions', '0020_tencent_history', '-1', '-2', '-3'}:
            # 跨版本回退必须在 MySQL 提交本次 DDL 前保留已有费用证据保护。
            history = ScriptDirectory.from_config(context.config).get_revision('0020_tencent_history')
            history.module.check_downgrade(target)
    # 为旧版应用恢复字段，并给已有绑定补回初始值。
    op.add_column('feishu_connection', sa.Column(
        'coverage_status', sa.String(32), nullable=False, server_default='unknown', comment='连接覆盖状态',
    ))
    op.alter_column('feishu_connection', 'coverage_status', existing_type=sa.String(32), server_default=None)
