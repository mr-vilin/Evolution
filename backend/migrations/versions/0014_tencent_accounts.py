"""腾讯云账号与本模块实际请求事实；不改组织表，不触发采集。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import TINYINT

revision = '0014_tencent_accounts'
down_revision = '0013_employee_profile'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('tencent_account',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, comment='腾讯云账号内部标识'),
        sa.Column('uin', sa.String(191, collation='utf8mb4_bin'), nullable=False, comment='不可重新绑定的腾讯云主账号 UIN 字符串'),
        sa.Column('alias', sa.String(128), nullable=False, comment='管理员维护的中文账号别名'),
        sa.Column('credential_ref', sa.String(64, collation='utf8mb4_bin'), nullable=False, comment='后端受控凭据注册表引用，不保存可用密钥'),
        sa.Column('credential_revision', sa.Integer(), nullable=False, server_default='1', comment='账号凭据绑定修订号，用于隔离在途旧结果'),
        sa.Column('is_enabled', sa.Boolean().with_variant(TINYINT(unsigned=True), 'mysql'), nullable=False, server_default='1', comment='账号总开关：1启用，0停用并禁止新结果'),
        sa.Column('verification_status', sa.String(32), nullable=False, comment='归属验证状态，仅 verified 可执行查询'),
        sa.Column('verified_at', sa.DateTime(), nullable=False, comment='最近一次实际归属验证成功的 UTC 时间'),
        sa.Column('create_time', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), comment='账号登记 UTC 时间'),
        sa.Column('update_time', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='账号最后修改 UTC 时间'),
        sa.UniqueConstraint('uin', name='uk_tencent_account_uin'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_general_ci', comment='独立腾讯云账号及受控凭据绑定')
    op.create_table('tencent_api_call',
        sa.Column('id', sa.String(36, collation='utf8mb4_bin'), primary_key=True, comment='每次实际调用的唯一审计事件标识'),
        sa.Column('request_id', sa.String(36, collation='utf8mb4_bin'), nullable=False, comment='服务端生成的本次入站请求关联标识'),
        sa.Column('direction', sa.String(16), nullable=False, comment='调用方向：inbound入站，outbound腾讯云出站'),
        sa.Column('action', sa.String(64), nullable=False, comment='服务端登记的业务动作，未知为 unknown'),
        sa.Column('permission_code', sa.String(64), nullable=True, comment='本次服务端实际执行的独立权限动作'),
        sa.Column('actor_id', sa.String(191, collation='utf8mb4_bin'), nullable=True, comment='已认证管理员开放标识，匿名拒绝为空'),
        sa.Column('target_id', sa.String(191, collation='utf8mb4_bin'), nullable=True, comment='必要的账号 UIN 或外部操作目标，不保存财务正文'),
        sa.Column('method', sa.String(16), nullable=False, comment='实际 HTTP 方法或 SDK 调用方式'),
        sa.Column('route', sa.String(255), nullable=False, comment='规范接口模板或腾讯云官方动作名称'),
        sa.Column('status_code', sa.Integer(), nullable=True, comment='已观察到的 HTTP 状态码，未返回时为空'),
        sa.Column('outcome', sa.String(32), nullable=False, comment='调用结果：running、succeeded、failed、unknown'),
        sa.Column('reason_code', sa.String(64), nullable=True, comment='稳定错误码，不保存外部异常原文'),
        sa.Column('upstream_request_id', sa.String(128), nullable=True, comment='腾讯云返回的请求标识，不保存余额或账单'),
        sa.Column('started_at', sa.DateTime(), nullable=False, comment='实际调用开始 UTC 时间'),
        sa.Column('returned_at', sa.DateTime(), nullable=True, comment='观察到实际响应返回的 UTC 时间，未观测为空'),
        sa.Column('finished_at', sa.DateTime(), nullable=True, comment='调用结束 UTC 时间，未结束为空'),
        sa.Column('duration_ms', sa.Integer(), nullable=True, comment='单调时钟测量的实际耗时毫秒数'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_general_ci', comment='腾讯云模块实际请求事实，元信息白名单且不保存财务正文')
    op.create_index('ix_tencent_api_call_request_id','tencent_api_call',['request_id'])
    # 余额限流按账号读取最近调用窗口，避免审计历史增长后全表扫描。
    op.create_index('ix_tencent_api_call_rate_window','tencent_api_call',['direction','action','target_id','started_at'])


def downgrade():
    # 只允许在已确认无业务记录或已备份恢复时执行，禁止以删审计表充当运行回退。
    op.drop_table('tencent_api_call')
    op.drop_table('tencent_account')
