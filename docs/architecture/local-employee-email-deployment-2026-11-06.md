# 本地人员浏览与邮箱迁移记录（2026-11-06）

## 授权与目标

用户本轮明确授权“执行本地迁移与发布”，范围包括加密备份、隔离恢复演练、0011→0012 邮箱迁移、候选制品发布及浏览器验证。目标为本机 Docker Desktop 的 `organization-directory` Compose 项目，入口 `http://127.0.0.1:8000`。未发布远端环境，未清理、重新初始化或手动发起同步。

## 已完成的数据库迁移

- 执行器：`deploy/migrate_local_0012.py`，复用既有 DPAPI/Fernet 与容器 SQL 工具，固定来源 `0011_organization_browser` 和目标 `0012_employee_email`。实际调用显式传入已校验制品与 `--authorized-local-migration`；脚本授权参数不替代用户指令。
- 预检：MySQL 8.4.11，初始化完成，无活动任务。停写后再次核实空闲状态。
- 加密备份：`.cache/migrations/local-0012-20261106-091440-19d481/database.sql.fernet`；独立 DPAPI 密钥文件记录于同目录 `backup.json`。业务明文 SQL 未落盘。
- 隔离演练：使用原 MySQL 镜像、无网络/无监听进程、临时内存数据目录，恢复加密备份后比对全部原有表/列/索引/约束/外键及逐表业务数据摘要，全部一致；同一候选镜像执行 0012 后再次核对，仅新增预期邮箱列。演练容器已删除。
- 业务库执行后：schema `0012_employee_email`，仅新增可空 `employee.email VARCHAR(254) COLLATE utf8mb4_bin` 与准确中文注释；全部原有列、索引、外键和业务数据摘要保持。已有人员 email 全为 NULL，无回填。
- 数量保持：department 940（含虚拟根，页面有效部门 939）、employee 44、employee_department 57、store_profile 0、admin_allowlist 1。
- 世代 `6f4b7cfc749e4dadaee518b8a55835ed`、data_version 32、初始化 complete、coverage unknown 保持。
- 证据：上述迁移目录中的 before/database-before/database-after、metadata-before/after、data-digests-before/after、restored、rehearsal 和 result JSON。恢复到业务库的操作未执行，隔离恢复演练成功不等于真实灾难恢复已执行。

## 已完成的首轮发布

使用 `deploy/release.py deploy --artifact .cache/artifacts/release-20261106-081429-3a6f06a6` 发布已审查候选镜像。app/MCP 健康，77 个前端资源哈希、构建元信息、就绪/存活、未认证 API 边界均通过；实际 `verify` 再次通过。

首轮镜像 `sha256:8f6bdbd03e1f7ce012da80cffd12f81f2caeb9434ba7d29a0585d85611d3d4b1`。这是未提交工作区开发快照（dirty=true），不是正式发行或远端上线。

真实管理员浏览器验证：全公司默认点选；44 个当前成员触发仅直属，实际展示根直属 14 人，“全部成员”选项禁用；切换信息技术部后统计该范围 7 个有效部门/9 人，默认全部成员；搜索零结果时顶部统计保持。6 部门归属人员显示三行与 +3，气泡包含全部 6 条完整路径。邮箱/手机未采集时明确显示未知，未将空值冒充采集成功。

## 移动端后续验证

真实 390×844 验收发现统计区挤压人员列表可见空间，已将窄屏组织区改为自然页面滚动，并给人员卡片保留最低高度。修正版制品 `release-20261106-092747-d44ac27b` 已通过标准 `release.py build/deploy/verify` 发布。最终镜像 `sha256:24130373523d59873a55e58bda2b823d88d19e473d6dfb841ccd0b35f2fdaf62`，开发快照 dirty=true，schema 仍为 0012；该修复只涉及 CSS，不新增数据库迁移。

- 真实 390×844 窄屏下可自然滚动查阅 14 个根直属成员；不再被顶部统计区挤成无可见空间。临时视口已恢复。
- 桌面 1436×764 复核全公司统计、图标提示、八列表头与人员滚动区正常；默认全公司和大部门禁用规则已在真实管理员会话验证。
- 最终 verify：app/MCP healthy、镜像及构建元信息一致，首页/初始化/live/ready 为 200；未认证管理会话/初始化 API 为 401；77 个 JS/CSS 哈希通过。
- 实际应用 MySQL 会话为 utf8mb4/general_ci；迁移工具的 MySQL CLI 只读探针会话为 utf8mb4/0900_ai_ci，已单独记录，未用 CLI 默认值推定实际应用设置。email 列显式 utf8mb4_bin，经前后元数据比较确认。
- 最终快照业务数量仍为 940/44/57/0/1，初始化 complete；后台运行期间 data_version 从停写迁移时 32 变为 33，最终存在 1 个活动任务，因此不声称发布后数据静止或同步全部完成。邮箱已采集行数仍为 0；未手动发起同步。
- 最终证据目录：`.cache/releases/release-20261106-092747-d44ac27b/`，包含 final-inspection、verification、manifest、before/after、previous-images、candidate 及桌面/手机/多部门截图。迁移备份目录还包含落盘 DPAPI 密钥恢复验证结果。


## 验证边界与恢复

功能实现通过完整后端 1404 项、前端 55 项回归及类型、Ant Design、版本和生产构建检查；数据库真实备份恢复演练和本地管理员浏览器证据另行记录，不以合成测试替代。未验证真实飞书邮箱字段权限，未手动同步，因此已有邮箱仍为未采集。

0012 之后不能直接使用要求 0011 的旧镜像回退；保持停写并按 [0012 手册](../../deploy/migrations/0012-employee-email.md) 恢复匹配备份/镜像。后续同 schema 的 CSS 增量发布可使用标准发布回退目录。
