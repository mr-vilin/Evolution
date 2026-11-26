"""规范同步状态、任务、明细、系统设置与租约。"""
from alembic import context, op
from alembic.script import ScriptDirectory
import sqlalchemy as sa

revision = '0025_sync_schema'
down_revision = '0024_organization_schema'
branch_labels = None
depends_on = None

_UP = {'dataset_state': ["MODIFY COLUMN data_version BIGINT UNSIGNED NOT NULL COMMENT '已提交数据版本号'",
                   'ADD COLUMN create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '
                   "'本地数据集状态记录创建UTC时间，存量以迁移时刻为起点'",
                   'ADD COLUMN update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '
                   "'本地数据集状态记录最后变更UTC时间'"],
 'pending_fact': ["ADD COLUMN create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '本地待核实事实记录创建UTC时间，存量以迁移时刻为起点'",
                  'ADD COLUMN update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '
                  "'本地待核实事实记录最后变更UTC时间'"],
 'sync_job_detail': ["MODIFY COLUMN attempt INT UNSIGNED NOT NULL COMMENT '对象处理尝试次数'",
                     'ADD COLUMN create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '
                     "'本地同步任务明细记录创建UTC时间，存量以迁移时刻为起点'",
                     'ADD COLUMN update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP '
                     "COMMENT '本地同步任务明细记录最后变更UTC时间'"],
 'system_setting': ['ADD COLUMN create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '
                    "'本地系统设置记录创建UTC时间，存量以迁移时刻为起点'",
                    'ADD COLUMN update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '
                    "'本地系统设置记录最后变更UTC时间'",
                    "CHANGE COLUMN `key` setting_key VARCHAR(128) NOT NULL COMMENT '系统设置键名'"],
 'worker_lease': ["MODIFY COLUMN generation INT UNSIGNED NOT NULL COMMENT '租约世代号'",
                  'ADD COLUMN create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '
                  "'本地Worker租约记录创建UTC时间，存量以迁移时刻为起点'",
                  'ADD COLUMN update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '
                  "'本地Worker租约记录最后变更UTC时间'"],
 'sync_job': ["MODIFY COLUMN attempt INT UNSIGNED NOT NULL COMMENT '任务尝试次数'",
              "MODIFY COLUMN lease_generation INT UNSIGNED NOT NULL COMMENT '任务租约世代号'",
              "MODIFY COLUMN execution_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '任务执行次数'",
              "MODIFY COLUMN retry_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '任务重试次数'",
              "MODIFY COLUMN total_count INT UNSIGNED NULL DEFAULT NULL COMMENT '任务对象总数'",
              "MODIFY COLUMN success_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '任务成功对象数'",
              "MODIFY COLUMN failure_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '任务失败对象数'",
              "CHANGE COLUMN created_at create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '任务创建时间'",
              'CHANGE COLUMN updated_at update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP '
              "COMMENT '任务更新时间'",
              "ADD COLUMN active_root_kind TINYINT UNSIGNED GENERATED ALWAYS AS (CASE WHEN status IN ('queued','running') "
              'THEN CASE WHEN root_department_id IS NULL THEN 0 ELSE 1 END ELSE NULL END) STORED COMMENT '
              "'活动任务根范围类型，0为全量，1为指定根，非活动任务为空'",
              "ADD COLUMN active_root_id VARCHAR(191) GENERATED ALWAYS AS (COALESCE(root_department_id, '')) STORED COMMENT "
              "'活动任务根范围标识，空根转换为空字符串'",
              'ADD UNIQUE KEY uk_sync_job_active_scope (type, active_root_kind, active_root_id)',
              'ADD INDEX idx_sync_job_create_time (create_time, id)',
              'ADD INDEX idx_sync_job_status_create_time (status, create_time, id)',
              'DROP INDEX ix_sync_job_status']}

_DOWN = {'dataset_state': ["MODIFY COLUMN data_version BIGINT NOT NULL COMMENT '已提交数据版本号'",
                   'DROP COLUMN update_time',
                   'DROP COLUMN create_time'],
 'pending_fact': ['DROP COLUMN update_time', 'DROP COLUMN create_time'],
 'sync_job_detail': ["MODIFY COLUMN attempt INT NOT NULL COMMENT '对象处理尝试次数'",
                     'DROP COLUMN update_time',
                     'DROP COLUMN create_time'],
 'system_setting': ['DROP COLUMN update_time',
                    'DROP COLUMN create_time',
                    "CHANGE COLUMN setting_key `key` VARCHAR(128) NOT NULL COMMENT '系统设置键名'"],
 'worker_lease': ["MODIFY COLUMN generation INT NOT NULL COMMENT '租约世代号'",
                  'DROP COLUMN update_time',
                  'DROP COLUMN create_time'],
 'sync_job': ["MODIFY COLUMN attempt INT NOT NULL COMMENT '任务尝试次数'",
              "MODIFY COLUMN lease_generation INT NOT NULL COMMENT '任务租约世代号'",
              "MODIFY COLUMN execution_count INT NOT NULL DEFAULT 0 COMMENT '任务执行次数'",
              "MODIFY COLUMN retry_count INT NOT NULL DEFAULT 0 COMMENT '任务重试次数'",
              "MODIFY COLUMN total_count INT NULL DEFAULT NULL COMMENT '任务对象总数'",
              "MODIFY COLUMN success_count INT NOT NULL DEFAULT 0 COMMENT '任务成功对象数'",
              "MODIFY COLUMN failure_count INT NOT NULL DEFAULT 0 COMMENT '任务失败对象数'",
              'DROP INDEX uk_sync_job_active_scope',
              'DROP INDEX idx_sync_job_create_time',
              'DROP INDEX idx_sync_job_status_create_time',
              'ADD INDEX ix_sync_job_status (status)',
              'DROP COLUMN active_root_id',
              'DROP COLUMN active_root_kind',
              "CHANGE COLUMN create_time created_at DATETIME NOT NULL COMMENT '任务创建时间'",
              "CHANGE COLUMN update_time updated_at DATETIME NOT NULL COMMENT '任务更新时间'"]}


_COUNTERS = {
    'dataset_state': ('data_version',),
    'worker_lease': ('generation',),
    'sync_job_detail': ('attempt',),
    'sync_job': ('attempt', 'lease_generation', 'execution_count', 'retry_count',
                 'total_count', 'success_count', 'failure_count'),
}


def _preflight(downgrade=False):
    bind = op.get_bind()
    for table, columns in _COUNTERS.items():
        limit = 9223372036854775807 if table == 'dataset_state' else 2147483647
        tests = [f'{column} > {limit}' if downgrade else f'{column} < 0' for column in columns]
        if bind.scalar(sa.text(f"SELECT 1 FROM {table} WHERE " + ' OR '.join(tests) + ' LIMIT 1')):
            raise RuntimeError(f'SYNC_SCHEMA_COUNTER_OUT_OF_RANGE: {table}')
    if not downgrade and bind.scalar(sa.text(
        "SELECT 1 FROM sync_job WHERE status IN ('queued','running') "
        "GROUP BY type, root_department_id HAVING COUNT(*) > 1 LIMIT 1"
    )):
        raise RuntimeError('SYNC_SCHEMA_DUPLICATE_ACTIVE_SCOPE')


def _apply(changes, upgrading):
    for table, clauses in changes.items():
        if not context.is_offline_mode():
            columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}
            if ('create_time' in columns) == upgrading:
                continue
        op.execute(sa.text(f'ALTER TABLE {table} ' + ', '.join(clauses)))


def upgrade():
    if not context.is_offline_mode():
        _preflight()
    _apply(_UP, True)


def downgrade():
    if not context.is_offline_mode():
        target = context.get_revision_argument()
        if target not in {down_revision, '0023_remove_connection_coverage', '0022_mysql_general_ci',
                          '0021_tencent_db_conventions', '0020_tencent_history', '-1', '-2', '-3', '-4'}:
            history = ScriptDirectory.from_config(context.config).get_revision('0020_tencent_history')
            history.module.check_downgrade(target)
        _preflight(downgrade=True)
    _apply(dict(reversed(list(_DOWN.items()))), False)
