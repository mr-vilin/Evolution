# 组织同步表重命名

MySQL 8.4，从 0025_sync_schema 升至 0026_org_table_names。

| 原表 | 新表 |
| --- | --- |
| dataset_state | org_dataset_state |
| pending_fact | org_pending_fact |
| sync_job | org_sync_job |
| sync_job_detail | org_sync_job_detail |
| sync_staging | org_sync_staging |
| worker_lease | org_worker_lease |

通过 RENAME TABLE 原地更名，保留数据、字段、注释、索引、自增状态及既有外键。同步任务明细和暂存表的外键指向 org_sync_job。腾讯云模块继续通过 ORM 使用 org_dataset_state 的初始化状态与数据集世代。评测案例和审计对象类型沿用既有业务标识。

执行前按发布流程停止写入、核对版本及六对表名无冲突，验证备份可恢复。逐表更名失败时保持停写，核对实际表名及外键，重试会跳过已完成的表。执行后使用 schema_check 验证完整结构、记录数量与外键，并验证组织同步和腾讯云初始化检查。回退按反向顺序恢复原表名和配套应用版本。
