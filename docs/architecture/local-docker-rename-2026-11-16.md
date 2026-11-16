# 本地 Docker 项目改名记录（2026-11-16）

## 范围与结果

用户明确授权本地 Docker 改名。2026-11-16 15:02（北京时间）通过 `deploy/release.py rename-local --environment local` 完成切换，随后标准 `inspect`、`verify` 均通过。未连接、修改或发布线上测试与正式环境。

| 资源 | 改名前 | 改名后 |
| --- | --- | --- |
| Compose 项目 | organization-directory | evolution |
| 应用容器 | organization-directory-app-1 | evolution-app-1 |
| MCP 容器 | organization-directory-mcp-1 | evolution-mcp-1 |
| MySQL 容器 | organization-directory-mysql-1 | evolution-mysql-1 |
| 应用镜像仓库 | organization-directory-runtime | evolution-runtime |
| 镜像标签 | release-20261116-034142-fadb8915 | 同一标签，新增仓库别名 |
| MySQL 数据卷 | organization-directory_mysql-data | 同一个 external 数据卷，保留旧名 |

应用与 MCP 继续使用不可变镜像 `sha256:dae0502e0d2b263ccd89c2dcf834ec855c131f8652c827878ce3852d353d39c6`，MySQL 继续使用 `sha256:6ea90827b1100f8f2ae306a539f86d2c264a26ed435a2a9f75551dd5c3aeb242`。没有重新构建或发布工作区中尚未部署的源码。

## 核验结果

- 本地 MCP stdio 启动脚本已使用当前用户原运行环境完成初始化并列出 15 个工具，只读验证未调用业务写入；SDK 默认裁剪环境时 Docker Compose 插件不可见，恢复同用户环境后通过。
- app、mcp、mysql 均为 healthy；本机 `http://127.0.0.1:8000` 可用。
- MySQL 实测 8.4.11，schema 为 `0013_employee_profile`；应用连接和服务端均为 `utf8mb4` / `utf8mb4_general_ci`。
- 停写后与新 MySQL 启动后、worker 启动前的快照一致：部门 940、人员 44、人员部门关系 58、门店资料 0、管理员白名单 1；dataset_epoch、data_version、初始化和覆盖状态、流程阶段相同。
- 验证后复查仍为上述数量，data_version 为 37，初始化 complete，覆盖 unknown，活动任务 0。没有执行 migrate、初始化、清理或手动同步；启动原应用后仍按原有配置运行监听与后台进程。
- 首页、初始化页、live/ready 为 200，未登录的会话与初始化 API 为 401；92 个 JS/CSS 资源逐项哈希一致，宿主机发布端口的构建信息一致。
- 构建信息仍为版本 0.1.0、提交 `0cb0189b7ab685733ea6579959af973ef30e3e13`、dirty=true、构建时间 `2026-11-16T03:42:25.415Z`。这次只切换名称，没有升级产品版本。
- 旧项目容器（含两个已退出的历史迁移容器）和无端点网络已在验收后移除，不删除任何数据卷。没有创建或运行新的 migrate 容器。
- 19 项发布及改名单元测试通过，包含本地目标保护、原卷要求、内容变化阻断、停止的无挂载历史容器识别、成功切换及故障回退。真实环境已另行验证，测试结果不替代运行证据。

## 最终复核发现的配置差异（用户已确认）

改名前的实际 server_collation 为 `utf8mb4_0900_as_cs`；仓库原 Compose 配置为 `utf8mb4_general_ci`，新容器启动后实际采用 general_ci。应用连接排序规则始终为 general_ci，库默认仍为 general_ci，表默认只读核实为 22 张 general_ci、1 张 0900_as_cs。本次没有执行 ALTER 或其他表结构转换；服务端默认变化不等于修改现有字段排序规则。

改名流程原来比较 schema、状态和业务数量，最终对全字段快照检查才发现这个差异。已补充数据库运行元数据变化的阻断测试，后续发现类似变化会在 worker 启动前停止。用户于 2026-11-16 明确选择“保留仓库规定的 general_ci 默认值”。因此保留当前服务端 `utf8mb4_general_ci`，与 Compose 和应用连接配置一致，无需额外重启或执行数据库变更。确认后再次运行标准 inspect 与 verify 均通过：schema、data_version、业务数量保持不变，app/MCP 健康，92 个前端资源校验一致。本次改名及这项已确认的服务端默认值调整已完成收尾。

## 证据与恢复边界

证据目录为 `.cache/releases/rename-20261116-070141-13f2a6e2/`，包含原配置字节备份、原容器与镜像清单、源码状态、before/stopped/before-workers/after 快照、资源验证及结构化 rename.json。运行证据不应公开分享；不保存或打印完整环境变量和连接凭据。

流程在验收失败时停止新服务、恢复配置与原容器并核验；这次成功后才清理旧容器。成功后的人工反向改名需要按证据重新创建原项目容器，并在停写状态下核实同一卷及原镜像，绝不能同时启动两个挂载同一数据卷的 MySQL。不要把 rename-id 传给普通应用版本 rollback；该命令处理的是原 release-id。

同一卷复用及配置/镜像回退不等于数据库备份或数据库回滚。这次不修改数据库结构，不复制或迁移卷内容；后续真实数据恢复与迁移仍须独立授权、备份及恢复演练。

## 保留名称与日常入口

- 数据库卷旧名用于固定已有业务数据；不要为追求名称统一而删除或替换。
- 历史镜像标签、制品及 BuildKit 缓存保留旧名，供历史核验和缓存复用。
- MCP 客户端注册名 organization-directory 与 Docker 项目名无关；本地脚本自动读取新 Compose 配置。
- 远端部署路径、项目名、镜像以及独立测试项目均未改变；本轮没有重新核实远端状态。
- 日常发布继续用 release.py；镜像覆盖文件 `.cache/deployment-image.json` 是必要配置，不绕过它直接 up --build。代码修改并验证后通知用户，只有用户明确要求部署时才启动发布。
