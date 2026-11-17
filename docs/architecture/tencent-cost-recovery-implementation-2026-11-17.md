# 腾讯云成本重试、追溯与恢复（T04）

2026-11-17，对应 [#19](https://github.com/mr-vilin/Evolution/issues/19)。在 T03 的同事务完整月发布基础上扩展，不部署、不执行任何业务环境迁移或真实腾讯云请求。专项规则使用系统研发入口及数据库、API、权限、调用审计、日志、定时任务、Ant Design 与全局版本规范。

## 项目执行值

权威队列为 MySQL 8.4 的腾讯云任务/尝试/配置表，不占组织单例 worker 租约，不增加部署拓扑。原应用容器中的成本 worker 以 `run(stop,max_concurrency=2)` 跨配置并发，上限可在程序入口控制为 1–8；每配置整轮串行，包含重试等待。收到停止信号后不再领取，已领取尝试按预算完成或留下接管证据。SDK 每次调用 10 秒、NoopRetryer；采集前后和发布前检查预算，心跳不延长尝试或轮次预算。

| 配置 | 默认值 | 校验范围及语义 |
| --- | --- | --- |
| max_attempts | 3 | 1–5，包含首次；最多 2 次自动重试 |
| deadline_seconds | 90 | 30–300，单次完整采集/发布预算 |
| run_deadline_seconds | 900 | 60–86400，从首次领取起计算，包含执行、退避及重试；不得小于单次预算 |
| retry_base_seconds / retry_max_seconds | 30 / 300 | 5–300 / 5–900，指数退避；上限不得小于基数 |
| retry_jitter_seconds | 5 | 0–30，在有界退避上叠加的抖动上限 |
| lease_seconds / heartbeat_seconds | 120 / 20 | 30–600 / 5–60，心跳不得超过租约三分之一 |
| queue_limit | 200 | 1–500，当前配置/epoch 下 pending、running、retry_wait 合计上限 |
| queue_deadline_seconds | 86400 | 60–604800，可靠受理至首次领取的独立等待上限 |
| max_rows | 10000 | 1–10000，单次产品行数上限 |

受理在配置锁内检查队列和稳定幂等，满队列返回 429/TENCENT_COST_QUEUE_FULL；同幂等重试先返回原受理，不重复占队。首次领取前过期不伪造尝试。领取候选先按可执行配置分组，运行中/退避占用的同配置积压不挤占全局前 100 条候选窗口，避免另一个配置饿死。

自动重试仅处理 TENCENT_TIMEOUT、TENCENT_RATE_LIMITED、TENCENT_UNAVAILABLE 和已明确可重复采集的 TENCENT_COST_NOT_READY。权限、参数、归属、契约/安全资格变化、完整性错误、单次或总预算耗尽不盲重试。次数或总截止不足以等待下一次时直接结束。普通配置 revision 只影响新轮次；control_revision 独立隔离停用之前的任务，停用再启用也不复活旧任务。

## 事实捕获与恢复

实际输入在出站前提交，包含完整补齐后的执行策略、固定期间/口径、凭据安全引用、原可信 open_id、请求关联和执行代次。每次重试保留同 job，新增 attempt 和独立 request_id。执行时复查当前白名单，不依赖浏览器自然有效期；不保存 token、digest、CSRF 或秘密。普通组织 data_version 更新不取消费用任务。

处理契约 `tencent-cost-month-v1` 的正常返回就是完整的精确提交回执，不含整批账单。费用期间、全部产品、job/attempt 成功状态、原始回执和配置进度同事务保存。job.commit_receipt 是原回执的同事务恢复副本；attempt.execution_output 是当次真实返回存档。输入和回执内联完整保存，源分页受 10000 行和请求 ID 128 字符限制，正常回执约束在 32KiB 内；不以摘要、当前配置或日志链接替代完整历史。

| 返回事实 | 解释 |
| --- | --- |
| VALUE | 已确认处理器正常返回；输出归档单独标记保存状态 |
| NOT_RETURNED | 处理器因已观察异常未正常返回，execution_output 为空，另存稳定安全失败证据 |
| UNKNOWN | 执行者失联，返回事实无法确认；结束时间保持空，不伪造结束 |

返回事实与保存状态独立：output_capture_status 为 CAPTURED、FAILED、NO_CONTENT 或 UNAVAILABLE。正常返回但输出归档缺失时保留 VALUE 并显示 FAILED，不能改写成未返回；仅从原事务回执修复后恢复 CAPTURED。输入在出站前已可靠保存，input_capture_status 为 CAPTURED。

上游 HTTP 已返回错误和处理器未正常返回是两层事实：raw/官方 SDK 错误保存经校验的上游 RequestId、稳定原因与 ERROR 状态；对应 outbound 审计有真实 returned_at；handler attempt 为 NOT_RETURNED。Message、任意异常原文和上游财务正文不进入失败证据。

提交确认丢失时先用新连接核实原 job/attempt 的成功状态和原回执，返回同一回执，不重新采集。重启扫描也修复成功尝试的归档缺口，仅复制原事务保存的回执并标记 archive_repaired；不能从当前期间费用重建旧回执。全部数据库不可用时不伪造核实成功，保留既有执行资格和后续恢复依据。

租约失联时在短事务内核对当前资格、递增 generation 并隔离旧执行者；旧运行尝试转 UNKNOWN，保留独立输入、空结束时间及观察时间。只有安全只读采集且剩余预算允许，才继续同 job 的新 attempt。迟到执行者在出站前和发布时受 owner/generation/期限/当前资格共同拒绝。重试等待保留 active_job_id，防止后续同配置轮次越过；正常心跳只延长当前合法 owner 的期限，并受单次/总截止限制。

初始化未完成时领取循环空闲。恢复产生新 epoch 后旧活动任务与 owner 被隔离，旧任务不重绑新世代；幂等唯一键为 config_id+dataset_epoch+idempotency_key，新世代可复用相同手动请求键。已提交费用与全部历史保留。公共 evaluation reset/seed 和测试夹具均拒绝 owner、active_job_id 或活动执行；退避中的 owner 为空也不允许清理。

## 接口和页面

新增 `POST /admin/api/tencent/cost-jobs/{job_id}/rerun`，动作 tencent.cost.rerun，真实管理员+CSRF；请求为 idempotency_key 和结构化原因 after_fix/refresh_result。仅终态原任务可重跑，创建 source_job_id 关联的新逻辑任务，使用当前经过校验的策略/绑定/epoch，原任务及所有历史保持不变。稳定请求键范围和费用原子替换规则不变。

详情新增 source_job_id、next_attempt_at、deadline_at、queue_deadline_at 和逐次 request_id/return_state/failure_evidence。当前配置和任务、期间的所有入站路由从数据库账号设置审计 target UIN，不能相信客户端目标。

成本页面用中文数值控件修改策略，并逐字段校验范围/预算关系。任务详情分开显示逻辑任务状态、每次尝试状态、已核实时间及全部结构化只读输入/返回；未知和未返回不显示成空成功。自动重试等待显示下一次时间；终态提供原因选择和人工重跑，网络受理未知时保持同一请求键。没有 JSON 录入或密钥入口。

## 0016 迁移与恢复

迁移 head 为 `0016_tencent_recovery`，下接 0015；新增列均有中文 COMMENT，稳定 epoch/请求 ID 保持 utf8mb4_bin，其他表规则沿用 InnoDB/utf8mb4_general_ci，无物理外键。control_revision 从旧 revision 回填；epoch 从原 snapshot 回填；历史成功回执从原成功 attempt 复制。旧任务独立等待截止从 create_time+86400 回填，已开始轮次截止从 started_at+900 回填；旧 attempt 输入不改写，新 attempt 补齐本版本策略默认值。

业务环境执行须另行授权并先静默全部成本 worker、备份受影响表、记录 alembic 版本和现有结构。只读预检：

```sql
SELECT version_num FROM alembic_version;
SELECT DATABASE(), VERSION(), @@character_set_connection, @@collation_connection, @@time_zone, @@transaction_isolation;
SELECT id, revision, owner, active_job_id FROM tencent_sync_config WHERE owner IS NOT NULL OR active_job_id IS NOT NULL;
SELECT id FROM tencent_sync_job WHERE JSON_EXTRACT(snapshot,'$.dataset_epoch') IS NULL OR JSON_TYPE(JSON_EXTRACT(snapshot,'$.dataset_epoch')) <> 'STRING';
SELECT config_id, idempotency_key, COUNT(*) AS copies FROM tencent_sync_job GROUP BY config_id,idempotency_key HAVING COUNT(*)>1;
```

前两项确认实际 MySQL8.4、当前0015与连接配置；活动资格先按有证据的恢复流程收尾；epoch 缺失先核实来源，不猜测回填。最后一项是降级前检查：若新世代重复键已存在，不得降级为旧两列唯一索引，更不能删除历史来强行降级。

执行后验证 schema_check、全部新字段类型/中文注释、唯一索引顺序、epoch 回填、成功 job 的原事务回执与 attempt 输出一致，以及外键/金额列未变化。MySQL DDL 非整体事务：中途失败先按备份和实际列/索引清单核对，保留原表，禁止盲重跑或清空。优先保留前向兼容 schema 回退应用；只有备份确认、worker 静默、降级预检通过且额外授权时执行 Alembic downgrade，归档证据需先保存。

## 验证证据和边界

只使用本机13306、MySQL8.4.11、任务专用 tencent_t04_*_test 隔离库；新建完整迁移验证了实际字段、中文注释、索引、会话和精确金额，未触碰13307业务实例。旧试验库存在迭代期间 schema 漂移时创建新的隔离库，不修改有活动资格的旧库。

迁移前只读预检（目标环境逐一核实，不打印连接凭据）：

```sql
SELECT DATABASE(),VERSION(),@@character_set_connection,@@collation_connection,@@time_zone,@@transaction_isolation;
SELECT version_num FROM alembic_version;
SELECT COUNT(*) FROM tencent_sync_config WHERE owner IS NOT NULL OR active_job_id IS NOT NULL;
SELECT COUNT(*) FROM tencent_sync_job WHERE status IN ('pending','running','retry_wait');
SELECT id FROM tencent_sync_job WHERE JSON_TYPE(JSON_EXTRACT(snapshot,'$.dataset_epoch'))<>'STRING' OR JSON_EXTRACT(snapshot,'$.dataset_epoch') IS NULL;
-- 降级额外预检：跨世代同键不允许压回旧唯一键。
SELECT config_id,idempotency_key,COUNT(*) FROM tencent_sync_job GROUP BY config_id,idempotency_key HAVING COUNT(*)>1;
```

执行前应已有授权、备份和 worker 静默。发现无法回填的旧快照先停止核实；MySQL DDL 分段提交，失败时保留结构和证据，根据实际列与迁移版本恢复，禁止盲目重放。升级后使用 `database_ready` 与 `check_schema` 核对 head、实际列/中文备注、唯一键及会话，再核对旧回执、epoch、控制修订和预算。降级会丢失本票新增的恢复字段，默认应用回退保留 0016；必须降级时先导出受控证据，预检跨世代重复键、未知/活动任务并核实备份。程序遇重复键在首个 DDL 前拒绝，不能删除任务来迁就旧结构。

真实 HTTP→实际 worker→独立连接 MySQL，腾讯云原始出站为合成传输：验证网络重启重试、固定旧策略、raw/官方 SDK 限流 RequestId、预算耗尽、失联接管/迟到拒绝、提交确认丢失零重采、重启修复原回执、epoch 幂等、队列预算/过期、101条同配置积压下独立配置推进、生产并发循环/停止收尾、真实心跳续租、关联重跑及可信UIN审计。前端流程测试覆盖开启采集、逐次完整事实和重跑、字段级策略校验；类型/生产构建与Ant Design检查单独执行。真实腾讯云、真实业务登录会话、业务库迁移与部署仍未验收。

## 本票最终复核

已合入集成分支 `a99bdca28b4a6cd110433e403cf5261f633c5d27`，保留多月看板及已提交费用跨组织世代继续有效的行为。

- 独立 MySQL 8.4.11 新库 `tencent_t04_final_test` 从空库迁移至 0016，账号、余额、完整月、重试恢复和看板的 HTTP/worker/MySQL 回归共 108 项通过；包含 VALUE 与归档保存状态分离后的重启修复。
- 新库 `tencent_t04_migration_final_test` 完成 0015 合成历史回填、0016 实际结构、静默降级再升级演练；中文字段注释、epoch 唯一键顺序通过核验。再植入跨世代同幂等键的两条合成终态记录，确认降级在首个 DDL 前拒绝，版本、列和全部历史保持完整。
- 前端任务详情、手动成本页面和多月看板共 3 文件、5 项流程通过；生产构建（含 TypeScript 检查）成功，生成 112 个资源。此前本票 3 个组件的 Ant Design 检查无问题。
- 测试仅使用 13306 隔离实例和合成腾讯云传输，未连接 13307 业务库，未执行真实腾讯云请求、真实登录会话验收、业务迁移或部署。合成迁移冲突证据保留于独立测试库。