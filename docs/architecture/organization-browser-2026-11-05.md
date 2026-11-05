# 组织工作台实现与迁移交付

日期：2026-11-05（北京时间）。依据：[Issue #11](https://github.com/mr-vilin/OrganizationalStructure/issues/11) 与[规格](../ui/organization-tree-spec-2026-11-05.md)。用户本次显式调用 `implement` 授权开始实现；原规格中的 Q12 待确认是发布规格时的历史状态，不再阻止本轮实现。

## 实现契约

管理员组织页采用 `/admin/api/organization/` 专用接口：

| 接口 | 行为 |
| --- | --- |
| GET `departments` | 指定父级的直接下级；初次 `parent_id=0`，返回 `has_children` 与本地顺序；游标分页 |
| GET `search` | 完整同步数据的部门名称片段搜索；返回祖先及 `matched_ids` |
| GET `employees` | 具体部门的当前有效成员，直属/所有下级，20 人上限、去重总数、绑定全部条件的游标 |
| POST `selection` | 按显式 ID 集合解析有效目标、四步切换、下级完整性、准确计数；可请求目标详情 |
| POST `order` | 移动部门到同父级锚点之前/之后；锁定数据版本，服务端读取完整同组顺序 |
| POST `stores` | 组织页整批直接保存；无 500 部门限制，世代/版本、有效性、字段、编码、审计及投影同事务校验 |

树、搜索、人员、选择读取和写入绑定 `dataset_epoch` / `data_version`。浏览器分别维护点选、展开和实际选择；冲突时保留显式 ID，不重新应用旧的“全选”意图。批量草稿冻结原目标和版本，用户点击“重新核对目标”后移除失效目标、保留其余草稿，并再次手动保存。其他门店入口及 Agent/MCP 协议保持原约定。

人员账号五个标志各自可为 NULL；手机号及标志的 `field_readability` 区分 `readable`、`not_collected`、`unreadable`。合法空手机号不等于未知。账号状态筛选直接读取原始标志，不设互斥优先级；未知表示本页需要的五个标志至少一项未知。

## 数据库变更及规范差异

迁移：`backend/migrations/versions/0011_organization_browser.py`，基线 `0010_initialization_wizard`。ORM 与 Alembic 同步维护；新安装使用完整 Alembic 链，SQLite 仅为隔离单元测试创建 ORM 表，不作为生产建表入口。

- `department.sort_order`：MySQL `INT UNSIGNED NOT NULL DEFAULT 0`，既有同父级按二进制稳定 ID 初始化；新增/移入追加，同 ID 同父级恢复保序。
- `idx_department_order(parent_id,sort_order,id)`：用于同父级顺序读取；保留既有外键及其 `parent_id` 索引。
- `employee.mobile`：`VARCHAR(128) utf8mb4_bin NULL`；五个账号标志为可缺省 Boolean；`field_readability` 为可空 JSON。历史记录不填充虚假事实。
- 每个新增字段均有中文注释。沿用 MySQL 8.4、InnoDB、表级 `utf8mb4_general_ci`、稳定 ID 的 `utf8mb4_bin`，不转换既有字符集、字段或约束。
- 本项目保留已存在的外键、稳定字符串 ID 和 SQLAlchemy Boolean 映射，与通用数据库 Skill 的默认 INT 主键、禁外键、布尔 unsigned 建议存在差异；本次不扩大为历史结构改造。员工表新增列超过通用 30 列审查阈值，是本次明确要求的七项采集事实及可读性分组，按每页 20 人读取，未引入额外基础设施。
- 规格明确要求名称/姓名任意片段匹配，使用 MySQL 原生 LIKE 且转义通配符；这是对通用全模糊限制的任务内例外，未改其他页面查询规则。执行计划和延迟须按实际规模记录。

## 本地迁移的执行前检查

业务库执行需要用户另行授权；实现和隔离测试不构成该授权。线上测试与正式环境本轮未接触，不推断其结构。

1. 运行 `backend/.venv/Scripts/python.exe deploy/release.py inspect`，确认目标是本地、当前版本 `0010_initialization_wizard`、没有 queued/running 任务或 checking/running 初始化。确认源码制品及当前 app/MCP 不可变镜像回退点。
2. 使用当前业务应用的 `create_mysql_engine` / `schema_snapshot` 只读核实版本、全部原字段/默认值/注释/索引/约束及会话；应为 MySQL 8.4、UTC、REPEATABLE READ、utf8mb4/general_ci，稳定 ID binary。检查同父级 ID 顺序及现有业务数量；不输出个人资料或凭据。
3. 停止 app/MCP 写入后复核空闲。对业务库做完整一致性加密备份，密钥单独以当前用户 DPAPI 保存；备份不写入 Git。保留结构快照、业务数量、世代/版本、配置与镜像回退信息。
4. 将备份恢复到独立隔离 MySQL 8.4 实例，对照结构和数量；对恢复库演练 `0010 → 0011`、结构校验及业务读取，再验证降级或整库恢复。演练通过后才执行目标业务库迁移。
5. 迁移只使用已审查制品内的 `python -m alembic upgrade 0011_organization_browser`；具体连接由原 Compose 提供，命令行不携带业务库凭据。不得借迁移发起清理、初始化或同步。

## 执行后验证与失败恢复

1. 验证 Alembic head、`app.persistence.schema_check.check_schema` 无差异；所有原字段及约束保留，原 `parent_id` 索引保留；新增字段中文注释、NULL 事实、顺序初始化准确。
2. 比较业务数量、世代/版本和初始化状态与执行前一致。本迁移不触碰业务状态或发起数据采集。运行本制品的 ready 预检。
3. 统一使用 `deploy/release.py deploy --artifact <已校验制品目录>` 切换本地 app/MCP，再 `verify`。真实登录后串联首次树、展开、搜索、当前成员、四步勾选、排序刷新与批量保存；业务验收应使用已授权的目标，不能把健康检查当作业务验收。
4. MySQL DDL 会隐式提交；中途失败立即停写并检查真实字段/索引，不能假定事务自动恢复，也不能盲目重跑全部脚本。按前快照恢复部分结构，或从已演练的加密备份恢复原库及原镜像。新数据不得在恢复中静默丢弃。
5. `alembic downgrade 0010_initialization_wizard` 会删除新增事实与本地顺序，须事先备份并单独授权；正常应用回退优先保留兼容新增列。`release.py` 的应用镜像回退不等于数据库恢复，跨 schema 时禁止绕过其保护。

## 验证事实与边界

- 本地业务实例只读核实：MySQL 8.4.11、`0010_initialization_wizard`、940 部门、44 人、55 条部门关系；已初始化、无活动任务。本轮尚未执行业务库迁移或业务同步。
- 隔离 MySQL 8.4：已验证 501 部门完整选择及一次保存、属性/审计/投影三个失败阶段全部回滚、世代隔离、同组并发旧版本拒绝，以及迁移升级/降级、旧字段与约束保留。
- 飞书应用身份只读样本：一名用户的五个账号标志均返回布尔值；`mobile_visible=true` 但 `mobile` 被省略。只能证明该样本账号标志可读，手机号应显示“未采集/未知”，不能据此断言手机号为空、没有权限或全员可读。未触发同步、未持久化样本个人资料。
- 前端 Testing Library 使用合成 HTTP 响应。真实本地容器浏览器验收须在业务库迁移获授权并发布后进行。

## 两轴审查与处置

- Standards：发现服务端字段错误未定位到部门行、晚到的详情响应可能覆盖新选择；现已保留 `error.fields` 并映射到对应行，详情仅返回冻结基线，不回写全局选择。复查无剩余阻断项。
- Spec：发现异步表单校验期间存在重复触发窗口；保存锁前移到校验之前，校验失败释放。复查未发现其他有充分证据的缺失、错误行为或范围扩张。
- 补充行为回归覆盖公共请求错误字段保留、批量重复保存防护与编码错误行定位；原有批量版本冲突测试继续验证草稿及显式目标保留。
- 当前业务规模的只读 `EXPLAIN ANALYZE` 样本：部门 940 行全扫描约 8.467 ms，人员 44 行全扫描约 1.639 ms。这是当前规模单次测量，不代表大规模性能结论。

## 最终检查及本地制品

- 后端全量：从 `backend/` 运行 `pytest tests --require-mysql -q -p no:cacheprovider`，1,395 项通过（含真实隔离 MySQL）。历史 0009 迁移测试仍逐表验证原结构和会话数据保留；就绪检查改为明确拒绝旧 schema，不再假设旧 schema 与当前 head 仅有版本号差异。
- 前端全量：18 个测试文件、52 项全部通过；包含受控树/搜索/选择、三批人员续载与旧响应隔离、批量冲突草稿保留、重复提交防护及字段错误定位。测试 DOM 对样式表和伪元素的提示不影响通过结果。
- 发布工具：`python -m unittest deploy.tests.test_release -v`，12 项通过。产品版本校验通过（0.1.0，未自动递增）。前端 TypeScript 检查及生产构建通过；三个修改组件的 Ant Design CLI 检查均为 0 issues。
- 标准 `deploy/release.py build` 已生成 `.cache/artifacts/release-20261105-090216-947f0ea0/`；制品源提交 `bd079ed1906bcda04df03c62b599682c44b27ffe`，`dirty=true`，包含本轮实现快照和逐文件摘要，不是干净正式发行。制品校验通过，共 278 个源文件，schema 为 `0011_organization_browser`。
- 镜像 ID：`sha256:0c7cbdd096837ee185a42efd66c9e7faf9f8a53133050cad821992481b3747bf`；压缩包 SHA-256：`c1680c3e4185f352ae77be0dd5c9f2688e33292873d7f1e82cf1df68fd055f3f`。与最终工作区逐文件复核，唯一差异是新增前端测试的选择器修正；运行代码完全一致。
- 尚未执行本地业务库的加密备份、恢复演练、`0010 → 0011` 迁移或应用切换。需按仓库数据库/部署规则另行授权后继续；不触发初始化、清理或同步。未接触远端环境。
