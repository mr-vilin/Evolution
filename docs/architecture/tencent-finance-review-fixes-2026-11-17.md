# 腾讯财务两轴审查修复与验证

2026-11-17—18，对集成基线 `c391c52bbf4cbe4b614f1dcdf8b5e2fe42f83581` 的规格轴与规范轴报告统一修复。用户后续 `implement-spec` 授权父工单 #15、子工单 #16–24 和本机独立临时 MySQL 写入。本记录说明代码与本地验证，真实腾讯云联调、业务库迁移及部署均未执行。

## 修复语义

| 问题 | 最终行为 |
| --- | --- |
| 月模式可提交 day 绕过月三日到期 | 新请求仅 daily/weekly 可带 day；原幂等任务先按原身份重放，不改原冻结范围 |
| 合法小队列只受理部分近期期间，父批次提前完整 | recent＋可处理旧缺口统一计算 selected/deferred，阻止和窗口外独立披露，audit 使用真实延期长度；延期保留原父批次、执行策略、频率及身份，已覆盖近期仍按原意图复核 |
| 周中持续发现扩大周日目标 | 自动发现和历史页面沿最后实际受理的计划点；继续推进旧范围，下一计划点才扩展新日期；人工 range/all 按本次受理时刻 |
| 旧 epoch 刷新在采集前被拒绝却降级费用 | 任务拒绝事实保留；未开始的资格门槛拒绝不改变已提交完整费用的总额和比较资格，真实采集失败仍显示保留旧值 |
| 最老来源月排队跨月后，冻结零值资格过期 | 空月证明前后及发布事务内同时核对冻结资格和当前真实来源窗口；移出窗口则 ZERO_UNCONFIRMED，保留旧产品及非零总额 |
| 金额/比例/时间缺少排序 | 每表受控单列三态，筛选后全量稳定排序再分页；空值升降均置底，刷新保留；金额用八位固定单位 BigInt 比较，不经 Number |
| 账号及账月费用卡高度和窄屏未适配 | 共用实际顶栏、工具栏、摘要、分页、行高测量，60%/三行预算分支、低位整卡吸顶、极矮自然滚动；窄表体优先保留名称，右固定按中间96px预算退让。ProTable固定布局变化时重建内部列状态，外部排序/分页保留 |
| 时间依赖浏览器时区或省略秒 | 腾讯页面共享显式 Asia/Shanghai 的 YYYY-MM-DD HH:mm:ss；表格统一12px/20px/400/说明灰 |
| 独立 worker 丢 INFO，未知异常无安全定位 | main 首先初始化 JSON INFO；仅白名单关联、异常类型与最多4链/每链12帧，排除任意消息、源码行、locals、SQL参数与响应正文；心跳、调度、领取、执行和停机捕获保留安全诊断。重试 WARN、最终失败 ERROR |

## 数据库与测试边界

所有 MySQL 验证仅本机 `127.0.0.1:13306` 的 `tencent_*_test` 和迁移夹具随机测试库，实例 MySQL 8.4.11。夹具自身核验数据库名、端口、版本、utf8mb4/utf8mb4_general_ci、UTC、REPEATABLE-READ 及 worker 静默后才写入。业务实例 `evolution-mysql-1` 与业务端口13307未操作。schema head 仍为0020_tencent_history；本轮没有新增迁移。

主行为用管理端 HTTP → 真实任务/调度/worker → 独立 MySQL，只有腾讯出站响应使用可控传输。低队列、跨配置延期、周中边界、旧epoch拒绝、跨月零值、实际数据库写故障和失败日志均观察公开任务/费用结果。独立子进程直接调用生产 main、真实领取及提交，只有出站和有界停止时间被注入，确认 INFO start/commit/stop JSON。

原全量中的三个测试入口随契约适配：manual-day 迁移用例通过 ORM 构造修复前旧任务继续证明降级不丢证据；自动预算耗尽月仅在 blocked，不再同时作为 deferred；离线原生 SQL 执行显式 no_parameters，防止 PyMySQL 把 DATE_FORMAT 的 %Y 当绑定。全表非空 Evaluation 夹具补齐七张腾讯表的静默终态合成记录，仍保留全表非空及 reset 后仅基线表断言。

## 已观察验证

- 全 MySQL 集成：跨月补充前263通过，包含非腾讯旧模块、迁移、Evaluation及全部腾讯流程；534.35秒。跨月队列/辅助查询与独立main补充3项通过；加入guard后的全部腾讯集成213通过、53个非腾讯用例未选取，502.92秒。随后加强每日queue1已有覆盖近期重查及真实审计延期计数的单项再次通过（19.68秒）。
- 非集成后端与部署测试：1450通过、16跳过，87.60秒。跨月guard及worker日志修改均包含在此验证内。
- 前端全量：34文件112项通过，147.78秒；腾讯前端：8个测试文件25项通过；包含账号完整数据排序/分页/刷新、八位小额负数、大金额相邻值、缺失和稳定顺序及非上海时间。
- 真实 Edge 146.0.3856.109、UTC 上下文、仅合成API：9场景通过。账号1440×900、1152×720等效125%可用视口、侧栏收起、1000×350极矮、260px容器；费用低位卡、等效125%视口、单行和空表。等效视口验证未修改系统缩放，不等同操作浏览器真实缩放控件。
- 账号宽屏分页底850.59/视口900；等效125%底670.59/720；极矮保留171px三行并自然滚动；210px表体保留左固定、解除右固定。低位费用卡top80.31、分页底851.31/900，等效125%底671.31/720；少量/空表自然收缩。
- 最终typecheck、生产build、Ant Design差异检查（0问题、0跳过、非partial）及git diff --check通过。
- 版本工具9项与相对主分支基线5792913的历史保留检查通过；version.json不变。本分支只维护Unreleased，候选整理由集成交付完成。

共享证据位于本任务visualizations目录：`tencent-review-fixes-mysql-complete.log`、`tencent-review-fixes-rollover.log`、`tencent-review-fixes-mysql-postroll.log`、`tencent-review-fixes-frontend.log`、`tencent-review-browser-results.json`、`tencent-browser-check.cjs`及`tencent-review-*.png`。全量非集成后端、前端、类型、构建和antd日志分别为`tencent-review-fixes-backend.log`、`tencent-review-fixes-frontend-all.log`、`tencent-review-fixes-typecheck.log`、`tencent-review-fixes-build.log`、`tencent-review-fixes-antd.json`。

真实CAM权限、真实账单来源窗口和有效零值仍待同账号同口径联调；模拟源通过不证明腾讯实际可取范围。未启动业务同步，未部署或发布版本。
