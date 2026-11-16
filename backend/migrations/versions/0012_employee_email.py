"""仅新增可缺省的人员邮箱，不回填、不发起同步。"""
from alembic import op
import sqlalchemy as sa

revision = '0012_employee_email'
down_revision = '0011_organization_browser'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('employee', sa.Column('email', sa.String(254, collation='utf8mb4_bin'), nullable=True,
                  comment='飞书人员邮箱，缺省或不可读时为空，可读性记录于 field_readability'))


def downgrade():
    # 会删除已采集邮箱；须另行授权和备份。应用回退优先保留此兼容新增列。
    op.drop_column('employee', 'email')
