"""统一业务字符串列的排序规则。"""

from alembic import context, op
from alembic.script import ScriptDirectory

revision = '0022_mysql_general_ci'
down_revision = '0021_tencent_db_conventions'
branch_labels = None
depends_on = None

GENERAL = 'utf8mb4_general_ci'
BINARY = 'utf8mb4_bin'

# 冻结自 0021 的实际 DDL，修改时显式保留字段类型、默认值和中文备注。
COLUMNS = {
    'admin_allowlist': (
        "`open_id` varchar(191) {collation} NOT NULL COMMENT '管理员飞书开放标识'",
    ),
    'admin_session': (
        "`id` varchar(191) {collation} NOT NULL COMMENT '管理员会话内部标识'",
        "`open_id` varchar(191) {collation} NOT NULL COMMENT '管理员飞书开放标识'",
        "`token_digest` varchar(64) {collation} NOT NULL COMMENT '管理员会话令牌 SHA-256 摘要'",
    ),
    'api_client': (
        "`id` varchar(191) {collation} NOT NULL COMMENT 'API 客户端标识'",
    ),
    'change_log': (
        "`object_id` varchar(191) {collation} NOT NULL COMMENT '变更对象标识'",
        "`job_id` varchar(191) {collation} DEFAULT NULL COMMENT '关联同步任务标识'",
    ),
    'dataset_state': (
        "`dataset_epoch` varchar(191) {collation} NOT NULL COMMENT '数据集世代标识'",
    ),
    'department': (
        "`id` varchar(191) {collation} NOT NULL COMMENT '内部部门稳定标识'",
        "`feishu_department_id` varchar(191) {collation} NOT NULL COMMENT '飞书部门标识'",
        "`parent_id` varchar(191) {collation} DEFAULT NULL COMMENT '父部门标识'",
        "`leader_user_id` varchar(191) {collation} DEFAULT NULL COMMENT '部门负责人用户标识'",
    ),
    'employee': (
        "`id` varchar(191) {collation} NOT NULL COMMENT '内部员工稳定标识'",
        "`feishu_user_id` varchar(191) {collation} NOT NULL COMMENT '飞书用户标识'",
        "`open_id` varchar(191) {collation} DEFAULT NULL COMMENT '飞书用户开放标识'",
        "`primary_department_id` varchar(191) {collation} DEFAULT NULL COMMENT '主部门标识'",
        "`employee_type_id` varchar(191) {collation} DEFAULT NULL COMMENT '员工类型枚举选项标识'",
        "`leader_user_id` varchar(191) {collation} DEFAULT NULL COMMENT '直属上级用户标识'",
        "`permission_role_id` varchar(191) {collation} DEFAULT NULL COMMENT '权限角色选项标识'",
        "`store_attribute_id` varchar(191) {collation} DEFAULT NULL COMMENT '门店属性选项标识'",
        "`mobile` varchar(128) {collation} DEFAULT NULL COMMENT '飞书完整手机号，空值含义由字段可读性说明'",
        "`email` varchar(254) {collation} DEFAULT NULL COMMENT '飞书人员邮箱，缺省或不可读时为空，可读性记录于 field_readability'",
        "`avatar_url` varchar(2048) {collation} DEFAULT NULL COMMENT '飞书人员头像 HTTPS 地址，缺省或不可读时为空'",
    ),
    'employee_department': (
        "`employee_id` varchar(191) {collation} NOT NULL COMMENT '员工标识'",
        "`department_id` varchar(191) {collation} NOT NULL COMMENT '部门标识'",
    ),
    'employee_store': (
        "`employee_id` varchar(191) {collation} NOT NULL COMMENT '员工标识'",
        "`store_id` varchar(191) {collation} NOT NULL COMMENT '门店部门标识'",
    ),
    'event_inbox': (
        "`event_id` varchar(191) {collation} NOT NULL COMMENT '飞书事件标识'",
        "`object_id` varchar(191) {collation} DEFAULT NULL COMMENT '事件对象标识'",
    ),
    'feishu_connection': (
        "`tenant_key` varchar(191) {collation} DEFAULT NULL COMMENT '飞书租户标识'",
        "`app_id` varchar(191) {collation} NOT NULL COMMENT '飞书应用标识'",
    ),
    'login_identity': (
        "`open_id` varchar(191) {collation} NOT NULL COMMENT '飞书开放标识'",
        "`user_id` varchar(191) {collation} NOT NULL COMMENT '飞书用户标识'",
        "`tenant_key` varchar(191) {collation} NOT NULL COMMENT '飞书租户标识'",
    ),
    'operation_receipt': (
        "`operation_id` varchar(191) {collation} NOT NULL COMMENT 'Agent 能力调用的一次操作稳定标识'",
        "`idempotency_key` varchar(191) {collation} NOT NULL COMMENT '用于防止重复提交的幂等键'",
        "`actor_id` varchar(191) {collation} NOT NULL COMMENT '调用主体的稳定身份标识'",
        "`run_id` varchar(191) {collation} DEFAULT NULL COMMENT '关联的 Agent 运行标识'",
        "`case_id` varchar(191) {collation} DEFAULT NULL COMMENT '关联的 Evaluation 用例标识'",
        "`job_id` varchar(191) {collation} DEFAULT NULL COMMENT '关联的同步任务标识'",
        "`before_epoch` varchar(191) {collation} NOT NULL COMMENT '请求开始时的数据集世代标识'",
        "`committed_epoch` varchar(191) {collation} DEFAULT NULL COMMENT '业务提交后的数据集世代标识'",
    ),
    'pending_fact': (
        "`source_id` varchar(191) {collation} NOT NULL COMMENT '待核实来源标识'",
    ),
    'store_code_reservation': (
        "`store_code` varchar(128) {collation} NOT NULL COMMENT '预留门店编码'",
        "`department_id` varchar(191) {collation} NOT NULL COMMENT '占用该编码的部门标识'",
    ),
    'store_profile': (
        "`department_id` varchar(191) {collation} NOT NULL COMMENT '门店对应部门标识'",
        "`store_code` varchar(128) {collation} DEFAULT NULL COMMENT '门店编码'",
    ),
    'sync_job': (
        "`id` varchar(191) {collation} NOT NULL COMMENT '同步任务标识'",
        "`root_department_id` varchar(191) {collation} DEFAULT NULL COMMENT '子树同步根部门标识'",
    ),
    'sync_job_detail': (
        "`job_id` varchar(191) {collation} NOT NULL COMMENT '所属同步任务标识'",
        "`object_id` varchar(191) {collation} NOT NULL COMMENT '任务对象标识'",
    ),
    'sync_staging': (
        "`job_id` varchar(191) {collation} NOT NULL COMMENT '所属同步任务标识'",
        "`source_id` varchar(191) {collation} NOT NULL COMMENT '来源对象标识'",
    ),
    'system_setting': (
        "`key` varchar(128) {collation} NOT NULL COMMENT '系统设置键名'",
    ),
    'tencent_account': (
        "`uin` varchar(191) {collation} NOT NULL COMMENT '不可重新绑定的腾讯云主账号 UIN 字符串'",
        "`credential_ref` varchar(64) {collation} NOT NULL COMMENT '后端受控凭据注册表引用，不保存可用密钥'",
    ),
    'tencent_api_call': (
        "`id` varchar(36) {collation} NOT NULL COMMENT '每次实际调用的唯一审计事件标识'",
        "`request_id` varchar(36) {collation} NOT NULL COMMENT '服务端生成的本次入站请求关联标识'",
        "`actor_id` varchar(191) {collation} DEFAULT NULL COMMENT '已认证管理员开放标识，匿名拒绝为空'",
        "`target_id` varchar(191) {collation} DEFAULT NULL COMMENT '必要的账号 UIN 或外部操作目标，不保存财务正文'",
    ),
    'tencent_cost_item': (
        "`business_code` varchar(191) {collation} DEFAULT NULL COMMENT '可靠映射的产品BusinessCode，不是子产品ProductCode'",
    ),
    'tencent_sync_attempt': (
        "`owner` varchar(36) {collation} NOT NULL COMMENT '本次执行者标识'",
        "`request_id` varchar(36) {collation} DEFAULT NULL COMMENT '本尝试独立请求关联标识，历史未采集时为空'",
    ),
    'tencent_sync_config': (
        "`owner` varchar(36) {collation} DEFAULT NULL COMMENT '本配置当前执行者标识'",
    ),
    'tencent_sync_job': (
        "`idempotency_key` varchar(128) {collation} NOT NULL COMMENT '配置内可靠请求幂等键'",
        "`request_id` varchar(36) {collation} NOT NULL COMMENT '受理请求的服务端关联标识'",
        "`dataset_epoch` varchar(191) {collation} NOT NULL COMMENT '受理时冻结的初始化世代，用于隔离幂等键'",
    ),
    'worker_lease': (
        "`owner` varchar(191) {collation} DEFAULT NULL COMMENT '当前 worker 标识'",
    ),
}

# 0021 的现有外键均为单列且使用默认的 RESTRICT 行为。
FOREIGN_KEYS = (
    ('department', 'department_ibfk_1', 'parent_id', 'department', 'id'),
    ('employee', 'employee_ibfk_1', 'primary_department_id', 'department', 'id'),
    ('employee_department', 'employee_department_ibfk_1', 'employee_id', 'employee', 'id'),
    ('employee_department', 'employee_department_ibfk_2', 'department_id', 'department', 'id'),
    ('employee_store', 'employee_store_ibfk_1', 'employee_id', 'employee', 'id'),
    ('employee_store', 'employee_store_ibfk_2', 'store_id', 'department', 'id'),
    ('store_code_reservation', 'store_code_reservation_ibfk_1', 'department_id', 'department', 'id'),
    ('store_profile', 'store_profile_ibfk_1', 'department_id', 'department', 'id'),
    ('sync_job_detail', 'sync_job_detail_ibfk_1', 'job_id', 'sync_job', 'id'),
    ('sync_staging', 'sync_staging_ibfk_1', 'job_id', 'sync_job', 'id'),
)

TARGET_COLUMNS = {
    (table, definition.split('`')[1])
    for table, definitions in COLUMNS.items()
    for definition in definitions
}


def _column(name):
    return '`' + name.replace('`', '``') + '`'


def _check_data(connection, collation):
    # 唯一索引中含 NULL 的键可以重复，按索引的完整列组合和前缀检查。
    indexes = {}
    for table, index, column, length in connection.exec_driver_sql("""
        SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, SUB_PART
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND NON_UNIQUE = 0
        ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
    """):
        indexes.setdefault((table, index), []).append((column, length))

    for (table, index), columns in indexes.items():
        if not any((table, column) in TARGET_COLUMNS for column, _ in columns):
            continue
        group = []
        for column, length in columns:
            value = _column(column)
            if length:
                value = f'LEFT({value}, {int(length)})'
            if (table, column) in TARGET_COLUMNS:
                value += f' COLLATE {collation}'
            group.append(value)
        nonnull = ' AND '.join(f'{_column(column)} IS NOT NULL' for column, _ in columns)
        duplicate = connection.exec_driver_sql(
            f'SELECT 1 FROM {_column(table)} WHERE {nonnull} '
            f'GROUP BY {", ".join(group)} HAVING COUNT(*) > 1 LIMIT 1'
        ).first()
        if duplicate:
            raise RuntimeError(f'COLLATION_UNIQUE_CONFLICT: {table}.{index}')

    for table, name, column, parent, parent_column in FOREIGN_KEYS:
        child_value = f'child.{_column(column)}'
        parent_value = f'parent.{_column(parent_column)}'
        orphan = connection.exec_driver_sql(
            f'SELECT 1 FROM {_column(table)} AS child WHERE {child_value} IS NOT NULL '
            f'AND NOT EXISTS (SELECT 1 FROM {_column(parent)} AS parent '
            f'WHERE {parent_value} COLLATE {collation} = {child_value} COLLATE {collation}) LIMIT 1'
        ).first()
        if orphan:
            raise RuntimeError(f'COLLATION_FOREIGN_KEY_CONFLICT: {table}.{name}')


def _change_collation(collation):
    pending = TARGET_COLUMNS
    if not context.is_offline_mode():
        connection = op.get_bind()
        _check_data(connection, collation)
        pending = {
            (table, column)
            for table, column, rule in connection.exec_driver_sql("""
                SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME
                FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()
            """)
            if (table, column) in TARGET_COLUMNS and rule != collation
        }

    # 停写期间先验证目标规则下的外键，再成对修改关联列。
    # 仅暂停当前迁移会话的检查，保留原外键及其隐式支撑索引。
    op.execute('SET @evolution_0022_fk_checks = @@SESSION.FOREIGN_KEY_CHECKS')
    op.execute('SET SESSION FOREIGN_KEY_CHECKS = 0')
    try:
        for table, definitions in COLUMNS.items():
            changes = [
                'MODIFY COLUMN ' + definition.format(collation=f'CHARACTER SET utf8mb4 COLLATE {collation}')
                for definition in definitions
                if (table, definition.split('`')[1]) in pending
            ]
            if changes:
                op.execute(f'ALTER TABLE {_column(table)} {", ".join(changes)}')
    finally:
        op.execute('SET SESSION FOREIGN_KEY_CHECKS = @evolution_0022_fk_checks')


def upgrade():
    _change_collation(GENERAL)


def downgrade():
    if not context.is_offline_mode():
        target = context.get_revision_argument()
        if target not in {down_revision, '0020_tencent_history', '-1', '-2'}:
            history = ScriptDirectory.from_config(context.config).get_revision('0020_tencent_history')
            history.module.check_downgrade(target)
    _change_collation(BINARY)
