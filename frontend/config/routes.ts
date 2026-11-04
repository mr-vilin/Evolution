// 菜单与业务地址共用一份声明；人员详情归属于组织架构。
export default [
  { path: '/initialize', layout: false, component: './InitializationPage', hideInMenu: true },
  { path: '/', redirect: '/organization' },
  { path: '/organization', name: '组织架构', icon: 'ApartmentOutlined', component: './OrganizationPage' },
  { path: '/employees/:id', name: '人员详情', component: './EmployeePage', hideInMenu: true, parentKeys: ['/organization'] },
  { path: '/stores', name: '门店管理', icon: 'ShopOutlined', component: './StoresPage' },
  { path: '/sync', name: '同步中心', icon: 'SyncOutlined', component: './SyncPage' },
  { path: '/logs', name: '变更日志', icon: 'AuditOutlined', component: './LogsPage' },
  { path: '/settings', name: '管理设置', icon: 'SettingOutlined', component: './SettingsPage' },
  { path: '/system-info', name: '系统信息', icon: 'InfoCircleOutlined', component: './SystemInfoPage' },
  { path: '/examples/form', name: '表单演示', icon: 'FormOutlined', component: './examples/FormExample' },
  { path: '/examples/list', name: '列表演示', icon: 'TableOutlined', component: './examples/ListExample' },
  { path: '/examples/settings', name: '个人设置演示', icon: 'UserOutlined', component: './examples/SettingsExample' },
  { path: '/examples/login', name: '登录演示', component: './examples/LoginExample' },
  { path: '/examples/register', name: '注册演示', component: './examples/RegisterExample' },
  { path: '/examples/chat', name: '聊天演示', icon: 'MessageOutlined', component: './examples/ChatExample' },
  { path: '/*', redirect: '/organization' },
];
