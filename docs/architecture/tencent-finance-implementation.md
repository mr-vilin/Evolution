# 腾讯云财务实现与验证

## T01：账号首次接入（Issue #16）

本次实现沿用父规格 #15 与 ADR 0004/0006。管理员白名单及真实会话为唯一准入来源，整个模块要求 DatasetState.initialization_status=complete；机器只读凭据及 sidecar 身份不获财务权限。账号注册前实际查询 DescribeAccountBalance 并严格核对 Uin；不保存其余额正文。注册外部校验结束后，在短事务中重新锁读世代及当前管理员资格，防止初始化重来、撤权或会话失效后登记。

动作目录集中于 `backend/app/tencent/access.py`；接口通过明确动作接入，不使用历史通配符。账号 UIN 是唯一且不可重新绑定的身份字符串；首次接入默认启用且 verified，轮换和启停留给 T09。后续余额/成本通过 `require_account` 统一检查初始化、账号开关、归属状态及凭据修订。服务端锁顺序为 DatasetState → 账号 → 配置 → 任务；本票注册仅锁 DatasetState 和当前管理员授权。

| 入口 | 动作 | 成功行为 |
| --- | --- | --- |
| GET /admin/api/tencent/credential-options | tencent.account.read | 返回受控引用与中文标签，永不返回密钥 |
| GET /admin/api/tencent/accounts | tencent.account.read | 返回账号身份、别名、验证状态及时间 |
| POST /admin/api/tencent/accounts/validate | tencent.account.validate | CSRF 校验后验证归属；不登记账号或余额历史 |
| POST /admin/api/tencent/accounts | tencent.account.create | CSRF 校验、归属验证和唯一性检查后登记；201 |

沿用项目 `data/meta`、`error.code/message` 外壳。UIN 只接受无前导零的数字字符串，最大32位；alias 去除两侧空白，最大128字且不得空白；credential_ref 只能是固定注册表的引用。额外字段拒绝，不提供修改 UIN 的接口。财务路由（含失败）统一 no-store，并返回服务端生成的 X-Request-ID。INITIALIZATION_INCOMPLETE 会通知前端 AuthGate 重新获取会话并清除业务内容。

## 凭据部署配置

部署维护人员通过现有服务环境中的 `TENCENT_CREDENTIALS` 设置受控注册表；这是后端 SecretStr 配置，不是页面配置入口。注册表键为小写字母开头的字母、数字、连字符引用（最多64字符），每项使用 label、secret_id、secret_key 及可选 token。label 为页面中文名称，其余值是秘密；部署者通过既有秘密注入方式设置，不将实际值提交到仓库、文档、日志或命令输出。前端只选择 label 对应的受控引用，不能提交文件路径、环境变量名或自定义 SecretId/SecretKey。

每个独立主账号使用其自身只读子用户/角色身份。T01 需要 finance:DescribeAccountBalance，Resource 按官方动作定义为 *；实际 CAM 只读限制及账号身份需真实环境另行核实，完成一次归属验证不等于证明成本权限齐全。凭据注册表为空时页面显示联系部署维护人员的操作指引；配置损坏时返回稳定错误，不能静默放行。

官方 SDK 分包 billing/common 固定3.1.177，Python3.13 实际导入、签名构造及模拟 HTTP 出站通过。使用官方 BillingClient.call 原始 bytes，再 json.loads(parse_float=Decimal)，避免 generated 方法先转二进制 float。传输超时10秒，显式 NoopRetryer，单次适配调用只发一次实际请求；上层重试由后续任务治理处理。SDK 正文 logger 禁用，异常只映射稳定错误码，不输出外部错误原文。

## 调用事实与业务审计

`tencent_api_call` 只覆盖腾讯云模块入站和 SDK 出站元信息：每个实际请求一个 UUID 事件，direction 分开计数，出站通过 request_id 关联入站。不保存请求体、响应财务正文、Cookie、CSRF、密钥或密钥摘要。账号创建的 ChangeLog 与账号同事务保存；请求开始事实在独立事务中可靠保存，认证拒绝和业务回滚不会抹去它。

入站开始记录失败时尚未启动业务。返回前记录应用 HTTP 状态并标记结果待核实；实际发送完成后更新完成事实。若发送后的审计收尾写入失败，保留已持久化的 unknown/未结束记录并输出仅带 request_id 的安全故障事件，不能把已发送业务成功改写成业务失败，也不声称该条审计已完整。可据已有账号事实、请求事件和维护日志核实；不自动重放账号注册。审计辅助表使用 UUID 主键与调用时间字段，作为业务表默认 INT/create_time/update_time 之外的明确例外。

## 迁移预检、执行与恢复

迁移为0014_tencent_accounts，从0013_employee_profile增加 tencent_account 和 tencent_api_call 两表，不改组织字段、表或初始化删除清单。表明确 InnoDB/utf8mb4/utf8mb4_general_ci；稳定标识使用 utf8mb4_bin；每列有中文 COMMENT。ORM 和迁移一致，CURRENT_SCHEMA_HEAD 同步。

真实环境执行仍需指定环境及迁移授权。执行前只读核对目标 DATABASE()/VERSION()、会话字符集/排序规则/时区/隔离级别、alembic_version=0013_employee_profile、两新表不存在，保留结构快照与一致备份，并核对账号注册表只读权限。新表为空，因此没有既有字符串转换或外键兼容变化；UIN 唯一键从首次注册生效。

获得相应授权后才用项目发布/迁移入口升级；本票没有对现有业务库执行迁移。执行后检查 alembic_version=0014_tencent_accounts、两表实际引擎/排序规则、每列 COMMENT、UIN 唯一索引和 utf8mb4_bin，以及 readiness。可在隔离库演练重复UIN被拒绝、事务失败不残留账号、失败重来不删除腾讯云表。

失败恢复先核对 MySQL DDL 已提交事实及 alembic_version，保留新增记录和调用审计；不要把删除新表当作常规回滚。仅在确认两表没有业务记录或完成一致备份、并获明确授权时才允许 downgrade。若已有账号/审计，优先停止新能力、保留两表，恢复兼容应用或按备份演练恢复；不得自动清空数据。应用旧构建与新 schema head 不兼容时 readiness 会阻止误运行，须由环境负责人选择已验证恢复制品。

## 本票验证记录

2026-11-17，仅本任务隔离 MySQL8.4.11（本机13306，tencent_t01_test）执行迁移与合成数据测试，未触及 evolution-mysql-1 业务实例。测试夹具自身先校验本机端口、tencent_*_test 库名、实际数据库版本/会话及无活动 worker/任务，再允许写入；不能只依赖外部 runner 的保护。测试使用独立连接验证真实提交及竞态。

已验证：匿名/普通非白名单/机器身份拒绝、CSRF、初始化门槛、注册与列表、受控引用、错配UIN、重复与并发登记、外部校验期间世代改变/管理员撤权、验证不登记、实际入站/出站分离计数、审计收尾故障不改写已发送结果，以及真实MySQL中文注释/字符集/排序规则。官方SDK通过模拟 requests.Session.request 路径核对实际一次出站；中文页面通过登记表单交互、类型检查和 antd lint。

真实腾讯云凭据及 CAM 未提供/未调用，因此真实账号归属、权限、网络和财务来源联调未验收。没有部署。依赖使用既有锁定环境加 SDK 隔离包完成本地验证，全锁文件全新安装由集成阶段另核实。

官方依据：[余额接口](https://cloud.tencent.com/document/api/555/20253)、[费用中心CAM](https://cloud.tencent.com/document/product/598/92835)、[SDK源码](https://github.com/TencentCloud/tencentcloud-sdk-python)。

## T02：实时余额（Issue #17）

余额入口位于已登记账号的行操作，详情地址 `/tencent/accounts/:id/balance`。进入及手动刷新均调用 `GET /admin/api/tencent/accounts/{account_id}/balance`，动作固定为 `tencent.balance.query`；无需成本配置，不创建余额任务、配置、尝试或历史结果。页面不自动轮询，刷新开始即清除上一结果，错误不显示旧金额；切换账号或离开时取消请求，并丢弃迟到响应。初始化失效沿用 AuthGate 返回初始化向导。

后端读取当前已验证且启用的账号，使用其受控凭据调用自身 DescribeAccountBalance（无其他账号目标参数），每次核对返回 Uin。在返回前按 DatasetState → 账号 → 管理员资格顺序短事务锁读，重新验证 dataset_epoch、凭据修订、启用/验证状态、当前会话及白名单资格。并不在网络调用期间持有业务行锁。

原始 JSON 经 Decimal 解析，九项核心金额均要求原生数值、有限且满足64位有效数字及指数边界，再精确从分换算成元字符串。至少两位小数，保留更细精度，零统一 `0.00`；缺失、字符串、布尔或非有限金额拒绝。RealBalance 是主卡；弃用 Balance 不作为回退。现金、收益转入、赠送、冻结、欠费、信用额度、信用可用与真实可用各自展示；可选 TempCredit 返回时单独展示。币种明确为国内站财务账本配置的人民币 CNY，不声称来源响应含币种。查询时间由服务端返回 UTC，页面按北京时间展示到秒。

单次 SDK 原始出站沿用10秒超时、无自动重试；页面15秒取消。MySQL连接级 GET_LOCK 按库名+UIN哈希隔离，同一账号仅允许一个余额出站进行中，不等待锁，竞争返回429/TENCENT_BALANCE_BUSY。持锁后检查同账号最近一秒实际 DescribeAccountBalance 出站事实（含账号验证）；达到5次时返回429/TENCENT_BALANCE_RATE_LIMITED。此限制覆盖共享数据库的应用进程；账号首次接入等其他动作本身的频率治理不属于此接口。锁始终在原连接释放，释放故障时废弃连接，避免带锁连接回池。

响应为 `data/meta`，data包含账号ID/UIN/别名、currency/unit/currency_source、amounts十进制字符串及queried_at。失败使用既有错误外壳；超时504、上游权限或解析失败502、UIN不符422、资格/世代改变409或401。所有响应no-store及X-Request-ID；入站、真实出站分别记录元信息，始终不存余额正文。成功余额查询的全部非调用审计表行数保持不变。

2026-11-17 验证：独立 `tencent_t02_test` / 本机13306 / MySQL8.4.11，在夹具自身目标、版本、会话和静默检查后执行。27个HTTP→真实MySQL行为覆盖高精度、负数、零、无效金额、并发429、频率、资格五类竞态、UIN错配、超时、权限与无业务记录写入；仅模拟腾讯原始出站。前端6个交互覆盖登记/入口、进入查询、刷新错误清空、切换丢弃迟到结果及初始化初始/失效门禁；类型检查、生产构建及两页antd lint通过，账号与余额合计43项MySQL回归通过。没有调用真实腾讯云、迁移业务数据库或部署。真实账号权限及网络仍待环境联调。

T02在未部署的0014与ORM同步补充 "ix_tencent_api_call_rate_window"（direction、action、target_id、started_at），使账号限流使用调用时间范围索引。仅在自有隔离库经实际目标/会话及静默校验、确认两腾讯表完全为空后重演0014，并验证真实索引列序与ORM声明一致；没有为已有业务数据库执行降级、重建或索引写入。已有0014预览测试库需要在相同条件下重演；任何含记录的业务库不得直接套用这一测试步骤。
