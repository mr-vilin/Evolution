# 管理端使用与启动指南

## 本地启动

1. 当前工作区已准备依赖，可在根目录终端启动后端（默认 `http://127.0.0.1:8000`）：

   ```powershell
   backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
   ```
2. 在仓库根目录运行：

   ```powershell
   npm.cmd --prefix frontend run dev
   ```

3. 打开终端显示的 Umi Max 地址（默认 `http://127.0.0.1:5173`，可通过 `PORT` 指定端口）。Umi 会把 `/admin`、`/api`、`/auth`、`/health` 代理给本地后端。
4. 未登录时页面只显示飞书登录入口；身份配置缺失、无权限和后端不可用均有独立提示及重试入口。

管理端默认使用真实接口，不自动登录，也不填充示例业务数据。浏览器请求携带会话 Cookie；写请求在会话验证成功后自动带 `X-CSRF-Token`。

无数据库/飞书配置时，上述命令用于检查服务入口和登录门禁。完整业务联调按[部署说明](../deploy/README.md)配置 MySQL、HTTPS 与飞书；本地 Python 从进程环境变量读取配置，复制 `.env` 本身不会自动加载，Compose 会通过 `env_file` 注入。

## 页面说明

- **组织架构**：一次读取完整且版本一致的部门树；搜索部门，独立勾选节点，按直属或全部后代查看员工。编辑门店资料必须先预览，只有预览内容与当前表单、数据版本都一致时才能提交；遇到 409 会保留表单并要求重新预览。
- **人员详情**：展示全部部门关系、全部门店、唯一主门店和派生状态。“不在门店”与“暂无法判断”分别展示。
- **门店管理**：按名称或编码搜索，切换是否包含失效门店，查看全部归属或主门店归属员工，编辑门店编码和备注。人数栏仅表示该门店归属人数。
- **同步中心**：展示初始化、覆盖、最近全量成功时间、全部任务页、实际阶段与计数。总量未知时显示“总量待确认”，不展示伪百分比。活动任务详情每 3 秒轮询，失败任务可重试。
- **变更日志**：按对象、来源、操作者、任务和时间筛选，抽屉内对照 before/after。
- **管理设置**：维护管理员白名单和只读 API 客户端。客户端创建与轮换的密钥只显示一次；轮换、撤销和移出管理员均要求确认。

## 腾讯云页面

- **腾讯云账号**（`/tencent/accounts`）：中文表单选择受控凭据、验证后登记，行操作查看实时余额或维护别名、凭据与总开关。验证和登记时间按北京时间秒展示，可单列升序、降序或取消。
- **实时余额**：进入及手动刷新查询当次返回，失败清除旧结果；不依赖成本同步配置，不自动轮询，也不保存余额历史。
- **腾讯云成本**（`/tencent/costs`）：结构化配置手动/月度/每日/每周计划和执行预算，查看父批次、实际期间及逐次尝试；金额保持原十进制精度。历史面板区分未知起点、连续覆盖、已探测缺口和未探测，指定范围或全部可取历史先预览再确认。尚未受理和预算阻止分别披露。
- **腾讯云费用看板**（`/tencent/cost-dashboard`）：按账号和账月范围查看精确费用、全部产品、覆盖及可比条件下的环比/同比，支持搜索、三态单列排序和全量 CSV。空值不冒充零，缺口不冒充完整总额；刷新保留查询及排序条件。

表格先筛选和完整数据排序再分页，金额比较不经二进制浮点转换。账号与账月费用卡按实际顶栏、工具栏、摘要、分页和三行预算测量高度；窄容器优先保留名称列，空间不足时解除操作列固定。来源时间统一按 `Asia/Shanghai` 显示到秒。

详细边界见[腾讯财务实现](architecture/tencent-finance-implementation.md)、[历史范围](architecture/tencent-cost-history-implementation-2026-11-17.md)和[审查验证](architecture/tencent-finance-review-fixes-2026-11-17.md)。真实腾讯云联调与部署未完成。

## 构建与检查

```powershell
npm.cmd --prefix frontend ci --strict-peer-deps
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
antd.cmd lint frontend/src --format json
```

执行 setup、typecheck 或 build 前先停止 dev；这些命令共用 Umi 生成目录，避免并行生成类型和开发路由。

## 连接与计划

同步中心通过 `/admin/api/status` 显示脱敏连接摘要、最近事件处理时间和失败事件数，并可从事件列表重试包含对象 ID 的失败事件。管理设置通过 `/admin/api/settings/reconcile-schedule` 读取和保存每日核对时间，固定使用 `Asia/Shanghai`。

管理端使用 ProLayout 与 PageContainer，普通资源表由现有 hooks 受控传入 ProTable，不启用额外请求。任务详情使用 `/sync?job=...`，关闭详情会清除参数，支持浏览器前进后退。`react-router-dom` 仅用于测试，应用导航由 Umi 提供。构建命令先生成 Umi 类型并执行 tsc，再构建并输出同一份 `dist/build-info.json`。
