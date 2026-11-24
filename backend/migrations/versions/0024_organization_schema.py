"""规范组织目录字段和索引，保留同步时间及关系数据。"""

from alembic import context, op
from alembic.script import ScriptDirectory
import sqlalchemy as sa


revision = '0024_organization_schema'
down_revision = '0023_remove_connection_coverage'
branch_labels = None
depends_on = None

_FLAGS = {
    'is_frozen': '飞书账号是否暂停，NULL 表示未知',
    'is_resigned': '飞书账号是否离职，NULL 表示未知',
    'is_activated': '飞书账号是否已激活，NULL 表示未知',
    'is_exited': '飞书账号是否主动退出，NULL 表示未知',
    'is_unjoin': '飞书账号是否未加入，NULL 表示未知',
}
_JOIN_COMMENT = '飞书入职时间 Unix 秒时间戳，按北京时间展示日期，未填写或不可读时为空'
_SYNC_COMMENT = '最近一次由同步流程写入或确认的UTC时间'
_PREVIOUS_SYNC_COMMENT = '最近一次从飞书看到的时间'


def _alter(table, clauses):
    op.execute(sa.text(f'ALTER TABLE {table} ' + ', '.join(clauses)))


def _timestamps(subject):
    return (
        "ADD COLUMN create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP "
        f"COMMENT '本地{subject}记录创建UTC时间，存量以迁移时刻为起点'",
        "ADD COLUMN update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP "
        f"COMMENT '本地{subject}记录最后变更UTC时间'",
    )


def _flag_definitions(column_type):
    return [
        f"MODIFY COLUMN {column} {column_type} NULL DEFAULT NULL COMMENT '{description}'"
        for column, description in _FLAGS.items()
    ]


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _preflight():
    bind = op.get_bind()
    root = 'is_root' if 'is_root' in _columns('department') else 'is_virtual_root'
    active = 'is_active' if 'is_active' in _columns('employee_department') else 'active'
    checks = (
        ('department', f"{root} NOT IN (0, 1) OR ({root} = 1) <> (id = '0')"),
        ('employee', ' OR '.join(['join_time < 0', *(f'{flag} NOT IN (0, 1)' for flag in _FLAGS)])),
        ('employee_department', f'is_primary NOT IN (0, 1) OR {active} NOT IN (0, 1)'),
    )
    for table, predicate in checks:
        if bind.scalar(sa.text(f'SELECT 1 FROM {table} WHERE {predicate} LIMIT 1')):
            raise RuntimeError(f'ORGANIZATION_SCHEMA_DATA_OUT_OF_RANGE: {table}')


def upgrade():
    offline = context.is_offline_mode()
    if not offline:
        _preflight()
    # 每张表使用一条原子 DDL。在线重试可跳过已经完成的表。
    if offline or 'is_root' not in _columns('department'):
        _alter('department', (
            "CHANGE COLUMN is_virtual_root is_root TINYINT UNSIGNED NOT NULL COMMENT '是否为组织树唯一根节点，部门ID为0'",
            f"CHANGE COLUMN last_seen_at last_sync_at DATETIME NULL DEFAULT NULL COMMENT '{_SYNC_COMMENT}'",
            "MODIFY COLUMN sync_quality VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci "
            "NOT NULL COMMENT '部门资料核验状态，用于同步监控和员工门店归属计算'",
            'RENAME INDEX feishu_department_id TO uk_feishu_department_id',
            'RENAME INDEX parent_id TO idx_parent_id',
            *_timestamps('部门'),
        ))
    if offline or 'last_sync_at' not in _columns('employee'):
        _alter('employee', (
            f"CHANGE COLUMN last_seen_at last_sync_at DATETIME NULL DEFAULT NULL COMMENT '{_SYNC_COMMENT}'",
            f"MODIFY COLUMN join_time BIGINT UNSIGNED NULL DEFAULT NULL COMMENT '{_JOIN_COMMENT}'",
            *_flag_definitions('TINYINT UNSIGNED'),
            "MODIFY COLUMN field_readability JSON NULL COMMENT '手机号、邮箱、头像、入职时间及账号标志的可读性：readable、not_collected、unreadable'",
            'RENAME INDEX feishu_user_id TO uk_feishu_user_id',
            'RENAME INDEX open_id TO uk_open_id',
            'RENAME INDEX primary_department_id TO idx_primary_department_id',
            *_timestamps('员工'),
        ))
    if offline or 'is_active' not in _columns('employee_department'):
        _alter('employee_department', (
            "CHANGE COLUMN active is_active TINYINT UNSIGNED NOT NULL COMMENT '关系是否有效'",
            "MODIFY COLUMN is_primary TINYINT UNSIGNED NOT NULL COMMENT '是否为主部门关系'",
            'RENAME INDEX department_id TO idx_department_id',
        ))


def downgrade():
    offline = context.is_offline_mode()
    if not offline:
        target = context.get_revision_argument()
        if target not in {down_revision, '0022_mysql_general_ci', '0021_tencent_db_conventions',
                          '0020_tencent_history', '-1', '-2', '-3'}:
            # 跨版本回退先沿用财务证据检查，避免拒绝前已提交组织表 DDL。
            history = ScriptDirectory.from_config(context.config).get_revision('0020_tencent_history')
            history.module.check_downgrade(target)
        _preflight()
        if op.get_bind().scalar(sa.text('SELECT 1 FROM employee WHERE join_time > 9223372036854775807 LIMIT 1')):
            raise RuntimeError('ORGANIZATION_SCHEMA_DATA_OUT_OF_RANGE: employee.join_time')
    if offline or 'is_active' in _columns('employee_department'):
        _alter('employee_department', (
            "CHANGE COLUMN is_active active TINYINT(1) NOT NULL COMMENT '关系是否有效'",
            "MODIFY COLUMN is_primary TINYINT(1) NOT NULL COMMENT '是否为主部门关系'",
            'RENAME INDEX idx_department_id TO department_id',
        ))
    if offline or 'last_sync_at' in _columns('employee'):
        _alter('employee', (
            f"CHANGE COLUMN last_sync_at last_seen_at DATETIME NULL DEFAULT NULL COMMENT '{_PREVIOUS_SYNC_COMMENT}'",
            f"MODIFY COLUMN join_time BIGINT NULL DEFAULT NULL COMMENT '{_JOIN_COMMENT}'",
            *_flag_definitions('TINYINT(1)'),
            "MODIFY COLUMN field_readability JSON NULL COMMENT '手机号和账号标志可读性：readable、not_collected、unreadable'",
            'RENAME INDEX uk_feishu_user_id TO feishu_user_id',
            'RENAME INDEX uk_open_id TO open_id',
            'RENAME INDEX idx_primary_department_id TO primary_department_id',
            'DROP COLUMN update_time',
            'DROP COLUMN create_time',
        ))
    if offline or 'is_root' in _columns('department'):
        _alter('department', (
            "CHANGE COLUMN is_root is_virtual_root TINYINT(1) NOT NULL COMMENT '是否为虚拟根部门'",
            f"CHANGE COLUMN last_sync_at last_seen_at DATETIME NULL DEFAULT NULL COMMENT '{_PREVIOUS_SYNC_COMMENT}'",
            "MODIFY COLUMN sync_quality VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '部门同步质量'",
            'RENAME INDEX uk_feishu_department_id TO feishu_department_id',
            'RENAME INDEX idx_parent_id TO parent_id',
            'DROP COLUMN update_time',
            'DROP COLUMN create_time',
        ))
