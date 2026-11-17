"""腾讯云有界重试与实际返回捕获；业务环境执行须另行授权。"""
from alembic import context, op
from sqlalchemy import text

revision = '0016_tencent_recovery'
down_revision = '0015_tencent_cost'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE tencent_sync_config MODIFY COLUMN revision INTEGER UNSIGNED NOT NULL DEFAULT '1' COMMENT '配置并发修订号，普通编辑仅影响新轮次', ADD COLUMN control_revision INTEGER UNSIGNED NOT NULL DEFAULT '1' COMMENT '启停控制修订号，隔离停用前旧任务', ADD COLUMN run_policy JSON NULL COMMENT '经过校验的重试预算、租约心跳及排队策略'")
    op.execute("UPDATE tencent_sync_config SET control_revision=revision")
    op.execute("ALTER TABLE tencent_sync_job MODIFY COLUMN status VARCHAR(32) NOT NULL COMMENT '任务状态pending、running、retry_wait、succeeded或failed'")
    op.execute("ALTER TABLE tencent_sync_attempt MODIFY COLUMN status VARCHAR(32) NOT NULL COMMENT '尝试状态running、succeeded、failed或unknown'")
    op.execute("ALTER TABLE tencent_sync_job ADD COLUMN dataset_epoch VARCHAR(191) COLLATE utf8mb4_bin NULL COMMENT '受理时冻结的初始化世代，用于隔离幂等键'")
    op.execute("UPDATE tencent_sync_job SET dataset_epoch=JSON_UNQUOTE(JSON_EXTRACT(snapshot,'$.dataset_epoch'))")
    op.execute("ALTER TABLE tencent_sync_job MODIFY COLUMN dataset_epoch VARCHAR(191) COLLATE utf8mb4_bin NOT NULL COMMENT '受理时冻结的初始化世代，用于隔离幂等键', DROP INDEX uk_tencent_job_request, ADD UNIQUE KEY uk_tencent_job_request(config_id,dataset_epoch,idempotency_key)")
    op.execute("ALTER TABLE tencent_sync_job ADD COLUMN next_attempt_at DATETIME NULL COMMENT '等待重试最早可领取UTC时刻', ADD COLUMN deadline_at DATETIME NULL COMMENT '首次领取后执行与重试共同截止UTC时刻', ADD COLUMN queue_deadline_at DATETIME NULL COMMENT '受理后首次领取排队截止UTC时刻'")
    op.execute("UPDATE tencent_sync_job SET queue_deadline_at=DATE_ADD(create_time,INTERVAL 86400 SECOND), deadline_at=CASE WHEN started_at IS NULL THEN NULL ELSE DATE_ADD(started_at,INTERVAL 900 SECOND) END")
    op.execute("ALTER TABLE tencent_sync_job ADD COLUMN source_job_id INTEGER NULL COMMENT '人工重跑关联的原逻辑任务，首次采集为空', ADD COLUMN commit_receipt JSON NULL COMMENT '与费用同事务保存的原始提交回执，用于归档恢复'")
    op.execute("UPDATE tencent_sync_job AS j JOIN tencent_sync_attempt AS a ON a.job_id=j.id AND a.status='succeeded' SET j.commit_receipt=a.execution_output WHERE j.status='succeeded' AND a.execution_output IS NOT NULL")
    op.execute("ALTER TABLE tencent_sync_attempt ADD COLUMN return_state VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN' COMMENT '实际返回形态VALUE、NOT_RETURNED或UNKNOWN'")
    op.execute("ALTER TABLE tencent_sync_attempt ADD COLUMN request_id VARCHAR(36) COLLATE utf8mb4_bin NULL COMMENT '本尝试独立请求关联标识，历史未采集时为空', ADD COLUMN failure_evidence JSON NULL COMMENT '稳定失败分类与已核实上游请求标识，不保存报文'")
    op.execute("UPDATE tencent_sync_attempt SET return_state=CASE WHEN status='succeeded' AND execution_output IS NOT NULL THEN 'VALUE' WHEN status='failed' THEN 'NOT_RETURNED' ELSE 'UNKNOWN' END")


def downgrade():
    # 仅在已授权、已备份且worker静默的恢复演练中执行；常规应用回退保留证据。
    # 降级前必须预检跨世代重复键；存在时拒绝，保留原证据而不删除任务。
    if not context.is_offline_mode():
        duplicate=op.get_bind().execute(text('SELECT config_id,idempotency_key FROM tencent_sync_job GROUP BY config_id,idempotency_key HAVING COUNT(*)>1 LIMIT 1')).first()
        if duplicate is not None:
            raise RuntimeError('TENCENT_RECOVERY_DOWNGRADE_CONFLICT: cross-epoch keys require preserving this schema')
    op.execute("ALTER TABLE tencent_sync_job DROP INDEX uk_tencent_job_request, ADD UNIQUE KEY uk_tencent_job_request(config_id,idempotency_key)")
    op.drop_column('tencent_sync_job', 'dataset_epoch')
    op.drop_column('tencent_sync_job', 'source_job_id')
    op.drop_column('tencent_sync_job', 'commit_receipt')
    op.drop_column('tencent_sync_attempt', 'return_state')
    op.drop_column('tencent_sync_job', 'queue_deadline_at')
    op.drop_column('tencent_sync_job', 'deadline_at')
    op.drop_column('tencent_sync_job', 'next_attempt_at')
    op.drop_column('tencent_sync_config', 'run_policy')
    op.drop_column('tencent_sync_config', 'control_revision')
    op.execute("ALTER TABLE tencent_sync_config MODIFY COLUMN revision INTEGER UNSIGNED NOT NULL DEFAULT '1' COMMENT '配置修订号，变更使旧执行失效'")
    op.drop_column('tencent_sync_attempt', 'failure_evidence')
    op.drop_column('tencent_sync_attempt', 'request_id')
    op.execute("ALTER TABLE tencent_sync_job MODIFY COLUMN status VARCHAR(32) NOT NULL COMMENT '任务状态pending、running、succeeded或failed'")
    op.execute("ALTER TABLE tencent_sync_attempt MODIFY COLUMN status VARCHAR(32) NOT NULL COMMENT '尝试状态running、succeeded或failed'")
