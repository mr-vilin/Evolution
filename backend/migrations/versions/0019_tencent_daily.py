"""日周真实期间；业务库执行须另行授权。"""
from alembic import op, context
from sqlalchemy import text
revision = '0019_tencent_daily'
down_revision = '0018_tencent_monthly'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE tencent_sync_config MODIFY COLUMN frequency VARCHAR(32) NOT NULL COMMENT '执行频率：manual手动、monthly每月三日、daily每日或weekly每周日', MODIFY COLUMN execution_time VARCHAR(5) NOT NULL DEFAULT '13:30' COMMENT '自动计划的北京时间时分，默认建议13:30可修改', ADD COLUMN schedule_start_date VARCHAR(10) NULL COMMENT '首次日周计划的补漏日期锚点，不代表已核验历史起点'")
    op.execute("ALTER TABLE tencent_cost_period ADD COLUMN granularity VARCHAR(8) NOT NULL DEFAULT 'month' COMMENT '来源真实粒度day单日或month完整月', ADD COLUMN period_key VARCHAR(10) NULL COMMENT '原始期间身份：月YYYY-MM或日YYYY-MM-DD'")
    op.execute("UPDATE tencent_cost_period SET period_key=month")
    op.execute("ALTER TABLE tencent_cost_period MODIFY COLUMN period_key VARCHAR(10) NOT NULL COMMENT '原始期间身份：月YYYY-MM或日YYYY-MM-DD', MODIFY COLUMN month VARCHAR(7) NOT NULL COMMENT 'Asia/Shanghai费用所属自然月YYYY-MM', DROP INDEX uk_tencent_period_scope, ADD UNIQUE KEY uk_tencent_period_scope(account_id,period_key,currency), ADD INDEX ix_tencent_period_month(account_id,currency,month)")
    op.execute("ALTER TABLE tencent_sync_job MODIFY COLUMN month VARCHAR(7) NULL COMMENT '实际日月期间所属自然月YYYY-MM，纯汇总父批次为空'")
    op.execute("ALTER TABLE tencent_cost_period COMMENT='腾讯云原始日月费用及一致覆盖回执'")
    op.execute("ALTER TABLE tencent_cost_item MODIFY COLUMN amount NUMERIC(24,8) NOT NULL COMMENT '该原始日月期间的产品总费用，保留负退款', COMMENT='原始期间全量产品行，未映射和同名行保持独立'")



def downgrade():
    if not context.is_offline_mode():
        bind=op.get_bind()
        if (bind.execute(text("SELECT id FROM tencent_cost_period WHERE granularity='day' LIMIT 1")).first()
            or bind.execute(text("SELECT id FROM tencent_sync_config WHERE frequency IN ('daily','weekly') OR schedule_start_date IS NOT NULL LIMIT 1")).first()
            or bind.execute(text("SELECT id FROM tencent_sync_job WHERE JSON_UNQUOTE(JSON_EXTRACT(snapshot,'$.granularity'))='day' LIMIT 1")).first()):
            raise RuntimeError('TENCENT_DAILY_DOWNGRADE_EVIDENCE: preserve daily config and task evidence; use application rollback')
        # MySQL DDL 非事务；跨过0018前先核对其证据门槛，避免先回退0019后才被拒绝。
        if (context.get_revision_argument() not in {down_revision,'-1'}
            and bind.execute(text("SELECT id FROM tencent_sync_job WHERE kind='batch' LIMIT 1")).first()):
            raise RuntimeError('TENCENT_MONTHLY_DOWNGRADE_EVIDENCE: preserve batch history; use application rollback')
        if bind.execute(text("SELECT id FROM tencent_sync_job WHERE status IN ('pending','running','retry_wait') AND JSON_UNQUOTE(JSON_EXTRACT(snapshot,'$.handler'))='tencent-cost-period-v2' LIMIT 1")).first():
            raise RuntimeError('TENCENT_DAILY_DOWNGRADE_EVIDENCE: old application cannot execute pending period-v2 contract')
    op.execute("ALTER TABLE tencent_sync_config MODIFY COLUMN frequency VARCHAR(32) NOT NULL COMMENT '执行频率：manual手动或monthly每月三日', MODIFY COLUMN execution_time VARCHAR(5) NOT NULL DEFAULT '13:30' COMMENT '月度计划的北京时间时分，默认建议13:30可修改'")
    op.execute("ALTER TABLE tencent_sync_job MODIFY COLUMN month VARCHAR(7) NULL COMMENT '固定完整账月YYYY-MM，纯汇总父批次为空'")
    op.execute("ALTER TABLE tencent_cost_period MODIFY COLUMN month VARCHAR(7) NOT NULL COMMENT 'Asia/Shanghai完整账月YYYY-MM', COMMENT='腾讯云当前完整月费用及一致覆盖回执'")
    op.execute("ALTER TABLE tencent_cost_item MODIFY COLUMN amount NUMERIC(24,8) NOT NULL COMMENT '该完整账月的产品总费用，保留负退款', COMMENT='完整月全量产品行，未映射和同名行保持独立'")
    op.execute("ALTER TABLE tencent_cost_period DROP INDEX uk_tencent_period_scope, ADD UNIQUE KEY uk_tencent_period_scope(account_id,month,currency), DROP INDEX ix_tencent_period_month")
    op.drop_column('tencent_cost_period','period_key')
    op.drop_column('tencent_cost_period','granularity')
    op.drop_column('tencent_sync_config','schedule_start_date')
