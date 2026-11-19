"""历史检查点及领取优先级；不新增财务实体。业务执行另行授权。"""
from alembic import op,context
from sqlalchemy import text
revision='0020_tencent_history'
down_revision='0019_tencent_daily'
branch_labels=None
depends_on=None


def upgrade():
    op.execute("ALTER TABLE tencent_sync_config ADD COLUMN history_progress JSON NULL COMMENT '经类型校验的历史发现检查点，来源窗口不代表账号历史起点'")
    op.execute("ALTER TABLE tencent_sync_job ADD COLUMN priority INT NOT NULL DEFAULT 0 COMMENT '实际领取优先级：0近期或人工，20历史发现；活动重试保持资格', ADD INDEX ix_tencent_job_priority(config_id,status,priority,id)")
    # 只补领取元数据，不重写冻结范围/epoch或复活任务。月度及人工保留最近两个
    # 已到重检日期的自然月；日/周模式保留当月及上月，避免旧积压挡住近期。
    op.execute("""UPDATE tencent_sync_job j
        JOIN tencent_sync_config c ON c.id=j.config_id
        SET j.priority=20
        WHERE j.kind='period' AND j.status IN ('pending','retry_wait')
        AND j.month < DATE_FORMAT(DATE_SUB(
            CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','+08:00'),
            INTERVAL (CASE WHEN c.frequency IN ('daily','weekly') THEN 1
                WHEN DAY(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','+08:00'))>=3 THEN 2
                ELSE 3 END) MONTH),'%Y-%m')""")



def check_downgrade(target):
    if not context.is_offline_mode():
        bind=op.get_bind()
        if (bind.execute(text("SELECT id FROM tencent_sync_config WHERE history_progress IS NOT NULL AND JSON_TYPE(history_progress)!='NULL' LIMIT 1")).first()
            or bind.execute(text("SELECT id FROM tencent_sync_job WHERE priority<>0 OR JSON_UNQUOTE(JSON_EXTRACT(snapshot,'$.request_namespace')) IN ('manual-range-v1','history-discovery-v1') LIMIT 1")).first()):
            raise RuntimeError('TENCENT_HISTORY_DOWNGRADE_EVIDENCE: preserve history config and jobs; use application rollback')
        if target not in {down_revision,'-1'}:
            if (bind.execute(text("SELECT id FROM tencent_cost_period WHERE granularity='day' LIMIT 1")).first()
                or bind.execute(text("SELECT id FROM tencent_sync_config WHERE frequency IN ('daily','weekly') OR schedule_start_date IS NOT NULL LIMIT 1")).first()
                or bind.execute(text("SELECT id FROM tencent_sync_job WHERE JSON_UNQUOTE(JSON_EXTRACT(snapshot,'$.granularity'))='day' OR (status IN ('pending','running','retry_wait') AND JSON_UNQUOTE(JSON_EXTRACT(snapshot,'$.handler'))='tencent-cost-period-v2') LIMIT 1")).first()):
                raise RuntimeError('TENCENT_DAILY_DOWNGRADE_EVIDENCE: preserve daily evidence before any DDL')
            if target not in {'0018_tencent_monthly'} and bind.execute(text("SELECT id FROM tencent_sync_job WHERE kind='batch' LIMIT 1")).first():
                raise RuntimeError('TENCENT_MONTHLY_DOWNGRADE_EVIDENCE: preserve batch history before any DDL')


def downgrade():
    check_downgrade(context.get_revision_argument())
    op.drop_index('ix_tencent_job_priority',table_name='tencent_sync_job')
    op.drop_column('tencent_sync_job','priority')
    op.drop_column('tencent_sync_config','history_progress')
