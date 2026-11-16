# UI 原型与实现截图

- [项目设计规范](design-standards.md)：当前界面与交互约束；配置默认使用可手动增删行的结构化表单，JSON 编辑仅在需求明确要求时允许。
- [组织树与部门人员浏览需求澄清](organization-tree-clarification-2026-11-05.md)：受控树、按需加载、完整搜索、拖拽排序与人员筛选的确认记录。
- [组织树、部门人员浏览与批量门店设置规格](organization-tree-spec-2026-11-05.md)：完整用户故事、实现与测试决策；已发布 [Issue #11](https://github.com/mr-vilin/Evolution/issues/11)，保留 Q12 实施前置确认。
- [六页原型总览](index.html)：建设前确定的页面结构与设计方向。
- 系统内入口为“参考案例 → UI 原型总览”（`/examples/ui-prototypes`）。`frontend/public/ui-prototypes/` 保存总览 HTML 及六张 SVG 的发布副本；修改本目录原型后须同步这些文件，确保开发与 Docker 制品均可完整查看。
- [桌面实现截图](implemented-desktop.png)：1440×1000，组织树与人员列表。
- [手机实现截图](implemented-mobile.png)：390×844，选择部门后的人员页面；宽表在卡片内滚动。

实现截图来自本机 Edge 对实际 React / Ant Design 页面的浏览器验证。数据由测试请求夹具提供，不是真实企业同步结果；生产代码没有默认登录或示例数据注入。

- 2026-11-06 人员范围、部门统计与邮箱 0012 的本地迁移及浏览器验收：[发布记录](../architecture/local-employee-email-deployment-2026-11-06.md)。
