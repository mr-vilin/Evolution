# 组织目录字段与接口调整

适用 MySQL 8.4。迁移从 `0023_remove_connection_coverage` 升至 `0024_organization_schema`。应用、MCP 和数据库在同一次切换中升级。调用方将部门对象中的 `is_virtual_root` 改为 JSON 布尔字段 `is_root`，详见[接口契约](../../docs/backend-api.md)。

| 表 | 结构变更 |
| --- | --- |
| `department` | `is_virtual_root` 改为无符号布尔列 `is_root`，`last_seen_at` 改为 `last_sync_at`，增加 `create_time` 和 `update_time`。保留父部门单列索引并命名为 `idx_parent_id`，保留同级排序和按 ID 分页的索引选择。唯一索引改名为 `uk_feishu_department_id`。 |
| `employee` | `last_seen_at` 改为 `last_sync_at`，增加 `create_time` 和 `update_time`。五个可空账号标志改为无符号布尔列，`join_time` 改为无符号 BIGINT，补全可读性注释，规范主部门及唯一索引名称。 |
| `employee_department` | `active` 改为 `is_active`，与 `is_primary` 一起改为无符号布尔列，反向查询索引改名为 `idx_department_id`。复合主键维持关系唯一性。这张关联表会在同步中重建关系行，省略创建和更新时间。 |

`last_sync_at` 保留历史值及空值，并由同步发布流程维护。同步确认相同资料时也刷新。`create_time` 与 `update_time` 由数据库维护，已有行从迁移 UTC 时刻开始记录。部门或员工行变更时刷新 `update_time`，包括同步时间变化。数据库会话使用 UTC。

## 执行与验证

1. 在目标环境核对 MySQL 版本、当前迁移、字段类型、注释、索引、关联约束和字符集。确认布尔值只含 0、1 及允许的空值，根标志与部门 ID 0 一致，入职时间没有负值。
2. 按[发布流程](../ENVIRONMENTS.md)准备配套制品，停止应用和同步写入，记录三表行数并验证一致性备份的恢复。先在隔离实例演练升级与降级。
3. 执行受审查的 Alembic 迁移后，用 `app.persistence.schema_check` 比对实际结构，核对三表行数、主外键、索引及原同步时间和空值。用部门详情、组织树、员工嵌套部门和 MCP 部门工具验证新字段，核对待核验部门的门店推导。用执行计划检查同级排序、按父部门分页及按部门查询成员。

数据库 HTML 目录静态提取模型和历史 DDL。它可能把本迁移的重命名列和自定义布尔映射列为差异，实际列定义以 `SHOW CREATE TABLE` 和结构校验为准。

## 失败恢复

每张表各用一条原子 DDL，MySQL 仍可能在表与表之间留下部分完成状态。发生失败时维持停写，核对迁移版本和三张表的实际定义。在线重试会跳过已完成的表。完整升级后需要回退时，先留存新增的行级时间，降至 `0023_remove_connection_coverage` 后启用对应旧版应用和客户端。若结构或数据核对失败，使用迁移前已验证的备份恢复。
