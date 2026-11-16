"""组织展示顺序与可缺省的飞书人员事实；仅新增本需求字段。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0011_organization_browser'
down_revision = '0010_initialization_wizard'
branch_labels = None
depends_on = None

FLAGS = {
    'is_frozen': '飞书账号是否暂停，NULL 表示未知',
    'is_resigned': '飞书账号是否离职，NULL 表示未知',
    'is_activated': '飞书账号是否已激活，NULL 表示未知',
    'is_exited': '飞书账号是否主动退出，NULL 表示未知',
    'is_unjoin': '飞书账号是否未加入，NULL 表示未知',
}


def upgrade():
    op.add_column('department', sa.Column('sort_order', mysql.INTEGER(unsigned=True), nullable=False,
                  server_default='0', comment='同父级共享的本地展示顺序，非负整数，普通同步保留'))
    # MySQL 8.4 的窗口结果先物化，再按稳定 ID 初始化；不触碰原有事实。
    op.execute('''UPDATE department AS d JOIN (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY parent_id ORDER BY id) - 1 AS position
        FROM department
    ) AS ranked ON ranked.id = d.id SET d.sort_order = ranked.position''')
    op.create_index('idx_department_order', 'department', ['parent_id', 'sort_order', 'id'])
    # InnoDB 可能用新联合索引替换外键的自动索引；恢复原 parent_id 索引，
    # 避免本迁移改变既有索引集合，并保证降级时外键仍有支撑索引。
    if op.get_context().as_sql or 'parent_id' not in {
        item['name'] for item in sa.inspect(op.get_bind()).get_indexes('department')
    }:
        op.create_index('parent_id', 'department', ['parent_id'])
    op.add_column('employee', sa.Column('mobile', sa.String(128, collation='utf8mb4_bin'), nullable=True,
                  comment='飞书完整手机号，空值含义由字段可读性说明'))
    for name, comment in FLAGS.items():
        op.add_column('employee', sa.Column(name, sa.Boolean(), nullable=True, comment=comment))
    op.add_column('employee', sa.Column('field_readability', sa.JSON(), nullable=True,
                  comment='手机号和账号标志可读性：readable、not_collected、unreadable'))


def downgrade():
    # 降级会丢失本地顺序及新增采集事实；执行前须备份，应用回退优先保留兼容新增列。
    op.drop_column('employee', 'field_readability')
    for name in reversed(FLAGS):
        op.drop_column('employee', name)
    op.drop_column('employee', 'mobile')
    op.drop_index('idx_department_order', table_name='department')
    op.drop_column('department', 'sort_order')
