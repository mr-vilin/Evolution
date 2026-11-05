import type { ProLayoutProps } from '@ant-design/pro-components';

const settings: ProLayoutProps = {
  title: '组织服务',
  // 混合导航：顶栏区域，侧栏展示当前区域页面。
  layout: 'mix',
  splitMenus: true,
  navTheme: 'light',
  contentWidth: 'Fluid',
  fixedHeader: true,
  fixSiderbar: true,
  siderWidth: 208,
  logo: false,
  colorPrimary: '#1677ff',
};
export default settings;
