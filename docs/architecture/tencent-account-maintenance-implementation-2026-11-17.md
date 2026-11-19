# 腾讯云账号维护、凭据轮换与在途隔离（T09）

2026-11-17，对应 [#24](https://github.com/mr-vilin/Evolution/issues/24)。在 T01 账号接入及 T02/T04 执行门槛上交付用户可用的账号维护，沿用父规格、CONTEXT、ADR0004/0006。仅执行授权的本机13306独立测试库写入；未调用真实腾讯云、迁移业务库或部署。

## 账号维护契约

`PATCH /admin/api/tencent/accounts/{account_id}` 使用 `tencent.account.update` 独立动作、当前管理员白名单会话、CSRF 与初始化 complete 门槛。请求必须携带正整数 `revision`，并提供至少一项非空的 alias、credential_ref 或 is_enabled；禁止额外字段及 UIN，账号不能改绑。响应继续沿用 data/meta、中文安全错误及 no-store。账号列表增加 revision，供页面按读取版本维护。

中文维护弹窗展示只读 UIN、别名、受控凭据选项与账号总开关。未选择轮换时不提交 credential_ref，改别名也不发验证请求。选择现有同一引用可以重新核验并递增安全修订，以便部署者更新注册表后显式建立新绑定资格。界面无密钥及 JSON 输入。并发冲突、验证期间成本能力变化或响应未知时保留输入并要求刷新核实，不静默套用新版本重放旧编辑；凭据错误显示字段级原因。辅助账单准备中使用独立提示，不能显示成完整费用采集成功。

| 修订 | 递增条件 | 用途 |
| --- | --- | --- |
| revision | 每次发生实际维护变化 | 账号普通乐观并发控制；不用秒级 update_time 代替 |
| credential_revision | 每次经过验证的凭据绑定，以及每次真实启用/停用切换 | 复用余额与成本的账号安全栅栏；别名编辑不递增 |

单次请求同时轮换和启停可递增两次安全修订，各自表达一个资格变化；普通并发修订仅递增一次。相同别名或相同开关不改变任一修订。安全修订保留数据库字段名以兼容已经建立的任务快照，不把可用秘密保存到快照。

## 事务外验证与提交门槛

1. 读取 complete、dataset_epoch、账号 UIN 与普通 revision，并记录该账号成本配置的标识、启用状态及 control_revision；提前拒绝过时维护版本。
2. 关闭读取事务，在受控注册表中解析一次不可变内存凭据。调用 DescribeAccountBalance 核对同一 UIN。成本当前启用时，使用同一个凭据对象检查 DescribeCostExplorerSummary 与当前月度零值核验采用的 DescribeBillSummaryByProduct。仅检查动作可用与响应基本契约，不完整分页、不保存账单或余额。
3. 成本主接口使用最近已到同步日的完整账月，费用账单/总费用/产品口径，首个最多100行页面。辅助动作同一账月；Ready=0 表示权限调用成功但账单准备中，与 TENCENT_PERMISSION_DENIED 区分。响应 meta.verification.auxiliary_readiness 只代表这次辅助接口的就绪观察，不证明完整成本数据已经可发布。
4. 短提交事务重读并锁定 complete/原 epoch、当前管理员资格及账号。重新匹配 revision；轮换再锁定成本能力并匹配原控制修订，即使成本经历停用后重新启用也不能绕过重新验证。任何失败均不替换旧绑定。全程不跨外部调用持有业务行锁。
5. 账号变化与 ChangeLog 同事务保存；其 after_data 包含服务端 request_id，关联实际入站及 UIN核验/权限检查的出站审计。失败调用通过独立 TencentApiCall 保留，记录稳定错误与校验后的上游 RequestId，不复制 Message、秘密、余额或整批费用。

官方文档核对：[成本分析参数](https://cloud.tencent.com/document/api/555/103991)明确产品维度 business、费用账单 BillType=1、FeeType=cost 及分页上限100；[产品汇总](https://cloud.tencent.com/document/api/555/35761)要求同月，Ready=0 表示准备中。公开文档和合成报文不能证明真实账号 CAM 或财务数据已验收。

## 启停与历史边界

停用后，新余额查询与成本受理/领取被当前账号门槛拒绝；已在途余额返回、成本心跳/出站/提交继续核对安全修订与账号资格。重新启用再次递增安全修订，不能让停用前的排队快照、余额响应或旧租约复活。失联恢复仍使用原 job/attempt 的真实事实与代次，不重绑旧任务；新资格按现有策略接收新工作。

别名维护只递增普通 revision，已受理余额和成本可继续。A 账号维护只改变 A，B 的账号与成本配置不变。单独关闭成本不关闭余额。账号停用保留费用和全部尝试历史，读取历史仍只要求当前管理员与初始化 complete；已成功提交费用不会仅因组织 epoch 改变而失效。

## 0017 迁移与失败恢复

`0017_tencent_maintenance` 下接 `0016_tencent_recovery`。新增 tencent_account.revision 为 INTEGER UNSIGNED NOT NULL DEFAULT 1，并有具体中文 COMMENT；历史账号回填1。仅更新 credential_revision 的中文含义备注，保留原 INTEGER、有符号、非空、默认1及既有安全修订值。保持 MySQL8.4、InnoDB、utf8mb4_general_ci、UIN的utf8mb4_bin与唯一键，不新增物理外键或改费用结构。

真实环境迁移需要额外授权。执行前逐环境核对实际结构、会话、版本和备份，静默全部账号维护与成本 worker；升级期间不要向旧实例投递新维护请求。只读预检：

```sql
SELECT DATABASE(), VERSION(), @@character_set_connection, @@collation_connection, @@time_zone, @@transaction_isolation;
SELECT version_num FROM alembic_version;
SHOW CREATE TABLE tencent_account;
SELECT COUNT(*) AS active_config_count FROM tencent_sync_config WHERE owner IS NOT NULL OR active_job_id IS NOT NULL;
SELECT COUNT(*) AS active_job_count FROM tencent_sync_job WHERE status IN ('pending','running','retry_wait');
SELECT id, credential_revision FROM tencent_account WHERE credential_revision < 1;
```

升级后执行现有 schema_check/database_ready，并查询 information_schema.COLUMNS 核实普通 revision 无符号、非空、默认1、中文备注，确认全部既有 UIN、别名、引用、安全修订与唯一键原样保留。MySQL DDL 非整轮事务；中途失败保留表与迁移证据，先核对实际列和 alembic_version 再恢复，不盲重跑 ADD COLUMN。

常规应用回退保留前向兼容列。确需降级时，另行授权、静默维护/worker、备份并保存并发修订证据；降级仅去掉普通 revision 并还原旧安全修订备注，保留安全修订值和财务历史。重新升级把普通 revision 回填1，因此所有旧页面必须关闭并重新读取账号，不能复用降级前表单。

## 验证

测试使用原始腾讯云响应模拟唯一出站边界，经完整管理端 HTTP、真实 TencentCostWorker 及独立 MySQL连接观察结果。覆盖轮换错配/权限不足保旧、辅助Ready=0、同一不可变凭据、验证期间能力/管理员/世代/版本变化、并发轮换单次发布、别名不取消在途、停用再启用隔离余额/队列/成本提交、重启回收保留UNKNOWN及迟到拒绝、A/B隔离、成本关闭仍查余额、CSRF与身份门槛及审计脱敏。迁移使用合成历史行实际降升核验回填、结构、中文备注与绑定保留。

前端测试覆盖固定UIN的别名维护、总开关、受控轮换/辅助未就绪和冲突后刷新；相邻账号/余额/成本页面回归及TypeScript/生产构建单独运行。Ant Design6.6.4 API查询及修改文件lint通过。版本仅补充Unreleased，不更改集成PR的0.3.0候选；实际业务登录、真实腾讯云权限/账单、业务环境迁移及部署仍未验收。

## 最终本地验证记录

- `tencent_t09_final_test` 从空库升级到0017，完整腾讯模块回归144项通过，包含本票35项维护行为及1项实际迁移回填/静默降升演练；实际目标MySQL8.4.11、127.0.0.1:13306，字符集/排序规则/UTC/RR及无活动worker保护由夹具核实。
- 账号、维护、余额与成本页面4文件12流程通过；辅助就绪字段最终命名后再次运行维护组件3流程、TypeScript检查及生产构建通过，生成112个资源。两处修改组件Ant Design lint均无问题。
- 所有验证均使用合成腾讯云传输和任务专用数据库；没有真实腾讯云请求、13307业务库读写、业务登录会话验收、业务迁移或部署。
