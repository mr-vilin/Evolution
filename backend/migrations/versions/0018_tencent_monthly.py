"""月度配置与纯汇总批次；业务库执行须另行授权。"""
from alembic import op, context
from sqlalchemy import text
revision = '0018_tencent_monthly'
down_revision = '0017_tencent_maintenance'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE tencent_sync_config MODIFY COLUMN frequency VARCHAR(32) NOT NULL COMMENT '执行频率：manual手动或monthly每月三日', ADD COLUMN execution_time VARCHAR(5) NOT NULL DEFAULT '13:30' COMMENT '月度计划的北京时间时分，默认建议13:30可修改', ADD COLUMN schedule_start_month VARCHAR(7) NULL COMMENT '首次启用月模式时的补漏起点，不代表已核验历史起点'")
    op.execute("ALTER TABLE tencent_sync_job ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'period' COMMENT '任务种类：batch纯汇总父批次或period实际期间', ADD COLUMN parent_job_id INTEGER NULL COMMENT '期间所属父批次标识，独立手动期间为空', MODIFY COLUMN month VARCHAR(7) NULL COMMENT '固定完整账月YYYY-MM，纯汇总父批次为空', ADD INDEX ix_tencent_sync_job_parent_job_id(parent_job_id), DROP INDEX uk_tencent_job_request, ADD UNIQUE KEY uk_tencent_job_request(config_id,dataset_epoch,kind,idempotency_key)")

def downgrade():
    if not context.is_offline_mode() and op.get_bind().execute(text("SELECT id FROM tencent_sync_job WHERE kind='batch' OR parent_job_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError('TENCENT_MONTHLY_DOWNGRADE_EVIDENCE: preserve batch evidence; use application rollback')
    op.execute("ALTER TABLE tencent_sync_job DROP INDEX uk_tencent_job_request, ADD UNIQUE KEY uk_tencent_job_request(config_id,dataset_epoch,idempotency_key)")
    op.drop_index('ix_tencent_sync_job_parent_job_id',table_name='tencent_sync_job')
    op.drop_column('tencent_sync_job','parent_job_id')
    op.drop_column('tencent_sync_job','kind')
    op.execute("ALTER TABLE tencent_sync_job MODIFY COLUMN month VARCHAR(7) NOT NULL COMMENT '固定完整账月YYYY-MM'")
    op.drop_column('tencent_sync_config','schedule_start_month')
    op.drop_column('tencent_sync_config','execution_time')
    op.execute("ALTER TABLE tencent_sync_config MODIFY COLUMN frequency VARCHAR(32) NOT NULL COMMENT '执行频率，本阶段仅manual手动'")
