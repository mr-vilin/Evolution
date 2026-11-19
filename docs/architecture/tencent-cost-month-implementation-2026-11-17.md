# 腾讯云单个完整账月实现与迁移验收（T03）

2026-11-17。对应 [#18](https://github.com/mr-vilin/Evolution/issues/18)，依据父规格、初始化重试边界 ADR 0004 和财务保留边界 ADR 0006。本票仅手动一个已到同步日的完整账月、有界首次尝试。自动调度、父批次、日周切换、历史回溯及租约恢复由后续工单扩展。

## 当前闭环与接口

管理端 `/tencent/costs` 选择账号、保存成本开关、选择完整账月并提交；中文结构化表单不开放密钥、JSON或自动调度模式。默认关闭，固定 manual、CNY、费用账单/总费用/产品维度。服务器核对已验证启用账号、受控凭据引用与处理器能力；每月北京时间1–2日最多受理上上月，3日起可受理上月。

| 接口 | 动作 | 语义 |
| --- | --- | --- |
| GET accounts/{id}/cost-config | tencent.cost.read | 不落库的默认关闭配置及最新可选账月 |
| PUT accounts/{id}/cost-config | tencent.config.update | CSRF、真实管理员会话、乐观修订；相同值保存不推进修订 |
| POST accounts/{id}/cost-jobs | tencent.cost.rerun | 可靠保存固定范围后返回202、任务编号和Location；配置内幂等键同月返回原任务，换月409 |
| GET accounts/{id}/cost-jobs | tencent.job.read | 最近100条任务元信息，后续查询票扩展分页 |
| GET cost-jobs/{id} | tencent.job.read | 状态及真实尝试完整脱敏输入、实际提交回执/稳定失败码 |
| GET accounts/{id}/cost-periods/{month} | tencent.cost.read | 同一REPEATABLE READ事务读取当前完整月的总计、全部产品和覆盖 |

所有路径前缀 `/admin/api/tencent`，沿用项目 data/meta 与稳定 error 外壳；返回金额是元单位八位十进制字符串，资源ID为字符串。接口均经初始化与管理员准入，写接口检查CSRF；读取可查已停用账号的历史完整结果，执行必须当前账号及成本配置启用。复用本模块入站/出站元信息审计，响应 no-store。普通日志不保存财务正文、凭据、会话或上游异常原文。

## 身份、任务与worker

HTTP受理冻结处理器 `tencent-cost-month-v1`、账号绑定修订、配置、Asia/Shanghai半开期间、官方请求口径、策略及 dataset_epoch。发起 open_id 来自服务器真实管理员身份，不接受客户端 actor 字段。不持久化浏览器令牌、token_digest、CSRF或可用云密钥。

异步手动任务的执行身份是“原服务器确认的发起管理员＋当前管理员白名单资格”；浏览器自然过期不取消已可靠受理任务，当前撤权会阻止领取/发布。未来系统调度需登记可信系统执行身份，不能冒充某个人或继续使用此手动白名单分支。

`TencentCostWorker.claim(now=None)` 原子领取并先提交完整脱敏实际输入；`execute(CostClaim)` 执行并返回真实原子提交回执或None；`run_once(now=None)` 提供一次生产工作循环入口。`CostClaim` 固定 job/config/attempt/owner/generation/snapshot/request_id。生产通过现有 `deploy/supervise.py` 额外监督 `python -m app.tencent.cost_worker`，仍为原应用容器，不使用组织同步单例租约。

配置独立 owner/generation/lease_expires_at/active_job_id 保证同配置串行，多worker可处理不同配置。锁序 DatasetState共享锁→账号共享锁→当前发起管理员资格→配置独占锁→job/attempt；出站期间不持锁。提交重新检查初始化、固定epoch、当前账号开关/凭据修订、当前成本启用、执行能力与owner/generation/期限。普通组织data_version递增不阻止同epoch费用发布。

T03的唯一可变配置是开关，revision在本阶段同时充当启停栅栏，停用再启用也不能让旧轮次发布。完全相同PUT不推进revision。**T04/T06开放频率、策略或参数编辑时必须拆分普通配置修订与启停控制修订**：普通编辑只影响新轮次，旧轮次继续按snapshot；不能沿用“当前普通revision必须等于冻结revision”取消旧任务。当前开关、安全绑定、能力版本和执行资格仍须复核。

有界策略：最多10000条产品，官方PageSize100，90秒采集预算，每次官方SDK调用10秒且NoopRetryer，120秒提交资格。预算超限、异常或资格变化均失败且保留旧结果。本票不自动回收进程崩溃遗留owner，也不重试；T04扩展同一配置的续租、恢复、失效执行者栅栏及attempt序号，不能重放已确认提交的业务以补历史。失败历史独立事务保存；成功回执与费用、任务、覆盖、配置进度在同一事务保存。

## 官方费用协议与金额

主接口 DescribeCostExplorerSummary 固定 BillType=1、FeeType=cost、Dimensions=business、PeriodType=month、NeedConditionValue=1；BeginTime/EndTime为北京时间月首至月末最后一秒。主响应不含UIN、币种、Ready或快照token，因此一次尝试先解析一次不可变受控凭据，用同一凭据 DescribeAccountBalance 核验实际UIN后再请求全部费用分页，不创建余额历史。

校验总条数、每页应有行数、重复页指纹（不含RequestId）、提前空/null页、声明总行数之后仍有产品、页间总条数/表头/总计变化，以及每行时间金额、所有产品和总计一致。最后重读首页，比较总条数、表头、总计及全部首页明细；筛选选项`ConditionValue`不参与一致性校验。**不宣称腾讯云提供事务快照**。当前明确支持单一月时间列的YYYY-MM、YYYY-MM-01、YYYY-MM-01 00:00:00三种标签，其他形态拒绝发布，待真实账号核验后再扩展。

金额从源十进制字符串直接Decimal处理，64位上下文求和，DECIMAL(24,8)无损落库。负数退款保持原值，超范围、非有限或超过八位有效小数拒绝，不舍入配平。CNY是境内账号配置声明，不冒充上游响应币种，不跨币种合计。

Total=0/空Detail本身不能清空旧费用。只有辅助 DescribeBillSummaryByProduct（BeginTime/EndTime均同一YYYY-MM、无PayerUin/PayType限制）Ready=1、折后总费用RealTotalCost=0、全产品零且BillMonth匹配，才形成同月就绪零证据。需额外只读CAM动作 `finance:DescribeBillSummaryByProduct`；无权限、未就绪、空/缺失正文或非零差异均保留旧值。非空正负相抵的零净额仍保留全部产品。

产品只用首次首页的`ConditionValue.Business`精确双向唯一字典映射BusinessCode，后续页及重读首页的筛选选项不会覆盖首次映射；不把子产品ProductCode混作BusinessCode，不按名字推码或合并。没有可靠映射、重复同名或双向歧义时，保留原始产品名、独立期间内行标识及unmapped/ambiguous。重新采集整月原子删除旧产品并插入完整新集合，消失产品自然移除，其他月份不受影响。T05应从期间覆盖计算范围，不将last_success_month（最近成功执行的月）误作连续历史高水位。

## 数据库迁移与回退

0015_tencent_cost 从0014新增 tencent_sync_config、tencent_sync_job、tencent_sync_attempt、tencent_cost_period、tencent_cost_item 五表，不修改组织表/初始化清理清单。InnoDB、utf8mb4/utf8mb4_general_ci显式指定；稳定标识utf8mb4_bin；每列中文COMMENT；主键/关联ID有符号INT、非负计数unsigned、金额DECIMAL(24,8)、无新增物理外键。迁移冻结显式DDL，不在执行时导入未来ORM。CURRENT_SCHEMA_HEAD同步0015。

执行前：分别核对目标环境、实际8.4版本、0014基线、五表不存在、引擎及会话字符集/排序规则/UTC/REPEATABLE READ，确认没有组织/云执行者或活动任务，备份并保存结构快照。0014新增未发布的审计限流索引也须存在；已在旧稿上升级的环境须核对实际索引，不以版本号代替结构证据。真实业务环境迁移仍需单独授权。

执行后：核对版本0015、五表完整结构/中文注释/唯一键/索引、金额精度、服务端create_time/update_time及ON UPDATE语义、readiness与只读schema_check；在隔离库验证幂等、原子覆盖及失败保留。本次修正结构检查器，按实际方言编译默认值并区分MySQL默认值和ON UPDATE额外语义，不能将MySQL语句误套到SQLite测试，也不能忽略真实MySQL自动更新时间差异。

运行回退优先回退应用并保留新增表与费用/尝试证据，不自动downgrade或删表。只有获得迁移回退授权、备份可恢复、无新增财务数据或已单独恢复的情况下才执行downgrade。MySQL DDL非整体事务，若中途失败须对照快照逐表确认、恢复备份或审查后补全，不能盲重放/自动drop；有业务记录时禁止用删除新表代替恢复。

## 验证与尚待真实联调

隔离目标仅本机13306、MySQL8.4.11专用 `tencent_t03_*_test` 库。夹具自身在任何写入前核验目标、版本、会话、无组织owner/活动任务和无云owner/活动任务；结束前拒绝仍持云owner的清理，测试必须先终结/加入全部worker。公共evaluation reset/seed同样拒绝云owner、active_job_id或running任务，过期owner也不例外；真实MySQL测试覆盖仅owner、过期owner、仅active_job_id及仅running任务的两个公开入口，确认拒绝后账号和任务仍可查。未触及本机业务MySQL实例，未迁移开发/测试/生产业务库，未部署Docker。

真实管理HTTP→实际独立worker→真实MySQL，只模拟腾讯云原始出站传输。已验证完整月受理/发布、消失产品/其他月保留/历史提交回执、可靠幂等、分页超过一页、重复/早空/变计数/尾页多余、负数退款/金额溢出/总计不符、空零未就绪/已确认零、归属错配、在途撤权/停用/改凭据/epoch/初始化、普通data_version不干扰、同配置互斥/到期拒绝、不同配置独立执行及数据库故障回滚。实际结构核验中文注释、引擎/排序、无外键及金额精度。

合入T01/T02后的最终新库 `tencent_t03_final_test` 回归：账号、余额及成本三个真实MySQL集成测试文件共81项通过；后端离线回归1400项通过、16项跳过。前端账号/余额/成本页面及HTTP/useResource五文件17项通过，覆盖中文开启配置→202等待执行→刷新成功状态与精确负退款。复杂表单保存按真实完成状态等待，预算5秒，避免并行回归中默认1秒等待导致假阴性；未模拟业务模块或跳过断言。合并后TypeScript通过；antd6.6.4离线元数据/lint及生产构建在本票核心实现上通过（111个构建资源）。jsdom的CSS解析和伪元素getComputedStyle提示是测试环境能力限制，不代表真实浏览器视觉验收。Windows依赖由集成分支固定 [tzdata2026.6](https://pypi.org/project/tzdata/2026.6/)，共享Python已验证Asia/Shanghai可用。

合成wire fixture只证明官方协议形态与故障处理，不证明真实账号CAM、历史可查范围、费用口径和月时间列格式。真实腾讯云费用查询、真实企业登录、容器运行及业务环境验收仍未执行。
