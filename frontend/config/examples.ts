// 固定官方 Ant Design Pro 6.0.3 的页面分类。该清单同时驱动路由和导航。
export const exampleGroups = [
  { name: '欢迎与管理', slug: 'overview', icon: 'HomeOutlined', pages: [
    { path: '/examples/welcome', name: '欢迎页', component: 'WelcomeExample', source: 'Welcome.tsx' },
    { path: '/examples/admin', name: '管理示例', component: 'AdminExample', source: 'Admin.tsx' },
  ] },
  { name: 'Dashboard', slug: 'dashboard', icon: 'DashboardOutlined', pages: [
    { path: '/examples/dashboard/analysis', name: '分析页', component: 'AnalysisExample', source: 'dashboard/analysis' },
    { path: '/examples/dashboard/monitor', name: '监控页', component: 'MonitorExample', source: 'dashboard/monitor' },
    { path: '/examples/dashboard/workplace', name: '工作台', component: 'WorkplaceExample', source: 'dashboard/workplace' },
  ] },
  { name: '表单', slug: 'forms', icon: 'FormOutlined', pages: [
    { path: '/examples/form', name: '基础表单', component: 'FormExample', source: 'form/basic-form' },
    { path: '/examples/forms/step', name: '分步表单', component: 'StepFormExample', source: 'form/step-form' },
    { path: '/examples/forms/advanced', name: '高级表单', component: 'AdvancedFormExample', source: 'form/advanced-form' },
  ] },
  { name: '列表', slug: 'lists', icon: 'UnorderedListOutlined', pages: [
    { path: '/examples/list', name: '查询表格', component: 'ListExample', source: 'table-list' },
    { path: '/examples/lists/standard', name: '标准列表', component: 'StandardListExample', source: 'list/basic-list' },
    { path: '/examples/lists/cards', name: '卡片列表', component: 'CardListExample', source: 'list/card-list' },
    { path: '/examples/search/articles', name: '搜索文章', component: 'ArticlesExample', source: 'list/search/articles' },
    { path: '/examples/search/projects', name: '搜索项目', component: 'ProjectsExample', source: 'list/search/projects' },
    { path: '/examples/search/applications', name: '搜索应用', component: 'ApplicationsExample', source: 'list/search/applications' },
  ] },
  { name: '详情', slug: 'profiles', icon: 'ProfileOutlined', pages: [
    { path: '/examples/profile/basic', name: '基础详情', component: 'BasicProfileExample', source: 'profile/basic' },
    { path: '/examples/profile/advanced', name: '高级详情', component: 'AdvancedProfileExample', source: 'profile/advanced' },
  ] },
  { name: '结果', slug: 'results', icon: 'CheckCircleOutlined', pages: [
    { path: '/examples/result/success', name: '成功页', component: 'SuccessExample', source: 'result/success' },
    { path: '/examples/result/fail', name: '失败页', component: 'FailExample', source: 'result/fail' },
  ] },
  { name: '异常', slug: 'exceptions', icon: 'WarningOutlined', pages: [
    { path: '/examples/exception/403', name: '403', component: 'ForbiddenExample', source: 'exception/403' },
    { path: '/examples/exception/404', name: '404', component: 'NotFoundExample', source: 'exception/404' },
    { path: '/examples/exception/500', name: '500', component: 'ServerErrorExample', source: 'exception/500' },
  ] },
  { name: '账户', slug: 'account', icon: 'UserOutlined', pages: [
    { path: '/examples/account/center', name: '个人中心', component: 'AccountCenterExample', source: 'account/center' },
    { path: '/examples/settings', name: '个人设置', component: 'SettingsExample', source: 'account/settings' },
  ] },
  { name: '用户页面', slug: 'user', icon: 'LoginOutlined', pages: [
    { path: '/examples/login', name: '登录', component: 'LoginExample', source: 'user/login' },
    { path: '/examples/register', name: '注册', component: 'RegisterExample', source: 'user/register' },
    { path: '/examples/user/register-result', name: '注册结果', component: 'RegisterResultExample', source: 'user/register-result' },
  ] },
  { name: '聊天', slug: 'conversations', icon: 'MessageOutlined', pages: [
    { path: '/examples/chat', name: '聊天界面', component: 'ChatExample', source: 'chatbot' },
  ] },
];
export const examplePages = exampleGroups.flatMap(group => group.pages.map(page => ({ ...page, icon: group.icon })));
export const officialSource = 'https://github.com/ant-design/ant-design-pro/tree/52506486ea134486937043c5fb677d89bbcd07f2/src/pages/';
