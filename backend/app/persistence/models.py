from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text as sql_text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.mysql import INTEGER, TINYINT


TABLE_ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_general_ci"}

def _table_args(comment: str) -> dict:
    return {**TABLE_ARGS, "comment": comment}
SOURCE_ID = String(191)


class _UpdateTimestamp(TextClause):
    """MySQL 服务端更新时间语义；SQLite 仅用于既有离线单测建表。"""
    inherit_cache = True


@compiles(_UpdateTimestamp, 'sqlite')
def _sqlite_update_timestamp(element, compiler, **kwargs):
    return 'CURRENT_TIMESTAMP'


class Base(DeclarativeBase):
    pass


class OAuthState(Base):
    __tablename__ = "oauth_state"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True, comment="OAuth 状态摘要")
    expires_at: Mapped[datetime] = mapped_column(DateTime, comment="OAuth 状态过期时间")
    __table_args__ = _table_args("OAuth 登录状态记录")


class LoginIdentity(Base):
    __tablename__ = "login_identity"
    open_id: Mapped[str] = mapped_column(SOURCE_ID, primary_key=True, comment="飞书开放标识")
    user_id: Mapped[str] = mapped_column(SOURCE_ID, comment="飞书用户标识")
    tenant_key: Mapped[str] = mapped_column(SOURCE_ID, comment="飞书租户标识")
    __table_args__ = _table_args("飞书登录身份映射")


class WorkerLease(Base):
    __tablename__ = "worker_lease"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="worker 租约单例标识")
    owner: Mapped[str | None] = mapped_column(SOURCE_ID, comment="当前 worker 标识")
    generation: Mapped[int] = mapped_column(Integer, default=0, comment="租约世代号")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, comment="租约过期时间")
    __table_args__ = _table_args("同步 Worker 租约")


class PendingFact(Base):
    __tablename__ = 'pending_fact'
    object_type: Mapped[str] = mapped_column(String(32),primary_key=True, comment="待核实对象类型")
    source_id: Mapped[str] = mapped_column(SOURCE_ID,primary_key=True, comment="待核实来源标识")
    normalized_data: Mapped[dict] = mapped_column(JSON, comment="待核实规范化数据")
    error_code: Mapped[str] = mapped_column(String(64), comment="待核实错误编码")
    updated_at: Mapped[datetime] = mapped_column(DateTime, comment="待核实记录更新时间")
    __table_args__ = _table_args("待核实同步事实")


class DatasetState(Base):
    __tablename__ = "dataset_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="数据集状态单例标识")
    dataset_epoch: Mapped[str] = mapped_column(SOURCE_ID, comment="数据集世代标识")
    data_version: Mapped[int] = mapped_column(BigInteger, default=0, comment="已提交数据版本号")
    initialization_status: Mapped[str] = mapped_column(String(32), default="pending", comment="初始化状态")
    coverage_status: Mapped[str] = mapped_column(String(32), default="unknown", comment="通讯录覆盖状态")
    last_full_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最近一次全量同步时间")
    __table_args__ = _table_args("组织数据集状态单例")


class SystemSetting(Base):
    __tablename__ = "system_setting"
    key: Mapped[str] = mapped_column(String(128), primary_key=True, comment="系统设置键名")
    value: Mapped[str] = mapped_column(Text, comment="系统设置值")
    __table_args__ = _table_args("系统设置")


class Department(Base):
    __tablename__ = "department"
    id: Mapped[str] = mapped_column(SOURCE_ID, primary_key=True, comment="内部部门稳定标识")
    feishu_department_id: Mapped[str] = mapped_column(SOURCE_ID, unique=True, comment="飞书部门标识")
    parent_id: Mapped[str | None] = mapped_column(SOURCE_ID, ForeignKey("department.id"), comment="父部门标识")
    name: Mapped[str] = mapped_column(String(255), comment="部门名称")
    sort_order: Mapped[int] = mapped_column(Integer().with_variant(INTEGER(unsigned=True), 'mysql'), default=0, server_default='0', comment="同父级共享的本地展示顺序，非负整数，普通同步保留")
    leader_user_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment="部门负责人用户标识")
    status: Mapped[str] = mapped_column(String(32), default="active", comment="部门状态")
    sync_quality: Mapped[str] = mapped_column(String(32), default="unknown", comment="部门同步质量")
    is_virtual_root: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否为虚拟根部门")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最近一次从飞书看到的时间")
    __table_args__ = (Index('idx_department_order', 'parent_id', 'sort_order', 'id'), _table_args("飞书部门目录"))


class Employee(Base):
    __tablename__ = "employee"
    id: Mapped[str] = mapped_column(SOURCE_ID, primary_key=True, comment="内部员工稳定标识")
    feishu_user_id: Mapped[str] = mapped_column(SOURCE_ID, unique=True, comment="飞书用户标识")
    open_id: Mapped[str | None] = mapped_column(SOURCE_ID, unique=True, comment="飞书用户开放标识")
    name: Mapped[str] = mapped_column(String(255), comment="员工姓名")
    employee_no: Mapped[str | None] = mapped_column(String(128), comment="员工工号")
    mobile: Mapped[str | None] = mapped_column(String(128), comment="飞书完整手机号，空值含义由字段可读性说明")
    email: Mapped[str | None] = mapped_column(String(254), comment="飞书人员邮箱，缺省或不可读时为空，可读性记录于 field_readability")
    avatar_url: Mapped[str | None] = mapped_column(String(2048), comment="飞书人员头像 HTTPS 地址，缺省或不可读时为空")
    join_time: Mapped[int | None] = mapped_column(BigInteger, comment="飞书入职时间 Unix 秒时间戳，按北京时间展示日期，未填写或不可读时为空")
    is_frozen: Mapped[bool | None] = mapped_column(Boolean, comment="飞书账号是否暂停，NULL 表示未知")
    is_resigned: Mapped[bool | None] = mapped_column(Boolean, comment="飞书账号是否离职，NULL 表示未知")
    is_activated: Mapped[bool | None] = mapped_column(Boolean, comment="飞书账号是否已激活，NULL 表示未知")
    is_exited: Mapped[bool | None] = mapped_column(Boolean, comment="飞书账号是否主动退出，NULL 表示未知")
    is_unjoin: Mapped[bool | None] = mapped_column(Boolean, comment="飞书账号是否未加入，NULL 表示未知")
    field_readability: Mapped[dict | None] = mapped_column(JSON, comment="手机号和账号标志可读性：readable、not_collected、unreadable")
    employee_type_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment="员工类型枚举选项标识")
    employee_type_name: Mapped[str | None] = mapped_column(String(255), comment="员工类型展示名称")
    job_title: Mapped[str | None] = mapped_column(String(255), comment="员工职务")
    leader_user_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment="直属上级用户标识")
    permission_role_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment="权限角色选项标识")
    permission_role_name: Mapped[str | None] = mapped_column(String(255), comment="权限角色展示名称")
    store_attribute_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment="门店属性选项标识")
    store_attribute_name: Mapped[str | None] = mapped_column(String(255), comment="门店属性展示名称")
    status: Mapped[str] = mapped_column(String(32), default="active", comment="员工状态")
    sync_quality: Mapped[str] = mapped_column(String(32), default="unknown", comment="员工同步质量")
    primary_department_id: Mapped[str | None] = mapped_column(SOURCE_ID, ForeignKey("department.id"), comment="主部门标识")
    primary_store_status: Mapped[str] = mapped_column(String(32), default="unknown", comment="主门店解析状态")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最近一次从飞书看到的时间")
    __table_args__ = _table_args("飞书员工目录")


class EmployeeDepartment(Base):
    __tablename__ = "employee_department"
    employee_id: Mapped[str] = mapped_column(SOURCE_ID, ForeignKey("employee.id"), primary_key=True, comment="员工标识")
    department_id: Mapped[str] = mapped_column(SOURCE_ID, ForeignKey("department.id"), primary_key=True, comment="部门标识")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否为主部门关系")
    active: Mapped[bool] = mapped_column(Boolean, default=True, comment="关系是否有效")
    __table_args__ = _table_args("员工部门关系")


class StoreProfile(Base):
    __tablename__ = "store_profile"
    department_id: Mapped[str] = mapped_column(SOURCE_ID, ForeignKey("department.id"), primary_key=True, comment="门店对应部门标识")
    is_store: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否标记为门店")
    store_code: Mapped[str | None] = mapped_column(String(128), unique=True, comment="门店编码")
    notes: Mapped[str | None] = mapped_column(Text, comment="门店备注")
    __table_args__ = _table_args("门店资料")


class StoreCodeReservation(Base):
    __tablename__ = "store_code_reservation"
    store_code: Mapped[str] = mapped_column(String(128), primary_key=True, comment="预留门店编码")
    department_id: Mapped[str] = mapped_column(SOURCE_ID, ForeignKey("department.id"), comment="占用该编码的部门标识")
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="编码预留时间")
    __table_args__ = _table_args("门店编码预留")


class EmployeeStore(Base):
    __tablename__ = "employee_store"
    employee_id: Mapped[str] = mapped_column(SOURCE_ID, ForeignKey("employee.id"), primary_key=True, comment="员工标识")
    store_id: Mapped[str] = mapped_column(SOURCE_ID, ForeignKey("department.id"), primary_key=True, comment="门店部门标识")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否为主门店关系")
    path: Mapped[list] = mapped_column(JSON, comment="门店路径标识列表")
    __table_args__ = _table_args("员工门店关系")


class FeishuConnection(Base):
    __tablename__ = "feishu_connection"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="飞书连接单例标识")
    tenant_key: Mapped[str | None] = mapped_column(SOURCE_ID, unique=True, comment="飞书租户标识")
    app_id: Mapped[str] = mapped_column(SOURCE_ID, comment="飞书应用标识")
    status: Mapped[str] = mapped_column(String(32), comment="连接状态")
    coverage_status: Mapped[str] = mapped_column(String(32), default="unknown", comment="连接覆盖状态")
    custom_attrs: Mapped[dict] = mapped_column(JSON, default=dict, server_default=sql_text("('{}')"), comment="自定义字段映射与选项定义")
    __table_args__ = _table_args("飞书连接配置")


class AdminAllowlist(Base):
    __tablename__ = "admin_allowlist"
    open_id: Mapped[str] = mapped_column(SOURCE_ID, primary_key=True, comment="管理员飞书开放标识")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="加入白名单时间")
    __table_args__ = _table_args("管理员白名单")


class AdminSession(Base):
    __tablename__ = "admin_session"
    id: Mapped[str] = mapped_column(SOURCE_ID, primary_key=True, comment="管理员会话内部标识")
    token_digest: Mapped[str] = mapped_column(String(64), comment="管理员会话令牌 SHA-256 摘要")
    open_id: Mapped[str] = mapped_column(SOURCE_ID, index=True, comment="管理员飞书开放标识")
    csrf_hash: Mapped[str] = mapped_column(String(64), comment="CSRF 令牌摘要")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="会话过期时间")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="会话撤销时间")
    __table_args__ = (UniqueConstraint("token_digest", name="uq_admin_session_token_digest"), _table_args("管理员登录会话"))


class ApiClient(Base):
    __tablename__ = "api_client"
    id: Mapped[str] = mapped_column(SOURCE_ID, primary_key=True, comment="API 客户端标识")
    name: Mapped[str] = mapped_column(String(255), comment="API 客户端名称")
    secret_hash: Mapped[str] = mapped_column(String(255), comment="客户端密钥摘要")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="创建时间")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="撤销时间")
    __table_args__ = _table_args("只读 API 客户端")


class SyncJob(Base):
    __tablename__ = "sync_job"
    id: Mapped[str] = mapped_column(SOURCE_ID, primary_key=True, comment="同步任务标识")
    type: Mapped[str] = mapped_column(String(32), comment="同步任务类型")
    name: Mapped[str | None] = mapped_column(String(255), comment="同步任务名称")
    trigger_source: Mapped[str | None] = mapped_column(String(32), comment="任务触发来源")
    description: Mapped[str | None] = mapped_column(Text, comment="同步任务说明")
    root_department_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment="子树同步根部门标识")
    requested_by: Mapped[str] = mapped_column(String(255), comment="任务请求方")
    status: Mapped[str] = mapped_column(String(32), index=True, comment="任务状态")
    phase: Mapped[str | None] = mapped_column(String(64), comment="任务阶段")
    attempt: Mapped[int] = mapped_column(Integer, default=1, comment="任务尝试次数")
    execution_count: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"), comment="任务执行次数")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"), comment="任务重试次数")
    total_count: Mapped[int | None] = mapped_column(Integer, comment="任务对象总数")
    success_count: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"), comment="任务成功对象数")
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"), comment="任务失败对象数")
    lease_generation: Mapped[int] = mapped_column(Integer, default=0, comment="任务租约世代号")
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="任务租约过期时间")
    error_code: Mapped[str | None] = mapped_column(String(64), comment="任务错误编码")
    error_detail: Mapped[str | None] = mapped_column(Text, comment="任务错误详情")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="任务创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="任务更新时间")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="任务开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="任务结束时间")
    __table_args__ = (Index("ix_sync_job_scope", "type", "root_department_id", "status"), _table_args("同步任务"))


class SyncJobDetail(Base):
    __tablename__ = "sync_job_detail"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="任务明细自增标识")
    job_id: Mapped[str] = mapped_column(SOURCE_ID, ForeignKey("sync_job.id"), index=True, comment="所属同步任务标识")
    object_type: Mapped[str] = mapped_column(String(32), comment="任务对象类型")
    object_id: Mapped[str] = mapped_column(SOURCE_ID, comment="任务对象标识")
    object_name: Mapped[str | None] = mapped_column(String(255), comment="任务对象名称快照")
    status: Mapped[str] = mapped_column(String(32), comment="对象处理状态")
    error_code: Mapped[str | None] = mapped_column(String(64), comment="对象错误编码")
    error_message: Mapped[str | None] = mapped_column(Text, comment="对象错误摘要")
    attempt: Mapped[int] = mapped_column(Integer, default=1, comment="对象处理尝试次数")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="对象处理开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="对象处理结束时间")
    change_log_id: Mapped[int | None] = mapped_column(BigInteger, comment="关联变更日志标识")
    __table_args__ = (UniqueConstraint("job_id", "object_type", "object_id", name="uq_sync_job_detail_object"), _table_args("同步任务明细"))


class EventInbox(Base):
    __tablename__ = "event_inbox"
    event_id: Mapped[str] = mapped_column(SOURCE_ID, primary_key=True, comment="飞书事件标识")
    event_type: Mapped[str] = mapped_column(String(128), comment="飞书事件类型")
    object_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment="事件对象标识")
    payload: Mapped[dict] = mapped_column(JSON, comment="事件原始载荷")
    status: Mapped[str] = mapped_column(String(32), index=True, comment="事件处理状态")
    attempts: Mapped[int] = mapped_column(Integer, default=0, comment="事件处理尝试次数")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="事件接收时间")
    __table_args__ = _table_args("飞书事件收件箱")


class SyncStaging(Base):
    __tablename__ = "sync_staging"
    job_id: Mapped[str] = mapped_column(SOURCE_ID, ForeignKey("sync_job.id"), primary_key=True, comment="所属同步任务标识")
    object_type: Mapped[str] = mapped_column(String(32), primary_key=True, comment="暂存对象类型")
    source_id: Mapped[str] = mapped_column(SOURCE_ID, primary_key=True, comment="来源对象标识")
    normalized_data: Mapped[dict] = mapped_column(JSON, comment="规范化对象数据")
    __table_args__ = _table_args("同步暂存数据")


class ChangeLog(Base):
    __tablename__ = "change_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="变更日志自增标识")
    object_type: Mapped[str] = mapped_column(String(32), comment="变更对象类型")
    object_id: Mapped[str] = mapped_column(SOURCE_ID, comment="变更对象标识")
    source: Mapped[str] = mapped_column(String(32), comment="变更来源")
    actor: Mapped[str | None] = mapped_column(String(255), comment="操作主体")
    job_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment="关联同步任务标识")
    before_data: Mapped[dict | None] = mapped_column(JSON, comment="变更前数据")
    after_data: Mapped[dict | None] = mapped_column(JSON, comment="变更后数据")
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, comment="变更提交时间")
    __table_args__ = _table_args("数据变更审计日志")


class OperationReceipt(Base):
    """Agent 能力调用的一次操作回执。"""

    __tablename__ = "operation_receipt"
    operation_id: Mapped[str] = mapped_column(
        SOURCE_ID, primary_key=True, comment="Agent 能力调用的一次操作稳定标识"
    )
    idempotency_key: Mapped[str] = mapped_column(
        SOURCE_ID, nullable=False, comment="用于防止重复提交的幂等键"
    )
    capability: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="被调用的能力名称"
    )
    actor_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="调用主体类型，例如人工、Agent 或 CI"
    )
    actor_id: Mapped[str] = mapped_column(
        SOURCE_ID, nullable=False, comment="调用主体的稳定身份标识"
    )
    environment: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="操作运行环境，例如 production 或 test"
    )
    run_id: Mapped[str | None] = mapped_column(
        SOURCE_ID, comment="关联的 Agent 运行标识"
    )
    case_id: Mapped[str | None] = mapped_column(
        SOURCE_ID, comment="关联的 Evaluation 用例标识"
    )
    request_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="规范化请求内容的摘要"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="操作回执状态"
    )
    job_id: Mapped[str | None] = mapped_column(
        SOURCE_ID, comment="关联的同步任务标识"
    )
    before_epoch: Mapped[str] = mapped_column(
        SOURCE_ID, nullable=False, comment="请求开始时的数据集世代标识"
    )
    before_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="请求开始时的数据版本号"
    )
    committed_epoch: Mapped[str | None] = mapped_column(
        SOURCE_ID, comment="业务提交后的数据集世代标识"
    )
    committed_version: Mapped[int | None] = mapped_column(
        BigInteger, comment="业务提交后的数据版本号"
    )
    result_summary: Mapped[dict | None] = mapped_column(
        JSON, comment="脱敏后的结构化结果摘要"
    )
    error_code: Mapped[str | None] = mapped_column(
        String(64), comment="最近一次失败的稳定错误编码"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="操作回执创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="操作回执最近更新时间"
    )
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "environment", "idempotency_key", name="uq_operation_receipt_idempotency"
        ),
        Index("ix_operation_receipt_capability", "capability"),
        Index("ix_operation_receipt_actor_id", "actor_id"),
        Index("ix_operation_receipt_environment", "environment"),
        Index("ix_operation_receipt_run_id", "run_id"),
        Index("ix_operation_receipt_case_id", "case_id"),
        Index("ix_operation_receipt_status", "status"),
        Index("ix_operation_receipt_job_id", "job_id"),
        Index("ix_operation_receipt_error_code", "error_code"),
        Index("ix_operation_receipt_created_at", "created_at"),
        _table_args("Agent 操作回执记录"),
    )


class TencentAccount(Base):
    __tablename__ = 'tencent_account'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment='腾讯云账号内部标识')
    uin: Mapped[str] = mapped_column(SOURCE_ID, nullable=False, comment='不可重新绑定的腾讯云主账号 UIN 字符串')
    alias: Mapped[str] = mapped_column(String(128), nullable=False, comment='管理员维护的中文账号别名')
    credential_ref: Mapped[str] = mapped_column(String(64), nullable=False, comment='后端受控凭据注册表引用，不保存可用密钥')
    revision: Mapped[int] = mapped_column(Integer().with_variant(INTEGER(unsigned=True), 'mysql'), default=1, server_default='1', comment='账号维护并发修订号，每次有效维护递增')
    credential_revision: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment='账号安全修订号，凭据轮换或启停后隔离旧在途结果')
    is_enabled: Mapped[bool] = mapped_column(Boolean().with_variant(TINYINT(unsigned=True), 'mysql'), default=True, server_default='1', comment='账号总开关：1启用，0停用并禁止新结果')
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, comment='归属验证状态，仅 verified 可执行查询')
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment='最近一次实际归属验证成功的 UTC 时间')
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=sql_text('CURRENT_TIMESTAMP'), comment='账号登记 UTC 时间')
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=_UpdateTimestamp('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='账号最后修改 UTC 时间')
    __table_args__ = (UniqueConstraint('uin', name='uk_tencent_account_uin'), _table_args('独立腾讯云账号及受控凭据绑定'))


class TencentApiCall(Base):
    __tablename__ = 'tencent_api_call'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment='每次实际调用的唯一审计事件标识')
    request_id: Mapped[str] = mapped_column(String(36), comment='服务端生成的本次入站请求关联标识')
    direction: Mapped[str] = mapped_column(String(16), comment='调用方向：inbound入站，outbound腾讯云出站')
    action: Mapped[str] = mapped_column(String(64), comment='服务端登记的业务动作，未知为 unknown')
    permission_code: Mapped[str | None] = mapped_column(String(64), comment='本次服务端实际执行的独立权限动作')
    actor_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment='已认证管理员开放标识，匿名拒绝为空')
    target_id: Mapped[str | None] = mapped_column(SOURCE_ID, comment='必要的账号 UIN 或外部操作目标，不保存财务正文')
    method: Mapped[str] = mapped_column(String(16), comment='实际 HTTP 方法或 SDK 调用方式')
    route: Mapped[str] = mapped_column(String(255), comment='规范接口模板或腾讯云官方动作名称')
    status_code: Mapped[int | None] = mapped_column(Integer, comment='已观察到的 HTTP 状态码，未返回时为空')
    outcome: Mapped[str] = mapped_column(String(32), comment='调用结果：running、succeeded、failed、unknown')
    reason_code: Mapped[str | None] = mapped_column(String(64), comment='稳定错误码，不保存外部异常原文')
    upstream_request_id: Mapped[str | None] = mapped_column(String(128), comment='腾讯云返回的请求标识，不保存余额或账单')
    started_at: Mapped[datetime] = mapped_column(DateTime, comment='实际调用开始 UTC 时间')
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, comment='观察到实际响应返回的 UTC 时间，未观测为空')
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, comment='调用结束 UTC 时间，未结束为空')
    duration_ms: Mapped[int | None] = mapped_column(Integer, comment='单调时钟测量的实际耗时毫秒数')
    __table_args__ = (
        Index('idx_tencent_api_call_request_id', 'request_id'),
        Index('idx_tencent_api_call_rate_window', 'direction', 'action', 'target_id', 'started_at'),
        _table_args('腾讯云模块实际请求事实，元信息白名单且不保存财务正文'),
    )


class TencentSyncConfig(Base):
    __tablename__ = 'tencent_sync_config'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment='腾讯云业务配置标识')
    account_id: Mapped[int] = mapped_column(Integer, comment='所属腾讯云账号标识')
    business: Mapped[str] = mapped_column(String(32), default='cost', comment='业务类型，cost表示成本')
    is_enabled: Mapped[bool] = mapped_column(Boolean().with_variant(TINYINT(unsigned=True), 'mysql'), default=False, server_default='0', comment='成本能力开关，默认关闭')
    revision: Mapped[int] = mapped_column(Integer().with_variant(INTEGER(unsigned=True), 'mysql'), default=1, server_default='1', comment='配置并发修订号，普通编辑仅影响新轮次')
    control_revision: Mapped[int] = mapped_column(Integer().with_variant(INTEGER(unsigned=True), 'mysql'), default=1, server_default='1', comment='启停控制修订号，隔离停用前旧任务')
    run_policy: Mapped[dict | None] = mapped_column(JSON, comment='经过校验的重试预算、租约心跳及排队策略')
    frequency: Mapped[str] = mapped_column(String(32), default='manual', comment='执行频率：manual手动、monthly每月三日、daily每日或weekly每周日')
    execution_time: Mapped[str] = mapped_column(String(5), default='13:30', server_default='13:30', comment='自动计划的北京时间时分，默认建议13:30可修改')
    history_progress: Mapped[dict | None] = mapped_column(JSON, comment='经类型校验的历史发现检查点，来源窗口不代表账号历史起点')
    schedule_start_date: Mapped[date | None] = mapped_column(Date, comment='首次日周计划的补漏日期锚点，不代表已核验历史起点')
    schedule_start_month: Mapped[str | None] = mapped_column(String(7), comment='首次启用月模式时的补漏起点，不代表已核验历史起点')
    currency: Mapped[str] = mapped_column(String(3), default='CNY', comment='境内账单声明币种，不由源接口返回')
    owner: Mapped[str | None] = mapped_column(String(36), comment='本配置当前执行者标识')
    generation: Mapped[int] = mapped_column(Integer().with_variant(INTEGER(unsigned=True), 'mysql'), default=0, server_default='0', comment='配置执行资格递增代次')
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, comment='执行资格到期UTC时刻')
    active_job_id: Mapped[int | None] = mapped_column(Integer, comment='本配置正在执行的任务标识')
    last_success_month: Mapped[str | None] = mapped_column(String(7), comment='最近一次完整提交的账月')
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=sql_text('CURRENT_TIMESTAMP'), comment='配置创建UTC时间')
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=_UpdateTimestamp('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='配置更新UTC时间')
    __table_args__ = (UniqueConstraint('account_id', 'business', name='uk_tencent_config_business'), _table_args('腾讯云账号按业务独立配置及执行互斥'))


class TencentSyncJob(Base):
    __tablename__ = 'tencent_sync_job'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment='一次逻辑成本任务标识')
    config_id: Mapped[int] = mapped_column(Integer, comment='所属业务配置标识')
    account_id: Mapped[int] = mapped_column(Integer, comment='所属腾讯云账号标识')
    dataset_epoch: Mapped[str] = mapped_column(SOURCE_ID, comment='受理时冻结的初始化世代，用于隔离幂等键')
    idempotency_key: Mapped[str] = mapped_column(String(128), comment='配置内可靠请求幂等键')
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment='实际领取优先级：0近期或人工，20历史发现；活动重试保持资格')
    kind: Mapped[str] = mapped_column(String(16), default='period', server_default='period', comment='任务种类：batch纯汇总父批次或period实际期间')
    parent_job_id: Mapped[int | None] = mapped_column(Integer, comment='期间所属父批次标识，独立手动期间为空')
    month: Mapped[str | None] = mapped_column(String(7), comment='实际日月期间所属自然月YYYY-MM，纯汇总父批次为空')
    status: Mapped[str] = mapped_column(String(32), comment='任务状态pending、running、retry_wait、succeeded或failed')
    snapshot: Mapped[dict] = mapped_column(JSON, comment='冻结配置、口径、范围、可信发起身份及初始化世代，不含秘密')
    request_id: Mapped[str] = mapped_column(String(36), comment='受理请求的服务端关联标识')
    error_code: Mapped[str | None] = mapped_column(String(64), comment='最终稳定失败编码')
    source_job_id: Mapped[int | None] = mapped_column(Integer, comment='人工重跑关联的原逻辑任务，首次采集为空')
    commit_receipt: Mapped[dict | None] = mapped_column(JSON, comment='与费用同事务保存的原始提交回执，用于归档恢复')
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, comment='等待重试最早可领取UTC时刻')
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, comment='首次领取后执行与重试共同截止UTC时刻')
    queue_deadline_at: Mapped[datetime | None] = mapped_column(DateTime, comment='受理后首次领取排队截止UTC时刻')
    started_at: Mapped[datetime | None] = mapped_column(DateTime, comment='首次实际执行UTC时刻')
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, comment='任务终结UTC时刻')
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=sql_text('CURRENT_TIMESTAMP'), comment='任务可靠受理UTC时间')
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=_UpdateTimestamp('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='任务状态更新UTC时间')
    __table_args__ = (
        UniqueConstraint('config_id','dataset_epoch','kind','idempotency_key',name='uk_tencent_job_request'),
        Index('idx_tencent_job_claim','status','config_id','id'),
        Index('idx_tencent_job_priority','config_id','status','priority','id'),
        Index('idx_tencent_sync_job_parent_job_id','parent_job_id'),
        _table_args('腾讯云单月逻辑执行任务，不依赖浏览器会话存活'),
    )


class TencentSyncAttempt(Base):
    __tablename__ = 'tencent_sync_attempt'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment='一次真实执行尝试标识')
    job_id: Mapped[int] = mapped_column(Integer, comment='所属逻辑任务标识')
    attempt_no: Mapped[int] = mapped_column(Integer().with_variant(INTEGER(unsigned=True), 'mysql'), comment='任务内实际尝试序号，从1开始')
    generation: Mapped[int] = mapped_column(Integer().with_variant(INTEGER(unsigned=True), 'mysql'), comment='领取时的配置执行资格代次')
    owner: Mapped[str] = mapped_column(String(36), comment='本次执行者标识')
    status: Mapped[str] = mapped_column(String(32), comment='尝试状态running、succeeded、failed或unknown')
    execution_input: Mapped[dict] = mapped_column(JSON, comment='执行前可靠保存的完整脱敏实际入参')
    execution_output: Mapped[dict | None] = mapped_column(JSON, comment='处理器实际返回的原子提交回执，不保存账单原文')
    return_state: Mapped[str] = mapped_column(String(32), default='UNKNOWN', server_default='UNKNOWN', comment='实际返回形态VALUE、NOT_RETURNED或UNKNOWN')
    request_id: Mapped[str | None] = mapped_column(String(36), comment='本尝试独立请求关联标识，历史未采集时为空')
    failure_evidence: Mapped[dict | None] = mapped_column(JSON, comment='稳定失败分类与已核实上游请求标识，不保存报文')
    error_code: Mapped[str | None] = mapped_column(String(64), comment='明确失败或未知的稳定原因编码')
    started_at: Mapped[datetime] = mapped_column(DateTime, comment='尝试开始UTC时刻')
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, comment='尝试终结UTC时刻')
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=sql_text('CURRENT_TIMESTAMP'), comment='尝试事实创建UTC时间')
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=_UpdateTimestamp('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='尝试事实更新UTC时间')
    __table_args__ = (UniqueConstraint('job_id','attempt_no',name='uk_tencent_attempt_number'), _table_args('腾讯云真实尝试事实，失败记录独立于费用回滚'))


class TencentCostPeriod(Base):
    __tablename__ = 'tencent_cost_period'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment='当前完整费用期间标识')
    account_id: Mapped[int] = mapped_column(Integer, comment='所属腾讯云账号标识')
    month: Mapped[str] = mapped_column(String(7), comment='Asia/Shanghai费用所属自然月YYYY-MM')
    granularity: Mapped[str] = mapped_column(String(8), default='month', server_default='month', comment='来源真实粒度day单日或month完整月')
    period_key: Mapped[str] = mapped_column(String(10), default=lambda context: context.get_current_parameters()['month'], comment='原始期间身份：月YYYY-MM或日YYYY-MM-DD')
    currency: Mapped[str] = mapped_column(String(3), comment='独立金额维度的账单声明币种')
    total: Mapped[object] = mapped_column(Numeric(24,8), comment='费用账单总费用，保留8位小数及负退款')
    coverage: Mapped[dict] = mapped_column(JSON, comment='完整边界、费用口径及零值和完整性证明摘要')
    latest_job_id: Mapped[int] = mapped_column(Integer, comment='最近成功提交本期间的任务标识')
    latest_attempt_id: Mapped[int] = mapped_column(Integer, comment='最近成功提交本期间的尝试标识')
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=sql_text('CURRENT_TIMESTAMP'), comment='期间首次创建UTC时间')
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=_UpdateTimestamp('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='完整期间最后替换UTC时间')
    __table_args__ = (UniqueConstraint('account_id','period_key','currency',name='uk_tencent_period_scope'), Index('idx_tencent_period_month','account_id','currency','month'), _table_args('腾讯云原始日月费用及一致覆盖回执'))


class TencentCostItem(Base):
    __tablename__ = 'tencent_cost_item'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment='期间内费用产品行标识，不假设跨期稳定')
    period_id: Mapped[int] = mapped_column(Integer, comment='所属完整费用期间标识')
    row_no: Mapped[int] = mapped_column(Integer().with_variant(INTEGER(unsigned=True), 'mysql'), comment='本次全量结果内产品行序号')
    business_code: Mapped[str | None] = mapped_column(String(191), comment='可靠映射的产品BusinessCode，不是子产品ProductCode')
    source_name: Mapped[str] = mapped_column(String(255), comment='源接口原始产品显示名称')
    mapping_status: Mapped[str] = mapped_column(String(32), comment='产品映射状态mapped、ambiguous或unmapped')
    amount: Mapped[object] = mapped_column(Numeric(24,8), comment='该原始日月期间的产品总费用，保留负退款')
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=sql_text('CURRENT_TIMESTAMP'), comment='当前产品行创建UTC时间')
    update_time: Mapped[datetime] = mapped_column(DateTime, server_default=_UpdateTimestamp('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='当前产品行最后更新UTC时间')
    __table_args__ = (UniqueConstraint('period_id','row_no',name='uk_tencent_item_row'), _table_args('原始期间全量产品行，未映射和同名行保持独立'))
