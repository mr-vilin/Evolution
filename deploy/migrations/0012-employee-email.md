# 0012 人员邮箱迁移手册

本手册为审查与执行准备，不代表业务数据库执行授权。迁移为 `backend/migrations/versions/0012_employee_email.py`，仅新增人员邮箱列；不启动同步、清理或初始化。

## 目标与变更

- 当前任务目标：本机 Docker Compose 项目 `organization-directory`，入口 `http://127.0.0.1:8000`。不适用于远端测试或正式环境。
- 本轮只读检查：MySQL 8.4.11，schema `0011_organization_browser`，数据库及连接 `utf8mb4` / `utf8mb4_general_ci`；实际执行前必须再次核实，不沿用快照替代检查。
- 预期升级 `0011_organization_browser` → `0012_employee_email`。仅新增 `employee.email VARCHAR(254) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL`，默认 NULL，中文注释说明来源与可读性。无新外键、唯一键或索引，不修改已有字段、注释、默认值、生成列或约束。
- 邮箱取飞书用户 `email`，缺失为未采集；格式不可读或长度超过 254 时记录不可读，合法空值保留为空。旧记录不回填，页面明确显示未知（未采集）。

## 执行前核验

从仓库根目录执行 `backend/.venv/Scripts/python.exe deploy/release.py inspect`，核实目标、版本、初始化完成且无活动任务。使用目标已有凭据在容器内执行只读 SQL，不把密码放入命令输出或日志：

```sql
SELECT VERSION(), DATABASE(), @@character_set_database, @@collation_database,
       @@character_set_connection, @@collation_connection;
SELECT version_num FROM alembic_version;
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA,
       CHARACTER_SET_NAME, COLLATION_NAME, COLUMN_COMMENT, GENERATION_EXPRESSION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'employee'
ORDER BY ORDINAL_POSITION;
```

还应保存全部表的引擎/排序规则、列、索引、表约束和外键元数据；业务计数、数据世代、数据版本、初始化状态及现有 app/MCP 镜像 ID。确认 email 列尚不存在，当前版本恰为 0011；发现其他状态停止，不盲目重试 DDL。

## 授权后的顺序

1. 用户明确同意本地备份、恢复演练、0012 迁移和发布后，再进入停写阶段。使用 `deploy/release.py build` 已生成并校验的不可变制品，核对 manifest schema 为 0012。
2. 通过既有 Compose 停止 app/MCP，重新检查无活动任务；保留 MySQL 与原数据卷。
3. 以一致性逻辑备份保存原库；备份仅在内存接收后以 Fernet 加密落盘，密钥经当前 Windows 用户 DPAPI 加密并与备份分目录保存。沿用 `deploy/migrate_local_0010.py` 的加密和元数据核验机制，不直接运行其固定历史版本迁移入口。不在磁盘保存业务明文 SQL。
4. 新建无外网、无事件监听的临时 MySQL 8.4 容器，显式 utf8mb4/general_ci。从加密备份恢复，核对结构、计数、数据世代/版本及初始化状态与原库一致。只在该容器上用候选制品执行 `python -m alembic upgrade 0012_employee_email`，确认仅增加预期列，旧列/索引/外键及业务数据保持。销毁本轮临时容器。
5. 演练成功后，使用同一候选制品、原 Compose 的既有连接配置执行一次目标为 `0012_employee_email` 的 Alembic 升级。不要使用不限定目标的历史临时脚本，不自动启动同步。
6. 按下节核验数据库，再执行 `deploy/release.py deploy --artifact <已构建制品目录>`，随后 `deploy/release.py verify`。发布工具继续检查目标、空闲状态、回退点和资源哈希。保留原认证、会话及业务数据。
7. 在真实浏览器确认全公司默认点选、部门统计、20 人规则、筛选、八列与多部门气泡；真实飞书邮箱权限和后续采集另行验收，空字段不等于采集成功。

## 执行后核验

```sql
SELECT version_num FROM alembic_version;
SELECT COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, CHARACTER_SET_NAME,
       COLLATION_NAME, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'employee' AND COLUMN_NAME = 'email';
SELECT COUNT(*) AS existing_rows, COUNT(email) AS collected_email_rows FROM employee;
```

预期 schema 0012，email 为 varchar(254)/YES/NULL/utf8mb4/utf8mb4_bin，注释非空中文；迁移刚完成时已有人员 email 全为 NULL。比较迁移前后元数据，只允许新增 email 列；业务数量、数据世代/版本和初始化状态保持。发布后若正常事件造成变化，单独记录，不误报为迁移修改数据。

## 失败恢复

- DDL 前失败：不执行迁移，保留证据；确认库仍为 0011 后恢复原 app/MCP 镜像。
- MySQL DDL 不可依赖事务回滚；新增列后但版本未更新时，停写并核查列及 Alembic 状态，不直接重跑或手工 stamp。
- 0012 后应用失败：标准发布工具禁止跨 schema 直接回退镜像，不绕过就绪检查。优先修复并发布匹配 0012 的应用；如需恢复 0011，必须另行授权，在停写状态恢复迁移前备份与对应旧镜像，核对结构、计数、会话/数据世代恢复边界及运行健康。
- Alembic downgrade 会删除邮箱列及其值，不能作为无损回退。即使尚无采集邮箱，也要明确授权后执行，并核验全部原有字段及数据保留。

## 当前验证状态

已在独立临时 MySQL 8.4.11 中完成全部 1404 项后端测试，包含升级/降级保留既有 schema、索引、外键及合成人员数据的验证；临时容器已删除。该结果不等于对本地业务备份的恢复演练。用户后续明确授权后，本地业务库已完成加密备份、隔离恢复演练与 0012 迁移，并用标准 release.py 发布。逐表原有业务数据摘要及原有元数据保持；DPAPI 落盘密钥与加密备份可在内存恢复验证。迁移与发布证据见 [本地记录](../../docs/architecture/local-employee-email-deployment-2026-11-06.md)。不将该本地记录作为其他环境的授权或验证证据。
