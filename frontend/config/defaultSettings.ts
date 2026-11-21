import type { ProLayoutProps } from '@ant-design/pro-components';
import { productName } from '../src/branding/product';

const settings: ProLayoutProps = {
  title: productName,
  // 侧栏统一展示一级分区和二级页面，顶栏保留工作台操作。
  layout: 'mix',
  splitMenus: false,
  menu: { collapsedShowTitle: false },
  navTheme: 'light',
  contentWidth: 'Fluid',
  fixedHeader: true,
  fixSiderbar: true,
  siderWidth: 208,
  logo: '/branding/logo.svg',
};
export default settings;
