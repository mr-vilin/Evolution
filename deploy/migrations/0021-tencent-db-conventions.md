# 腾讯云数据库规范整改：0020 → 0021

本次只将 `tencent_sync_config.schedule_start_date` 从可空 `VARCHAR(10)` 改为可空 `DATE`，保留默认值和中文备注，并重命名五个 `ix_tencent_*` 普通索引为 `idx_tencent_*`。索引列、列序和唯一性不变；账号、费用、历史任务、业务账月及日月共用的 `period_key` 均不改。后者是混合粒度的业务标识，不是单纯日期字段。调度仍按北京时间计算日历边界，连接时区仍为 UTC，管理端契约及补采口径不变。

## 迁移前

仅在另获执行授权的目标环境操作。核对实际目标、源版本 `0020_tencent_history`、MySQL 8.4、InnoDB、库表字符集/排序规则以及应用会话的时区和隔离级别。以下查询只读，使用目标环境的应用连接配置：

```sql
SELECT DATABASE(), VERSION(), @@character_set_connection, @@collation_connection,
       @@time_zone, @@transaction_isolation;
SELECT version_num FROM alembic_version;
SHOW CREATE TABLE tencent_sync_config;
SHOW INDEX FROM tencent_api_call;
SHOW INDEX FROM tencent_sync_job;
SHOW INDEX FROM tencent_cost_period;
SELECT COUNT(*) FROM tencent_sync_config
WHERE schedule_start_date IS NOT NULL;
SELECT COUNT(*) FROM tencent_sync_config
WHERE owner IS NOT NULL OR active_job_id IS NOT NULL;
SELECT COUNT(*) FROM tencent_sync_job WHERE status = 'running';
```

确认五个旧索引的定义与 [0021 迁移](../../backend/migrations/versions/0021_tencent_db_conventions.py) 及 0020 制品一致，新名称未占用。暂停应用写入、调度和 worker，确认已无运行任务或在途执行资格。保留旧制品、数据库一致备份、结构快照和数据摘要；先恢复到隔离 MySQL 演练。日期转型可能重建配置表，按环境表量和恢复窗口安排维护时间。迁移通过在线 Alembic 运行，逐行校验非空日期必须是 MySQL 支持范围内的规范公历日期，遇坏值在任何 DDL 前拒绝，仅报配置 ID，不自动修值。离线生成的 SQL 仅供审查，不能替代在线预检。

## 迁移后

在演练库和目标库分别核对：版本为 `0021_tencent_db_conventions`；五个索引名已转换且定义不变；日期类型为 `DATE`，规范化文本值、空值计数、配置其他字段和既有业务数据摘要不变。运行 `python -m app.persistence.schema_check` 检查实际结构与连接；再检查目标制品的就绪状态，以及日周锚点、任务领取、费用看板。确认后才恢复写入和调度。

MySQL DDL 不保证多条语句整体回滚。中途失败保持停写，核对实际表结构和迁移版本，按已演练备份恢复或经评审补齐剩余 DDL；不要盲目重跑或仅改版本号。完整升级后回退到 0020 时先停写并备份当前数据，再执行 0021 的反向迁移。有效日期恢复为同一天的 ISO 文本，五个索引恢复原名，然后运行匹配的旧制品。跨更旧版本仍受既有历史、日账和批次证据保护，不把多跳降级作为常规恢复路径。

## 隔离 MySQL 复核

MySQL 8.4.11，临时库与生产数据隔离。使用 32 个合成账号、1,152 个历史账期和尝试、9,216 条产品行，采集实际 worker 和看板发出的 SQL，并执行传统 `EXPLAIN`：

| 查询 | 样例计划 |
| --- | --- |
| 任务领取 | 候选任务走 `idx_tencent_job_claim`（`range`），配置走主键（`eq_ref`）；公平性历史聚合仍扫描尝试索引，窗口计算及排序会用临时表和排序 |
| 账期范围 | `idx_tencent_period_month`（`range`） |
| 产品明细 | 账期走 `uk_tencent_period_scope`（`ref`），产品走 `uk_tencent_item_row`（`ref`），仍有排序 |
| 看板任务状态 | `uk_tencent_job_request`（`ref`），月份与 JSON 币种后过滤，仍有排序 |

计划是合成数据样本，不等于线上延迟或容量结论；历史尝试增长后优先复核领取聚合代价。未执行任何业务环境的 0021 迁移或发布。
