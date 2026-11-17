"""腾讯云手动完整月成本闭环；仅新增五表，不执行采集。"""
from alembic import op
revision = '0015_tencent_cost'
down_revision = '0014_tencent_accounts'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE tencent_sync_config (
	id INTEGER NOT NULL COMMENT '腾讯云业务配置标识' AUTO_INCREMENT, 
	account_id INTEGER NOT NULL COMMENT '所属腾讯云账号标识', 
	business VARCHAR(32) NOT NULL COMMENT '业务类型，cost表示成本', 
	is_enabled TINYINT UNSIGNED NOT NULL COMMENT '成本能力开关，默认关闭' DEFAULT '0', 
	revision INTEGER UNSIGNED NOT NULL COMMENT '配置修订号，变更使旧执行失效' DEFAULT '1', 
	frequency VARCHAR(32) NOT NULL COMMENT '执行频率，本阶段仅manual手动', 
	currency VARCHAR(3) NOT NULL COMMENT '境内账单声明币种，不由源接口返回', 
	owner VARCHAR(36) COLLATE utf8mb4_bin COMMENT '本配置当前执行者标识', 
	generation INTEGER UNSIGNED NOT NULL COMMENT '配置执行资格递增代次' DEFAULT '0', 
	lease_expires_at DATETIME COMMENT '执行资格到期UTC时刻', 
	active_job_id INTEGER COMMENT '本配置正在执行的任务标识', 
	last_success_month VARCHAR(7) COMMENT '最近一次完整提交的账月', 
	create_time DATETIME NOT NULL COMMENT '配置创建UTC时间' DEFAULT CURRENT_TIMESTAMP, 
	update_time DATETIME NOT NULL COMMENT '配置更新UTC时间' DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uk_tencent_config_business UNIQUE (account_id, business)
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='腾讯云账号按业务独立配置及执行互斥' COLLATE utf8mb4_general_ci
""")
    op.execute("""
CREATE TABLE tencent_sync_job (
	id INTEGER NOT NULL COMMENT '一次逻辑成本任务标识' AUTO_INCREMENT, 
	config_id INTEGER NOT NULL COMMENT '所属业务配置标识', 
	account_id INTEGER NOT NULL COMMENT '所属腾讯云账号标识', 
	idempotency_key VARCHAR(128) COLLATE utf8mb4_bin NOT NULL COMMENT '配置内可靠请求幂等键', 
	month VARCHAR(7) NOT NULL COMMENT '固定完整账月YYYY-MM', 
	status VARCHAR(32) NOT NULL COMMENT '任务状态pending、running、succeeded或failed', 
	snapshot JSON NOT NULL COMMENT '冻结配置、口径、范围、可信发起身份及初始化世代，不含秘密', 
	request_id VARCHAR(36) COLLATE utf8mb4_bin NOT NULL COMMENT '受理请求的服务端关联标识', 
	error_code VARCHAR(64) COMMENT '最终稳定失败编码', 
	started_at DATETIME COMMENT '首次实际执行UTC时刻', 
	finished_at DATETIME COMMENT '任务终结UTC时刻', 
	create_time DATETIME NOT NULL COMMENT '任务可靠受理UTC时间' DEFAULT CURRENT_TIMESTAMP, 
	update_time DATETIME NOT NULL COMMENT '任务状态更新UTC时间' DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uk_tencent_job_request UNIQUE (config_id, idempotency_key)
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='腾讯云单月逻辑执行任务，不依赖浏览器会话存活' COLLATE utf8mb4_general_ci
""")
    op.execute('CREATE INDEX idx_tencent_job_claim ON tencent_sync_job (status, config_id, id)')
    op.execute("""
CREATE TABLE tencent_sync_attempt (
	id INTEGER NOT NULL COMMENT '一次真实执行尝试标识' AUTO_INCREMENT, 
	job_id INTEGER NOT NULL COMMENT '所属逻辑任务标识', 
	attempt_no INTEGER UNSIGNED NOT NULL COMMENT '任务内实际尝试序号，从1开始', 
	generation INTEGER UNSIGNED NOT NULL COMMENT '领取时的配置执行资格代次', 
	owner VARCHAR(36) COLLATE utf8mb4_bin NOT NULL COMMENT '本次执行者标识', 
	status VARCHAR(32) NOT NULL COMMENT '尝试状态running、succeeded或failed', 
	execution_input JSON NOT NULL COMMENT '执行前可靠保存的完整脱敏实际入参', 
	execution_output JSON COMMENT '处理器实际返回的原子提交回执，不保存账单原文', 
	error_code VARCHAR(64) COMMENT '明确失败或未知的稳定原因编码', 
	started_at DATETIME NOT NULL COMMENT '尝试开始UTC时刻', 
	finished_at DATETIME COMMENT '尝试终结UTC时刻', 
	create_time DATETIME NOT NULL COMMENT '尝试事实创建UTC时间' DEFAULT CURRENT_TIMESTAMP, 
	update_time DATETIME NOT NULL COMMENT '尝试事实更新UTC时间' DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uk_tencent_attempt_number UNIQUE (job_id, attempt_no)
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='腾讯云真实尝试事实，失败记录独立于费用回滚' COLLATE utf8mb4_general_ci
""")
    op.execute("""
CREATE TABLE tencent_cost_period (
	id INTEGER NOT NULL COMMENT '当前完整费用期间标识' AUTO_INCREMENT, 
	account_id INTEGER NOT NULL COMMENT '所属腾讯云账号标识', 
	month VARCHAR(7) NOT NULL COMMENT 'Asia/Shanghai完整账月YYYY-MM', 
	currency VARCHAR(3) NOT NULL COMMENT '独立金额维度的账单声明币种', 
	total NUMERIC(24, 8) NOT NULL COMMENT '费用账单总费用，保留8位小数及负退款', 
	coverage JSON NOT NULL COMMENT '完整边界、费用口径及零值和完整性证明摘要', 
	latest_job_id INTEGER NOT NULL COMMENT '最近成功提交本期间的任务标识', 
	latest_attempt_id INTEGER NOT NULL COMMENT '最近成功提交本期间的尝试标识', 
	create_time DATETIME NOT NULL COMMENT '期间首次创建UTC时间' DEFAULT CURRENT_TIMESTAMP, 
	update_time DATETIME NOT NULL COMMENT '完整期间最后替换UTC时间' DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uk_tencent_period_scope UNIQUE (account_id, month, currency)
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='腾讯云当前完整月费用及一致覆盖回执' COLLATE utf8mb4_general_ci
""")
    op.execute("""
CREATE TABLE tencent_cost_item (
	id INTEGER NOT NULL COMMENT '期间内费用产品行标识，不假设跨期稳定' AUTO_INCREMENT, 
	period_id INTEGER NOT NULL COMMENT '所属完整费用期间标识', 
	row_no INTEGER UNSIGNED NOT NULL COMMENT '本次全量结果内产品行序号', 
	business_code VARCHAR(191) COLLATE utf8mb4_bin COMMENT '可靠映射的产品BusinessCode，不是子产品ProductCode', 
	source_name VARCHAR(255) NOT NULL COMMENT '源接口原始产品显示名称', 
	mapping_status VARCHAR(32) NOT NULL COMMENT '产品映射状态mapped、ambiguous或unmapped', 
	amount NUMERIC(24, 8) NOT NULL COMMENT '该完整账月的产品总费用，保留负退款', 
	create_time DATETIME NOT NULL COMMENT '当前产品行创建UTC时间' DEFAULT CURRENT_TIMESTAMP, 
	update_time DATETIME NOT NULL COMMENT '当前产品行最后更新UTC时间' DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uk_tencent_item_row UNIQUE (period_id, row_no)
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='完整月全量产品行，未映射和同名行保持独立' COLLATE utf8mb4_general_ci
""")


def downgrade():
    # 仅在独立隔离验证库或已授权、已备份且无业务数据时执行；运行回退保留五表。
    op.drop_table('tencent_cost_item')
    op.drop_table('tencent_cost_period')
    op.drop_table('tencent_sync_attempt')
    op.drop_table('tencent_sync_job')
    op.drop_table('tencent_sync_config')
