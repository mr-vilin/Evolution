# 人员字段同步检查与修复

## 字段来源与检查结论

2026-11-08 检查初始化 `InitializationCollector`、每日定时／手动全量／事件 `Collector`、共用 `Publisher`、Employee ORM 及详情读取链路。用户确认邮箱 `email` 为工作邮箱；手机号、直属上级、职务和自定义字段继续沿用既有来源。

| 页面字段 | 飞书来源 | 入库字段及结论 |
| --- | --- | --- |
| 用户 ID、姓名、工号 | user_id、name、employee_no | 已接入；user_id 同时保存稳定主键及 feishu_user_id |
| 头像 | avatar 内 HTTPS 图片地址 | avatar_url 已接入；补齐初始化预检报告标题 |
| 账号状态 | status 的五个布尔标志 | 五个原始标志及 field_readability 已接入，不从缺省推断状态 |
| 手机号 | mobile | mobile 已接入；保留缺省／不可读／可读空值区别 |
| 工作邮箱 | email | email 已接入，沿用用户确认来源，不自动替换或拼接其他邮箱 |
| 直属上级 | leader_user_id | 已接入；展示名称、头像通过本地人员引用解析 |
| 部门、主部门 | department_ids、orders.is_primary_dept | 关系表及 primary_department_id 已接入 |
| 人员类型 | employee_type 的 code | **修复**：普通同步原先只解析对象形式或额外 employee_type_id，遗漏飞书实际数字值，会清空初始化结果；现按 code 及已保存对照写入 employee_type_id/name |
| 入职日期 | join_time（Unix 秒） | join_time 已接入；按北京时间展示日期，补齐初始化预检报告标题 |
| 职务 | job_title | 已接入 |
| 门店属性 | 当前配置的同名 TEXT 自定义字段 | value.text 写入 store_attribute_name，id 留空；兼容既有单选形式 |
| 权限角色 | 当前配置的同名 ENUMERATION 自定义字段 | option_id/option_value 写入 permission_role_id/name；不等同本系统管理员权限 |

截图人员的应用身份只读样本中：employee_type 返回整数 1，而数据库类型为空，直接证明普通同步解析遗漏；job_title 返回空字符串；mobile、email、enterprise_email、leader_user_id、custom_attrs 未返回。仅凭接口省略不能断言未填写或缺少权限，本次不伪造数据、不更换字段、不修改飞书权限。

## 配置与兼容

管理设置增加“人员类型”，支持逐行新增、修改、删除 code 与显示名称。默认读取当前已保存的配置：1 正式、2 实习、3 外包、4 劳务、5 顾问、6 加盟、7 客服、8 盟友；这是一份环境配置快照，不在前端硬编码，也不覆盖现有设置。

复用 `/admin/api/settings/custom-attrs`，只提交 employee_type_options，保留权限角色和门店属性映射。前后端校验空白值、重复 code 和 191／255 字符容量。初始化与日常维护使用一致的配置校验。保存不立即批量改写人员数据；worker 在下次任务／事件读取最新配置并入库，页面明确提示该生效时机。

普通同步兼容数字、字符串 code 及原有对象／分离字段格式，以配置名称为准。未配置的 code 保留标识、名称为空并标为待核实；格式错误不会被当作合法空值覆盖已有人员。初始化仍严格拒绝未配置的已填写类型。

初始化预检报告曾因头像／入职日期加入可读性数据却未加入标题表而抛出 KeyError；补齐标题和字段要求后，允许省略并正确记录可读性。

## 数据与验收边界

本地业务库只读实测为 MySQL 8.4.11、schema `0013_employee_profile`，应用连接 `utf8mb4 / utf8mb4_general_ci`、时区 `+00:00`。本次不新增列、迁移或索引，不需要业务库迁移。

回归覆盖初始化预检及完整发布、定时任务触发后持久化、配置修改后重新调度、事件同步、详情序列化、未知／空／非法类型和配置失败保留。真实 MySQL 验收使用独立临时 `organization_test` 数据库及虚构飞书样本，不替代真实企业全量同步。

发布使用 `deploy/release.py`，仅本地 Docker；若存在活动同步任务，须等待其自然结束，不能绕过发布门禁。本次代码修复和配置页完成不代表历史人员已经回填；回填需要修复版本运行后的正常同步。

## 验证记录

- 字段、初始化、队列及同步相关测试 118 项通过；独立 MySQL 8.4 字段全链路 1 项通过，临时容器已移除。
- 扩展非集成回归首次在仓库根目录运行：1371 项通过、16 项跳过、6 项因 migrations 模块导入路径失败。切换至 backend 目录对三个受影响测试文件复验，24 项全部通过，没有修改迁移代码。
- 前端配置表单与初始化表单 15 项通过；TypeScript、Ant Design lint、版本校验及本机生产构建通过。
- Edge 隔离浏览器验证桌面 1440×1080 和手机 390×844：当前八项配置回显、新增、编辑、删除、保存及重复 code 拦截通过，无页面异常或横向溢出。API 全部使用虚构响应，真实 API 写入为零，不代表真实管理员会话验收。截图在 `.cache/employee-sync-browser/desktop.png` 和 `mobile.png`。

## 本地发布结果

2026-11-08 已通过标准 `deploy/release.py` 发布本地 Docker，制品为 `release-20261108-055432-bc09acf3`，源码提交 `4bc05b89c867ac00021be1dc86e64557e4c4be96`，包含本轮未提交改动（dirty=true）。镜像 ID 为 `sha256:da571901b51da7dcfa1890fb3ba21ef94e929070516cb7f030675994b87e9b99`，构建时间为北京时间 14:01:33。

- app、MCP 健康；首页、初始化页、live/ready、未登录接口边界和 73 个 JS/CSS 资源校验通过。上述隔离浏览器交互验证已对新 Docker 页面再次执行并通过。
- 新容器使用真实飞书只读返回和现有配置验证：截图人员的数字类型 `1` 正确解析为 ID `1`、名称“正式”，未执行人员写入。
- 发布前后 schema 均为 `0013_employee_profile`、data_version 均为 35、活动任务均为 0；部门 940、人员 44、部门关系 58、门店 0、管理员白名单 1，数据世代未变化。未执行迁移、初始化或手动同步；历史类型值仍等待后续正常同步更新。
- 发布证据及旧镜像回退点位于 `.cache/releases/release-20261108-055432-bc09acf3/`。未部署远端测试或正式环境。

构建时遇到 npm 网络中断及可选原生依赖下载遗漏。Docker 安装层增加下载重试，并在缓存该层前检查 Utoopack 原生模块可加载；依赖版本和基础镜像不变。修改后 Docker 构建成功，发布脚本 12 项回归通过。
