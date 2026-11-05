# 本地组织工作台迁移与发布记录

日期：2026-11-05（北京时间）。用户当次明确授权“本地业务库加密备份、隔离恢复演练、0010→0011 迁移、Docker 发布及浏览器验收”。目标仅为本机 Docker Desktop 的 `organization-directory`；未操作线上测试或正式环境。

## 执行结果

本地业务库已升级为 `0011_organization_browser`，标准 Docker 发布成功，app、MCP、MySQL 均健康。浏览器验收尚未完成：两次连接既有 Chrome 标签页均在 `Emulation.setFocusEmulationEnabled` 超时，随后 Computer Use 因无法可靠确定当前浏览器 URL 而停止本轮控制。未继续界面输入，未绕过登录或安全校验。真实容器的只读服务检查不能替代已登录浏览器验收。

## 备份、隔离演练与迁移

- 执行前：MySQL 8.4.11，schema `0010_initialization_wizard`，活动任务 0；初始化 complete、coverage unknown。940 部门、44 人、55 条人员部门关系、0 门店资料、1 管理员。
- 停止 app/MCP 后再次核实空闲，保存原应用镜像、部署配置、来源及完整实际结构/连接会话快照。数据库与连接沿用 utf8mb4/general_ci、UTC、REPEATABLE READ；稳定 ID 保留 utf8mb4_bin。
- 数据库一致性 mysqldump 仅在内存处理，以 Fernet 加密落盘；运行 `.env` 配置亦单独加密。密钥由当前 Windows 用户 DPAPI 保护，独立保存；通过从 DPAPI 文件恢复密钥、解密落盘备份，验证密文可恢复。无明文数据库备份或配置副本落盘。
- 证据目录：`.cache/migrations/local-0011-20261105-092530/`。密文为 `database.sql.fernet`、`configuration.fernet`；密钥路径为 `.cache/backup-keys/local-0011-20261105-092530.dpapi`。不得将密钥、备份或个人资料上传 Git。
- 使用业务实例相同 MySQL 镜像，创建 `--network none`、tmpfs 数据盘的独立演练容器，不公开端口。恢复真实密文备份后，逐项核对全部表元数据及所有原列的数据摘要，与停写业务库一致。
- 在隔离库使用已审查应用镜像运行 `0010→0011`：原列、默认值、中文注释、字符集、索引和约束保留；新增结构与 ORM 校验无差异，ready 通过；同父级顺序按稳定 ID 初始化，历史人员新增事实全部保持 NULL。
- 再执行隔离 `0011→0010` 降级演练，确认原结构、全部原列数据、世代和状态完全恢复。隔离容器随后删除，tmpfs 不留业务副本。
- 演练成功且业务库数据摘要未变化后，才对本地业务库执行 `alembic upgrade 0011_organization_browser`。执行后结构与演练库一致，ready 和完整 schema 检查通过，所有原列数据摘要不变。
- 迁移本身保持世代 `6f4b7cfc749e4dadaee518b8a55835ed`、数据版本 3、初始化 complete / coverage unknown 及全部业务数量；未清理、初始化或手动申请同步。

## 标准 Docker 发布与运行验证

- 使用 `deploy/release.py deploy --artifact .cache/artifacts/release-20261105-090216-947f0ea0` 发布，脚本返回 `deployed`；随后重新运行相同标准验证逻辑并保存结果。
- 镜像：`sha256:0c7cbdd096837ee185a42efd66c9e7faf9f8a53133050cad821992481b3747bf`。app/MCP 使用同一镜像，MySQL 容器及原数据卷保留。
- 产品 0.1.0，开发快照 `dirty=true`；制品元信息提交 `bd079ed1906bcda04df03c62b599682c44b27ffe`，构建时间 `2026-11-05T09:04:45.799Z`。Issue #11 实现提交为 `d1fcfe4dcd6157e31961e6d7fd01e5d4bfc6581a`；镜像是提交前已测试快照，运行代码与实现提交一致，仅测试选择器存在快照差异，详见[实现交付记录](organization-browser-2026-11-05.md)。不得称为干净正式发行。
- 标准验证通过：首页、初始化页、live/ready、宿主机发布端口、未登录会话/初始化 API 的 401 边界，以及 76 个 JS/CSS 内容摘要和前后端构建信息一致。
- 发布回退证据：`.cache/releases/release-20261105-090216-947f0ea0/`；迁移前的真正 0010 镜像及数据库回退点以迁移证据目录为准。
- 重启触发既有监听器的 `listener:startup` 自动 reconcile。发布即时快照版本 4、活动任务 1；后续只读检查版本 5，最近任务中有 succeeded/published 和 running/departments。未修改该既有机制，未宣称同步全部完成。发布后变化应与迁移数据保留验证分开理解。

## 真实数据只读功能检查

在已发布 app 容器内调用现有 OrganizationService，不修改数据，不创建测试身份或会话：

- 一级读取返回 23 个部门；完整根选择 939 个实际有效部门，清空后 0。
- 含下级部门的四步循环数量为 `1→16→15→0`；按需读取下级、按真实部门名称搜索并返回命中均通过。
- 人员首批 20 人，总数 44，unknown 筛选总数 44，返回可读性和账号原始事实字段。未触发采集以填充未知字段。
- 当前 schema 校验无差异；业务数量仍为 940 部门、44 人、55 条关系、0 门店资料；初始化 complete、coverage unknown。
- 原始安全检查结果为 `published-verification.json` 与 `service-read-verification.json`，只包含元数据、数量及任务状态，不含人员资料。

## 恢复与剩余验收

跨 schema 回退不能仅执行旧应用镜像 rollback：旧镜像要求 0010。发生故障时先停写，保存新现状；通过当前 Windows 用户 DPAPI 解开独立密钥，在内存解密备份并按已审查恢复流程处理数据库及原镜像，涉及真实恢复时遵循项目世代、会话及凭据重置规则。隔离降级演练不代表已对业务库执行降级。

待浏览器控制可用后，使用现有合法登录会话核验首次折叠、展开、搜索清空、勾选、人员滚动/筛选、同级排序持久化和批量保存。排序及门店写入本轮尚未通过真实浏览器验证；不能把先前自动测试或本轮健康检查记为完整业务验收通过。
