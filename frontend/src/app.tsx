import type { ReactNode } from 'react';
import type { RunTimeLayoutConfig } from '@umijs/max';
import { Link } from '@umijs/max';
import { Button, Space, theme } from 'antd';
import { SettingOutlined, InfoCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { AdminActions } from './components/AdminActions';
import { useWorkspaceSettings } from './components/WorkspaceSettings';
import { Providers } from './components/Providers';
import { useThemeColors } from './theme/ThemeProvider';
import { PageErrorBoundary } from './components/PageErrorBoundary';
import settings from '../config/defaultSettings';
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
    colorPrimary: colors.primary,
    token: {
      bgLayout: colors.canvas,
      header: { colorBgHeader: colors.surface, colorBgScrollHeader: colors.surface, colorHeaderTitle: colors.text, colorTextMenu: colors.text, colorTextMenuSecondary: colors.muted, colorTextRightActionsItem: colors.muted, colorBgRightActionsItemHover: token.colorFillAlter },
      sider: { colorMenuBackground: colors.surface, colorTextMenu: colors.text, colorTextMenuSecondary: colors.muted, colorTextMenuTitle: colors.text, colorMenuItemDivider: colors.line, colorBgCollapsedButton: colors.surface, colorTextCollapsedButton: colors.muted, colorBgMenuItemSelected: token.colorPrimaryBg, colorTextMenuSelected: colors.primary, colorTextSubMenuSelected: colors.primary, colorBgMenuItemHover: token.colorFillAlter },
      pageContainer: { colorBgPageContainer: colors.canvas, colorBgPageContainerFixed: colors.surface },
    },
    ErrorBoundary: PageErrorBoundary,
    actionsRender: () => [<Space key="admin" className="workspace-actions" size={0}><Button type="text" aria-label="布局设置" title="布局设置" icon={<SettingOutlined />} onClick={preferences.open} /><Link aria-label="系统信息" title="系统信息" to="/system-info"><Button type="text" aria-label="系统信息" icon={<InfoCircleOutlined />} /></Link><Button type="text" aria-label="官方参考帮助" title="官方参考帮助" icon={<QuestionCircleOutlined />} href="https://pro.ant.design/zh-CN/" target="_blank" rel="noopener noreferrer" /><AdminActions /></Space>],
    rightContentRender: false,
    menuDataRender: (items) => {
      const business = items.filter(item => ['/organization', '/stores'].includes(item.path ?? '') || item.path?.startsWith('/employees/'));
      const system = items.filter(item => ['/sync', '/logs', '/settings', '/system-info'].includes(item.path ?? ''));
      const examples = items.filter(item => item.path?.startsWith('/examples/'));
      const standards = items.filter(item => item.path?.startsWith('/ui-standards/'));
      return [
        { path: '/business', name: '业务管理', children: business },
        { path: '/system', name: '系统管理', children: system },
        { path: '/ui-standards', name: 'UI标准', children: standards },
        { path: '/examples', name: '参考案例', children: examples },
      ];
    },
    menuItemRender: (item, dom) => item.path ? <Link to={item.path} onClick={item.isMobile ? item.onClick : undefined}>{dom}</Link> : dom,
    menuFooterRender: () => <span>内部管理工作台</span>,
    links: [],
    footerRender: false,
    breadcrumbRender: false,
  };
};
