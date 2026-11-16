# 人员列表与详情抽屉本地发布记录

2026-11-07，按用户当次明确授权完成“本地加密备份 → 恢复演练 → 0013 迁移 → 本地部署”。目标为当前 Windows 主机的 Docker Desktop，实际部署目录为 `D:\WorkBench\AI Projects\OrganizationalStructure`，Compose 项目为 `organization-directory`，本机入口为 `http://127.0.0.1:8000`。

## 发布结果

- 制品：`release-20261107-092950-a80aac3e`；源码基于提交 `6d13e8eba8934a193fa078555dd4efe8362e1470` 的开发快照（dirty=true），不是已提交的正式发行版。
- 实际 app/MCP 镜像：`sha256:9903e270ff971185b9b3980ef02cbcefbc8661fb624e394bbbff138a83d86f50`。
- 构建时间：`2026-11-07T09:33:44.563Z`。
- 数据库：MySQL 8.4.11；schema 从 `0012_employee_email` 升级至 `0013_employee_profile`。
- 通过标准 `deploy/release.py deploy --artifact ...` 完成发布，并另行执行 `verify` 通过。app/MCP healthy、实际镜像、宿主机端口、live/ready、未登录接口 401、前后端构建信息及 72 个 JS/CSS 资源哈希均通过。

源码范围按 `.cache/profile-source-scope.json` 核验，采用此前运行源码与本次 21 个文件的隔离候选，排除无关品牌图片及旧迁移文档改动。制品压缩包 SHA-256 为 `eabb8c9930bd34e5b505af77c2b556ae09dab69d192cb01abf9149318989b163`；源码逐文件摘要及候选镜像摘要检查通过。

## 加密备份、恢复演练与真实迁移

执行前发现一个既有 `listener:reconnected` 核对任务，等待其自然结束后再停 app/MCP 写入。该任务将数据版本从 33 推进到 34、人员部门关系从 57 增至 58；这是迁移前的正常同步结果。迁移基线采用停写后的版本 34。

实际执行器：`deploy/migrate_local_0013.py`，SHA-256 为 `b3a6ba69b6805c872c2b3164a44ec114a3837fa42af446ee7d17060584454f84`。应用数据库会话实测为 `utf8mb4 / utf8mb4_general_ci`、时区 `+00:00`；mysql CLI 的连接排序规则为 `utf8mb4_0900_ai_ci`，已与应用会话分别记录，未改变数据库排序规则。

全库使用 Fernet 加密备份，密钥使用当前 Windows 用户 DPAPI 独立保护，无明文备份或明文密钥落盘。演练从实际保存的密文和 DPAPI 密钥读取、解密，在无网络、无映射端口、tmpfs 数据目录的临时 MySQL 实例恢复；恢复后的全表数据摘要、结构及状态与基线一致。使用同一候选镜像完成隔离升级后，才执行本地业务库迁移。临时演练容器已移除。

真实迁移后仅新增 `avatar_url`、`join_time` 两列，字段类型、可空性、中文注释及排序规则通过检查；两列初始全部为 NULL。全部原有字段、默认值、注释、索引、约束、外键及业务表数据摘要保持一致。

| 核验项 | 迁移前 | 迁移后 |
| --- | --- | --- |
| 部门 | 940 | 940 |
| 人员 | 44 | 44 |
| 人员部门关系 | 58 | 58 |
| 门店配置 | 0 | 0 |
| 管理员白名单 | 1 | 1 |
| 数据版本 | 34 | 34 |
| 数据世代 | `6f4b7cfc749e4dadaee518b8a55835ed` | 不变 |
| 初始化 / 覆盖状态 | complete / unknown | 不变 |

## 验收范围与后续数据状态

此前完成前端 11 项、后端 97 项、真实隔离 MySQL 升降级 1 项验证；时间戳 0 修订后另行复验人员资料相关 9 项。生产构建、类型检查、版本检查及 Ant Design lint 通过；桌面与手机的浏览器验证使用虚构人员 API。

发布后在真实容器内以只读事务读取全部 44 名人员，验证资料序列化、所需字段及真实 user_id 映射，未输出人员资料。检查时真实头像和入职日期均未采集，不将迁移视作数据回填。

应用正常启动后，既有监听器自动产生 `listener:startup` 核对任务；最终检查时仍在 departments 阶段，未确认同步完成。此次未手动发起同步、初始化或清理，也未部署远端。真实管理员浏览器会话验收仍未完成；只读容器检查不替代登录验收。

## 证据与恢复

以下路径相对于实际部署目录：

- 备份与迁移证据：`.cache/migrations/local-0013-20261107-095719-fbd7c1/`，包括授权与脚本摘要、旧镜像/来源、加密备份、应用会话、恢复与演练快照、迁移前后元数据和全表摘要。
- 独立密钥：`.cache/backup-keys/local-0013-20261107-095719-fbd7c1.dpapi`；仅供原 Windows 用户解密使用，不公开分享。
- 制品：`.cache/artifacts/release-20261107-092950-a80aac3e/`。
- 发布与复核：`.cache/releases/release-20261107-092950-a80aac3e/`，包括标准发布记录、`profile-read-verification.json`、`final-state.json` 和 `background-jobs.json`。

旧镜像要求 schema 0012，不能仅切换旧镜像回退 0013。涉及降级或恢复业务库时须另行明确授权、停写并保护迁移后的新增数据，遵循 [0013 迁移手册](../../deploy/migrations/0013-employee-profile.md)。本轮没有执行 downgrade 或业务库恢复。
