# 移除飞书连接覆盖状态

迁移 `0023_remove_connection_coverage` 在 MySQL 8.4 上移除 `feishu_connection.coverage_status`。应用仍使用连接表保存飞书应用、租户和自定义字段配置。数据集覆盖列继续供旧 API、MCP 和运维流程过渡使用。

## 执行前

1. 核对目标环境和当前 Alembic 版本 `0022_mysql_general_ci`。用应用连接核对 MySQL 版本、`utf8mb4` / `utf8mb4_general_ci` 和表结构，确认待删列没有索引、约束或应用之外的查询依赖。
2. 只统计 `SELECT coverage_status, COUNT(*) FROM feishu_connection GROUP BY coverage_status`，预期仅有 `unknown` 或暂无绑定。出现其他值时先记录来源。保存结构、应用绑定与组织数据的备份，并演练恢复。
3. 停止使用旧结构的 app、worker、飞书监听和 MCP，再按项目环境流程执行迁移。

## 验证与回退

- 确认 `feishu_connection.coverage_status` 已移除，`dataset_state.coverage_status` 仍存在，应用绑定、租户和配置记录与迁移前一致。检查 `/health/ready`、管理端同步摘要和原有 API 响应。
- 若需回退，先停写入方，再降级至 `0022_mysql_general_ci`。降级把已有绑定的覆盖值恢复为 `unknown`，并恢复原字段的非空及无默认值约束。核对结构后启动旧镜像。需要恢复迁移前的实际列值时使用迁移前备份。
- MySQL 的 DDL 会隐式提交。若迁移中断，先核对实际列定义和 Alembic 版本。结构与版本不一致时，从已演练的备份恢复到匹配的结构和版本，再重新迁移。
