# 腾讯云月度调度与批次实施（T06 / #21）

本页记录代码、隔离验收与运行边界，不代表已部署、已迁移业务库或已取得真实腾讯云权限。

## 月计划和受理边界

账号＋cost 只有一份配置。`frequency=monthly` 在 Asia/Shanghai 每月 3 日按保存的 `execution_time` 执行；13:30 只是可修改的默认建议。manual 保留独立完整月采集。所有配置编辑核对 revision；普通编辑只影响新轮次，启停递增 control_revision，旧任务不会因重新启用复活。成本开关不影响实时余额。

生产 `TencentCostWorker.run` 每轮先调用 `TencentCostScheduler.tick`，无需新增进程或基础设施。tick 在初始化完成、账号启用/已验证、凭据可解析且成本月配置启用时受理。系统执行身份为固定 `system:tencent-monthly` / `system-monthly`，不伪造管理员会话、白名单身份或浏览器令牌；人工入口仍检查当前管理员、会话和 CSRF。系统任务在领取、心跳和提交时继续核对冻结 epoch、当前账号/凭据修订、成本开关和 control_revision。

每个计划月以 config＋固定 epoch＋`schedule:monthly:YYYY-MM` 唯一定位事件，原始 UTC 计划点保存在 snapshot。执行时刻修改后，同一日历月已经受理的事件仍指向原批次。配置锁内以 locking current read 查原事件，避免 REPEATABLE READ 的旧快照在双调度器竞争时漏读。先查事件再算范围。人工批次使用 `manual-batch:` 命名空间；独立人工期间采用稳定请求摘要命名空间，兼容旧版未命名空间的请求；批次、期间在唯一键中区分 kind，期间子任务另有 `child:{parent}:month:{month}` 身份。

自动事件只合并最近的已到计划点，不逐个重放所有漏掉的旧计划点。到期边界按北京时间每月 3 日：12 月 3 日处理 11、10 月；1 月 1–2 日手动立即执行最多到 11 月，1 月 3 日才包括 12 月。提前到达保存执行时刻之前，不生成当月自动事件。

## 范围、缺口与预算

每批近期两月去重且优先入队，再追加到期缺口。`schedule_start_month` 是首次启用月模式时固定的补漏锚点（当时最近两月的起点），不是“已核验历史起点”，也不宣称全历史完成。初次全部历史探测及覆盖治理由 T08 衔接。锚点以后的漏月和已知更早失败月合并；成功财务期间跨组织 epoch 保留有效，不因组织重置把全部历史重采。

每批最多增加 12 个旧缺口，且不能超过冻结 queue_limit；至少能容纳近期两月才整体受理，不发布半个父批次。未入队月份保留在 deferred_months。旧缺口在同一 epoch 和凭据修订下累计 3 个失败自动批次后，加入 blocked_months，原因 `TENCENT_MONTH_AUTO_BUDGET_EXHAUSTED`，后续自动事件不继续盲试；可核查权限/可查历史后使用明确的人工单月重跑。新凭据或新 epoch 使用新的当前资格；旧任务不改绑。每个真实期间仍遵循冻结的单次预算、总尝试次数、重试退避、首次等待和轮次截止。

Ready=0 不清零旧值；当前冻结策略有限重试，不将官方约 10 分钟后的重新查询建议冒充已等待完成。若本轮预算内未就绪，保留失败和缺口，后续日历事件或明确人工重采再核实；同一 tick 不能无限创建新轮次绕过预算。

## 父批次与执行事实

同一 TencentSyncJob 区分 `kind=batch` 与 `kind=period`。父批次 month 为空；实际月子任务通过 parent_job_id 关联，冻结独立期间、运行策略、请求关联和身份。worker 候选仅选择 period。父批次不领取 owner/lease，不生成 TencentSyncAttempt，也不假装调用了处理器。

每个月沿既有完整分页、归属/金额核验和原子替换事务执行，成功/失败/恢复后同事务刷新父状态。全部子任务成功才为 succeeded；混合失败或失败且仍待执行为 partial_failed，全部终结失败为 failed。无子任务时可表达 no_work，绝不伪造费用。成功批次只表示已选择的子任务全部成功；deferred/blocked 仍单独显示缺口，不能据父成功声称全部历史覆盖。

GET job 返回真实 children、attempts、计划点及 deferred/blocked；GET config 显示下次计划、截止账月、最近成功月与最近实际成功时间。中文配置表单使用方式选择、北京时间输入和现有数值策略字段。批次详情可进入各月任务并使用已有人工重跑入口，没有 JSON 编辑框。

## 出站限频与日志

CostExplorer、ProductSummary、AccountBalance 默认上限为 20 次/秒（腾讯云官方接口说明：[成本分析](https://cloud.tencent.com/document/api/555/103991)、[产品汇总](https://cloud.tencent.com/document/api/555/35761)、[余额](https://cloud.tencent.com/document/api/555/20253)）。现实现以账号 UIN＋动作的 MySQL GET_LOCK 和已提交 TencentApiCall 开始事实作跨进程许可；开始事实在短临界区内可靠提交后释放许可锁，再进入真实传输。等待者每 50ms 在无业务行锁、无事务的状态等待，最长 10 秒，且持续通过 worker check 核对当前资格、心跳和冻结执行预算。等待没有出站事实；许可前失败没有虚构请求。

实际 started_at 为 DATETIME(0)，窗口保守外扩到 `floor(now)-1秒`，可比严格 1 秒窗口更慢，避免微秒 cutoff 早排同秒事实。余额原有单账号并发及 5/s 门槛沿用同一 cutoff。实际请求耗时从获得许可后计算，等待不伪装成网络耗时。许可锁释放失败时使连接失效，防止带锁连接返回池。

可靠日志复用同事务 ChangeLog：tencent_batch 受理与状态变化、逐月任务/费用提交；诊断复用 `tencent.monthly_deferred`、`tencent.monthly_schedule_unavailable` 和既有 worker 事件，只记录安全标识和稳定原因。审计仍每次真实入站/出站一条事实，不复制账单正文、秘密或浏览器身份。

## 数据库迁移与恢复

目标是项目既有 MySQL 8.4 / InnoDB / utf8mb4_general_ci；稳定标识继续 utf8mb4_bin，不新增物理外键。月迁移增加配置执行时刻/补漏锚点、任务 kind/parent_job_id，将父月字段允许空，扩展配置/epoch/kind/请求唯一键及父查找索引；旧工单默认 period，历史 id、月、输入与金额均保留。新增列及修改列均有非空中文 COMMENT，ORM 与迁移保持一致。

业务环境执行前需另行获得授权：核验实际目标/版本/会话、当前 Alembic head、表列和注释、账号/配置唯一性、任务幂等重复、parent 孤儿、批次 month 为空约束；检查 owner（即使过期）、active_job_id、running/retry_wait 等活动任务，停止并静默执行器，备份数据库及配置。不得把隔离库验收当作业务环境结构证据。

执行后核验唯一 Alembic head、`app.persistence.schema_check` 零差异、新列 COMMENT、kind 回填/索引/唯一约束、父子无孤儿和旧费用合计/回执未变，再以只读查询检查配置。不要自动发起真实同步。

MySQL DDL 非事务回滚：中途失败保留原表和数据，停用新执行器，核对已完成 DDL 后经审查恢复或向前修复；不盲目重放迁移。应用回退默认保留扩展结构。只有独立测试或另行批准且备份、worker 静默时才考虑 schema 降级；存在父批次或子关联时 downgrade 在任何 DDL 前明确拒绝，避免抹除证据。空结构的降级/升级和带旧工单升级已在专用临时库演练。

## 验证证据与边界

任务专用 tmpfs MySQL 8.4.11，127.0.0.1:13306；实际字符集 utf8mb4、排序 utf8mb4_general_ci、UTC、REPEATABLE-READ。测试夹具重新核验目标、版本、会话和执行静默；竞争使用独立连接。未接触业务实例 13307，未执行真实腾讯云调用、业务迁移或部署。

HTTP＋实际 scheduler/worker 的月度验收覆盖：跨年/1–2 日/3 日、固定事件与命名空间、保存时刻和冻结快照、晚到调账、停机合并、部分失败、长缺口有界近期优先、跨月失败总预算、初始化/账号/配置门槛、系统身份脱离浏览器、真实生产循环、在途 epoch 隔离、已提交财务跨 epoch 保留、双调度器竞争、快速分页20/s与余额5/s跨秒事实。单独迁移库验证旧请求升级与拒绝批次证据损失。前端流程验证配置保存、立即复核、部分失败和子任务下钻；类型检查、Ant Design lint 和生产构建另记最终运行结果。
