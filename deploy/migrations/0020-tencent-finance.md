# 本地腾讯财务迁移：0013 → 0020

## 目标与执行边界

此入口只用于实际本地 Evolution 部署目录、MySQL 8.4、`organization` 库，要求源版本为 `0013_employee_profile`、初始化完成且无活动同步任务。执行前必须获得当次本地数据库迁移授权；线上测试与正式环境不适用。

迁移按制品中的 Alembic 链依次执行 0014–0020，新建七张腾讯账号、请求审计、同步配置、任务、尝试、费用期间与产品明细表，并补齐这些新表的维护、恢复、日周月调度及历史检查点字段。现有组织业务表、初始化世代和业务数据保持原样，不触发账号登记或成本采集。

## 标准入口与验证

使用已通过 CI 的既有制品，不重建镜像。`deploy/migrate_local_0020.py` 校验制品压缩包、源码清单与镜像摘要，沿用发布锁、现有连接和 Compose，停 app/MCP 写入后：

1. 保存原镜像、部署来源、版本、全部元数据及原有业务表全部列的数据摘要（包括头像和入职时间）。
2. 全库备份仅在内存处理明文，落盘为 Fernet 密文；密钥通过当前 Windows 用户 DPAPI 独立保存。
3. 从落盘密文及独立密钥恢复到无外网、无宿主端口的临时 MySQL，核验恢复后的原结构和全表数据摘要。
4. 在恢复库中用同一候选镜像升级至 0020；要求只新增指定七表，原有元数据和数据摘要不变、新表为空，真实结构与镜像模型一致。
5. 只有演练成功才迁移本地业务库，并重复上述结构、数据及真实连接检查。成功后服务保持停写，交给标准发布入口启动同一制品。

```powershell
# 当次已获得授权，artifact 替换为已核验的真实制品目录。
backend/.venv/Scripts/python.exe deploy/migrate_local_0020.py --artifact .cache/artifacts/<release-id> --authorized-local-migration
# 仅在上一步退出码为 0 后继续；不重新构建。
backend/.venv/Scripts/python.exe deploy/release.py deploy --environment local --artifact .cache/artifacts/<release-id>
backend/.venv/Scripts/python.exe deploy/release.py verify --environment local
```

执行证据位于 `.cache/migrations/local-0020-*/`，密钥另存 `.cache/backup-keys/`。这些目录包含受保护的运行证据，不提交版本库，不公开分享。不要删除原数据库卷或把临时恢复库当成业务库。

## 失败恢复

MySQL DDL 不保证整轮回滚。任一步失败时保留服务停写和现场证据，先核对实际结构及 `alembic_version`，不能盲重跑或仅修改版本号。演练失败不会执行业务库迁移；业务迁移中途失败需根据实际已执行语句选择完成剩余迁移或恢复已演练的加密备份。

0013 旧镜像严格要求旧 schema。业务库升级到 0020 后，只回退旧镜像不能恢复服务。需要回退时，在授权范围内保存迁移后新增数据，停写、恢复备份并核验原版本、结构与摘要，再启动保存的旧镜像。不得把删除腾讯表或连续 downgrade 当成无损回退。

## 本次执行结果

后续执行仍须核实实际源版本，不可在已升级环境重复运行此脚本。业务库的实际迁移与发布证据留存在受控环境中，不随源码公开。
