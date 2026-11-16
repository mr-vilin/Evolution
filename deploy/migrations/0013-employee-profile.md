# 人员头像与入职日期迁移（0013）

## 范围与当前状态

2026-11-07 核实本地 Docker：MySQL 8.4.11、InnoDB、数据库及应用连接为 `utf8mb4 / utf8mb4_general_ci`，连接时区 `+00:00`；实际迁移版本为 `0012_employee_email`。测试、正式环境未核实，不适用本记录。

本次仅在 `employee` 新增两个可空列，不修改原有字段、索引、约束和业务记录：

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `avatar_url` | `VARCHAR(2048)`，`utf8mb4_bin` | 飞书头像 HTTPS 地址；无默认填充值，无新增索引 |
| `join_time` | `BIGINT` | 保留飞书 Unix 秒时间戳（包含 0），API 按北京时间返回 `join_date`；缺省、空值或不可读时存 NULL |

两列均有中文字段注释。入职字段存储来源时间戳以保留飞书语义，展示层只返回日期；不把服务器本地时区用于日期转换。已有 `field_readability` JSON 追加字段可读性键，不更改该列结构。人员表新增后为 29 列。

同步采集后才有真实头像及入职日期；迁移本身不回填、不初始化、不发起同步。缺头像显示默认头像，日期区分未填写、未采集和不可读。上级头像取已同步上级记录，未采集上级时不伪造头像或姓名。

## 执行前检查

1. 必须另行获得本地数据库迁移授权；默认本地镜像发布授权不包含 DDL 或业务同步。
2. `backend/.venv/Scripts/python.exe deploy/release.py inspect` 确认环境、schema 为 0012、无活动初始化或同步任务。
3. 通过既有应用连接只读检查 MySQL 版本、连接字符集、时区；导出全库结构快照和表行数/摘要，保留 employee 的原字段默认值、注释、索引及外键证据。确认 `avatar_url`、`join_time` 不存在。
4. 使用标准 `deploy/release.py build` 生成 0013 镜像；保存当前 app/MCP 不可变镜像 ID、Compose 覆盖与来源记录。
5. 在发布锁保护下停 app/MCP 写入；再次确认任务空闲。按仓库加密备份流程备份全库，密钥以当前 Windows 用户 DPAPI 独立保存，不落盘明文或输出凭据。
6. 在隔离 MySQL 8.4 临时实例恢复备份，比较全库结构与数据摘要，然后使用同一候选镜像演练 `alembic upgrade 0013_employee_profile`。只有新增两列且旧数据/结构保持一致后才能迁移业务库。

## 迁移与发布

迁移源文件：`backend/migrations/versions/0013_employee_profile.py`。复核 SQL 可在 backend 目录运行 `alembic upgrade 0012_employee_email:0013_employee_profile --sql`（仅生成脚本）。实际执行使用候选镜像内 Alembic、既有 Compose 连接及单独授权，不在命令行传入密码。

执行后核验：版本为 0013；新增字段类型、NULL、字符集和中文注释正确；原字段、默认值、注释、索引、外键、各表数据摘要不变；两列均为 NULL，无自动业务回填。随后通过 `deploy/release.py deploy --artifact <候选制品目录>` 和 `verify` 完成本地发布。

本地执行器为 `deploy/migrate_local_0013.py`。必须在当前实际部署目录执行，以沿用其 `.env`、Compose 项目与部署锁；不要在隔离源码工作树中使用环境默认值。执行器校验制品压缩包、源码文件与镜像摘要，保留旧镜像和部署来源，从落盘密文及独立 DPAPI 密钥执行恢复演练，并在真实迁移前后比较原结构和全表数据摘要。执行器成功后服务保持停写，随后由标准发布入口启动新镜像。

```powershell
# 当次已明确授权后，在实际本地部署目录执行，artifact 替换为已核验制品。
backend/.venv/Scripts/python.exe deploy/migrate_local_0013.py --artifact .cache/artifacts/<release-id> --authorized-local-migration
backend/.venv/Scripts/python.exe deploy/release.py deploy --artifact .cache/artifacts/<release-id>
backend/.venv/Scripts/python.exe deploy/release.py verify
```

## 失败恢复

MySQL DDL 不保证事务回滚。若只成功新增一列，立即停止并保存实际元数据，不盲目重跑 migration。服务保持停写，评估完成剩余 DDL 或从已演练的加密备份恢复；操作均须在授权范围内。

旧镜像就绪检查严格要求 schema 0012，因此仅恢复旧镜像不能完成跨迁移回退。若须回退，应停写并备份迁移后新增数据，在独立授权下执行 downgrade 或恢复迁移前备份，并核对 schema、业务摘要后恢复旧镜像。downgrade 会删除两列，不能当作无损操作。

## 验收范围

应覆盖采集缺省/空值/非法值、HTTPS 头像、北京时间日期边界、发布与读取上级头像、真实 MySQL 升降级与旧数据保留。隔离测试通过不代表业务库迁移、真实飞书采集或本地发布已完成。

2026-11-07 发布前验证：资料、同步和组织接口相关测试 42 项通过，就绪检查及生命周期回归 55 项通过；独立 MySQL 8.4 测试实例完成 0013 升降级、中文注释、字符集、原字段/索引/外键及原数据保留验证（1 项）。

后续已按用户当次授权完成本地加密备份、恢复演练、0013 真实迁移及本地 Docker 发布。迁移前后原结构与全表数据摘要一致；部署与独立复核通过。备份、回退边界、运行状态及验收限制见[本地发布记录](../../docs/architecture/local-employee-profile-deployment-2026-11-07.md)。
