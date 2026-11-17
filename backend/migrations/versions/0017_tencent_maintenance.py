"""账号维护并发修订；业务环境执行须另行授权。"""
from alembic import op

revision = '0017_tencent_maintenance'
down_revision = '0016_tencent_recovery'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE tencent_account ADD COLUMN revision INTEGER UNSIGNED NOT NULL DEFAULT '1' COMMENT '账号维护并发修订号，每次有效维护递增', MODIFY COLUMN credential_revision INTEGER NOT NULL DEFAULT '1' COMMENT '账号安全修订号，凭据轮换或启停后隔离旧在途结果'")


def downgrade():
    # 先静默账号维护入口并保存版本证据；常规应用回退保留前向兼容结构。
    op.drop_column('tencent_account', 'revision')
    op.execute("ALTER TABLE tencent_account MODIFY COLUMN credential_revision INTEGER NOT NULL DEFAULT '1' COMMENT '账号凭据绑定修订号，用于隔离在途旧结果'")
