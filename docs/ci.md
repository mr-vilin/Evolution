# 自动测试与 GitHub Actions 费用

## 检查入口

`.github/workflows/versioning.yml` 在 PR 创建或更新、推送 main、推送 `v*` 标签时运行三项独立检查：

| 检查 | 范围 | 超时 |
| --- | --- | --- |
| 后端非集成回归 | `backend/tests` 中除 `integration` 外的测试，以及 `deploy/tests` | 15 分钟 |
| MySQL 8.4 集成回归 | `integration` 全部测试及 `evaluation` 中需要真实数据库的用例 | 30 分钟 |
| 版本与前端构建 | 版本校验、版本工具测试、前端测试与构建；标签构建另核验镜像元信息 | 30 分钟 |

前端构建已包含类型检查。后端原来仅运行的两个测试文件已包含在完整非集成回归中，不再重复执行。非集成检查中的 Evaluation 数据库用例允许跳过，它们会在 MySQL 检查中实际执行。

更新同一 PR 会取消上一轮尚未完成的检查；main 和发行标签的运行不主动取消。检查只需仓库读取权限，不使用业务环境密钥，不发布应用。

## 临时 MySQL 的隔离与复用

MySQL 检查复用 `deploy/compose.mysql-test.yaml`，以独立 Compose 项目名 `evolution-backend-ci` 启动 MySQL 8.4；端口是 `127.0.0.1:13306`，数据目录使用 tmpfs。这里不使用根目录另一个测试 Compose，也不连接业务实例。

`backend/scripts/run_ci_mysql.py` 从该测试 Compose 读取本地测试凭据，仅在内存与测试子进程环境中传递连接。它不接收外部业务库 URL，并依次执行：

1. 核对镜像、端口及 tmpfs 声明，通过真实连接检查 MySQL 8.4、`utf8mb4`、`utf8mb4_general_ci`、UTC 和 REPEATABLE READ。
2. 显式创建 `tencent_ci_test` 专库；已有同名库时失败，不删除或清空旧库。
3. 对这个新库执行 `alembic upgrade head`，核验实际结构和库字符集、排序规则。
4. 给测试子进程设置专库连接及迁移演练连接，运行 `pytest tests/integration tests/evaluation --require-mysql -q -rs`。迁移用例沿用现有随机 `_test` 库夹具；出站腾讯云、飞书请求沿用测试替身，不要求真实云凭据。

缺少 MySQL、版本或会话设置不符、迁移失败、测试失败都会使 job 失败。测试按顺序执行，避免共享夹具并发污染。失败时输出有限的 MySQL 日志，结束时通过 `always()` 清理临时容器；不上传测试报告附件。即使运行器中断或强制取消导致清理步骤没有机会执行，GitHub 临时运行器销毁后也不会保留数据库。

本地复用命令（从仓库根目录执行；先激活已安装锁定依赖的 Python 环境）：

```powershell
$env:PYTHONUTF8 = '1'
docker compose -p evolution-backend-ci -f deploy/compose.mysql-test.yaml up -d --wait --wait-timeout 180
if ($LASTEXITCODE -ne 0) { throw '临时 MySQL 启动失败，停止测试' }
try {
    python backend/scripts/run_ci_mysql.py
    if ($LASTEXITCODE -ne 0) { throw 'MySQL 回归失败' }
} finally {
    docker compose -p evolution-backend-ci -f deploy/compose.mysql-test.yaml down --volumes
}
```

13306 若已被其他服务占用，应停止本次启动并核对占用，不停止或清理其他项目。普通测试从 `backend` 执行：

```powershell
python -m pytest tests ../deploy/tests --ignore=tests/integration -q -rs
```

## 费用依据与适用边界

2026-11-18 已通过 GitHub API 确认 `mr-vilin/Evolution` 为公开仓库。本工作流全部使用 GitHub 标准 `ubuntu-latest` 运行器，按当日官方规则，这类公开仓库的运行器计算免费。MySQL 是运行器上的临时 Docker 容器，不是单独购买的云数据库。

- [GitHub Actions 计费说明](https://docs.github.com/en/billing/concepts/product-billing/github-actions)：公开仓库的标准运行器免费；私有仓库计算与存储按账户额度计算。
- [套餐包含额度](https://docs.github.com/en/billing/reference/product-usage-included)：当前 GitHub Free 每月包含 12 美元计算额度，Pro 为 18 美元；按标准 Linux 每分钟 0.006 美元分别约合 2,000 / 3,000 分钟，额度也可能被其他符合条件的计算使用共享。
- [运行器单价](https://docs.github.com/en/billing/reference/actions-runner-pricing)：各 job 单独按分钟计量，不以三个 job 的并行墙钟时间代替总计算量。

运行器免费不等于所有存储无限免费。本次不新增报告附件上传或后端依赖缓存；沿用的前端 npm 缓存仍受仓库缓存额度约束，未提高存储额度。运行日志与 job summary 按官方说明不计入报告附件存储额度。

如以后将仓库改为私有、改用大型运行器，或增加报告附件、缓存等存储，应重新核对当时计费规则及账户实际用量。私有仓库超出套餐额度可能计费；有付款方式的账户可在 Billing 的预算中启用达到上限停止使用。此次未读取私人账单、调整付款方式或修改账户预算，不据公开仓库免费推定账户其他服务没有费用。
