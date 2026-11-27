# 0027 组织变更上下文迁移

MySQL 8.4，基线为 0026_org_table_names。在 change_log 添加五个可空字段，保存组织同步事务、任务或事件来源、对象名称及执行人快照。沿用 InnoDB 与 utf8mb4_general_ci，不更新历史行。

## 执行前

确认目标环境、备份与回退点。核对 SELECT VERSION()、当前 alembic_version、SHOW CREATE TABLE change_log 以及连接字符集和排序规则。确认新增字段不存在，现有表结构与 0026 一致。核对迁移账户权限和业务写入窗口。

## 执行后

检查 alembic_version 为 0027_org_change_context，使用 SHOW FULL COLUMNS FROM change_log 核实字段类型、可空性和中文注释。核对原有审计行数、主键与索引未发生变化。通过测试环境的任务与事件用例验证新记录包含 publication_id 和相应来源。

## 恢复

保留迁移前备份。若 DDL 部分完成，先检查实际字段，再由数据库负责人决定继续补齐或恢复备份，避免重复执行 DDL。降级会丢失新增组织变更上下文，使用降级脚本之前导出相关元数据并确认应用版本兼容；需要完整恢复时使用迁移前备份。