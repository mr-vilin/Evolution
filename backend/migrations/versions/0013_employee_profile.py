"""新增人员头像与入职时间；不回填业务数据，不触发同步。"""
from alembic import op
import sqlalchemy as sa

revision = '0013_employee_profile'
down_revision = '0012_employee_email'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('employee', sa.Column('avatar_url', sa.String(2048, collation='utf8mb4_bin'), nullable=True,
                  comment='飞书人员头像 HTTPS 地址，缺省或不可读时为空'))
    op.add_column('employee', sa.Column('join_time', sa.BigInteger(), nullable=True,
                  comment='飞书入职时间 Unix 秒时间戳，按北京时间展示日期，未填写或不可读时为空'))


def downgrade():
    # 会删除已采集头像和入职时间；实际执行须独立授权并备份。
    op.drop_column('employee', 'join_time')
    op.drop_column('employee', 'avatar_url')
