# 产品版本实现说明

## 规则来源

版本决策统一使用全局 `version-management-guidelines` Skill：

`C:/Users/Vilin/.codex/skills/version-management-guidelines/SKILL.md`

处理版本管理及主分支 PR 时读取该 Skill 的现行内容。本文件仅记录项目实现入口，不复制或覆盖其递增、触发时机、首次稳定发布、候选确认及日期规则。

## 项目文件与运行元信息

- `version.json`：产品版本的唯一手工声明。
- `CHANGELOG.md`：产品变更及版本记录。
- `scripts/versioning.mjs`：版本格式、记录顺序、基准历史保留与 tag 一致性校验，以及构建元信息生成。
- `scripts/versioning.test.mjs`：版本工具回归测试。
- `.github/workflows/versioning.yml`：CI 校验、相关测试及构建入口。
- [自动测试与费用说明](ci.md)：完整后端回归、隔离 MySQL、本地复用命令及 GitHub Actions 费用边界。
- `build-info.json`：构建生成的版本、提交、工作区状态、构建时间和发行元信息，不手工编辑或提交。前后端使用同一份元信息，系统信息页核对运行版本。
- `frontend/package.json`、`backend/pyproject.toml`：技术包版本；API 契约和 Alembic revision 分别管理，不作为产品版本来源。

未带发行 tag 的构建使用 `development`、`releaseDate=null`；发行构建通过 `RELEASE_TAG` 读取已校验 tag，并使用完整 `COMMIT_SHA`。脏状态通过 `SOURCE_DIRTY` 传入。文件变化不会自动替换运行镜像；部署入口见 [环境与发布流程](../deploy/ENVIRONMENTS.md)。

## 校验入口

```powershell
node scripts/versioning.mjs check
node --test scripts/versioning.test.mjs
# 基准必须使用已核实的完整提交 SHA
node scripts/versioning.mjs check --base-ref <完整提交SHA>
# 发行制品准备时使用，不能用候选记录冒充已确认日期
node scripts/versioning.mjs check --release
node scripts/versioning.mjs build-info --output build-info.json
```

脚本和 CI 仅检查文件格式与构建一致性；版本级别、PR 触发、首次稳定发布及日期口径由现行全局 Skill 判断。基准检查保留已有版本条目，允许补正说明和日期；不按当前递增策略追溯判定历史编号，也不要求历史日期倒序或全部齐备。发行构建仍需取得当前版本日期，以生成运行元信息。

## 历史依据

2026-10-24 用户确认项目尚未正式上线并从 `0.1.0` 建立开发基线。此记录保留为事实依据，不是当前编号规则。旧编号及当时验收见 [历史归档](releases/legacy-development-history.md)。ADR 0001、0003 中的历史版本流程已退出现行规则入口。
