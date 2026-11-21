import type { ReactNode } from 'react';
import type { RunTimeLayoutConfig } from '@umijs/max';
import { Link } from '@umijs/max';
import { Button, ConfigProvider, Space, theme } from 'antd';
import { AppstoreOutlined, BgColorsOutlined, BookOutlined, SettingOutlined, InfoCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { AdminActions } from './components/AdminActions';
import { useWorkspaceSettings } from './components/WorkspaceSettings';
import { Providers } from './components/Providers';
import { useThemeColors } from './theme/ThemeProvider';
import { PageErrorBoundary } from './components/PageErrorBoundary';
import settings from '../config/defaultSettings';
import { themeLogoUrl } from './branding/logo';
import { buildInfo } from './buildInfo';
import './styles.css';
import './responsive.css';
import './workspace.css';

export function rootContainer(container: ReactNode) {
  return <Providers>{container}</Providers>;
}

export const layout: RunTimeLayoutConfig = () => {
  const preferences = useWorkspaceSettings();
  const { colors } = useThemeColors();
  const { token } = theme.useToken();
  return {
    ...settings,
    ...preferences.settings,
    logo: <img src={themeLogoUrl(colors.primary)} alt="" />,
    colorPrimary: colors.primary,
    token: {
      bgLayout: colors.canvas,
      header: { colorBgHeader: colors.primary, colorBgScrollHeader: colors.primary, colorHeaderTitle: token.colorTextLightSolid, colorTextMenu: token.colorTextLightSolid, colorTextMenuSecondary: token.colorTextLightSolid, colorTextRightActionsItem: token.colorTextLightSolid, colorBgRightActionsItemHover: token.colorPrimaryHover },
      sider: { colorMenuBackground: colors.surface, colorTextMenu: colors.text, colorTextMenuSecondary: colors.muted, colorTextMenuTitle: colors.text, colorMenuItemDivider: colors.line, colorBgCollapsedButton: colors.surface, colorTextCollapsedButton: colors.muted, colorBgMenuItemSelected: token.colorPrimaryBg, colorTextMenuSelected: colors.primary, colorTextSubMenuSelected: colors.primary, colorBgMenuItemHover: token.colorFillAlter },
      pageContainer: { colorBgPageContainer: colors.canvas, colorBgPageContainerFixed: colors.surface },
    },
    ErrorBoundary: PageErrorBoundary,
    actionsRender: () => [<ConfigProvider key="admin" theme={{ components: { Button: { textTextColor: token.colorTextLightSolid, textTextHoverColor: token.colorTextLightSolid, textTextActiveColor: token.colorTextLightSolid, textHoverBg: token.colorPrimaryHover, colorBgTextActive: token.colorPrimaryActive } } }}><Space className="workspace-actions" size={0}><Button type="text" aria-label="布局设置" title="布局设置" icon={<SettingOutlined />} onClick={preferences.open} /><Link aria-label="系统信息" title="系统信息" to="/system-info"><Button type="text" aria-label="系统信息" icon={<InfoCircleOutlined />} /></Link><Button type="text" aria-label="官方参考帮助" title="官方参考帮助" icon={<QuestionCircleOutlined />} href="https://pro.ant.design/zh-CN/" target="_blank" rel="noopener noreferrer" /><AdminActions /></Space></ConfigProvider>],
    rightContentRender: false,
    menuDataRender: (items) => {
      const business = items.filter(item => ['/organization', '/stores', '/tencent/accounts', '/tencent/costs', '/tencent/cost-dashboard'].includes(item.path ?? '') || item.path?.startsWith('/employees/'));
      const system = items.filter(item => ['/sync', '/logs', '/settings', '/system-info'].includes(item.path ?? ''));
      const examples = items.filter(item => item.path?.startsWith('/examples/'));
      const standards = items.filter(item => item.path?.startsWith('/ui-standards/'));
      return [
        { path: '/business', name: '业务管理', icon: <AppstoreOutlined />, children: business },
        { path: '/system', name: '系统管理', icon: <SettingOutlined />, children: system },
        { path: '/ui-standards', name: 'UI标准', icon: <BgColorsOutlined />, children: standards },
        { path: '/examples', name: '参考案例', icon: <BookOutlined />, children: examples },
      ];
    },
    // ProLayout 默认只绘制一级图标，二级页面保留原菜单 DOM 并补上路由图标。
    menuItemRender: (item, dom) => {
      const content = <span className="workspace-menu-leaf"><span className="workspace-menu-leaf-icon" aria-hidden="true">{item.icon}</span>{dom}</span>;
      return item.path ? <Link to={item.path} onClick={item.isMobile ? item.onClick : undefined}>{content}</Link> : content;
    },
    menuFooterRender: (props) => props?.collapsed ? null : <div className="workspace-menu-version">版本 V {buildInfo.version}</div>,
    links: [],
    footerRender: false,
    breadcrumbRender: false,
  };
};
