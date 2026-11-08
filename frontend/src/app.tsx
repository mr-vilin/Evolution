import type { ReactNode } from 'react';
import type { RunTimeLayoutConfig } from '@umijs/max';
import { Link } from '@umijs/max';
import { Button, Space } from 'antd';
import { SettingOutlined, InfoCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { AdminActions } from './components/AdminActions';
import { useWorkspaceSettings } from './components/WorkspaceSettings';
import { Providers } from './components/Providers';
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
  return {
    ...settings,
    ...preferences.settings,
    ErrorBoundary: PageErrorBoundary,
    actionsRender: () => [<Space key="admin" className="workspace-actions" size={0}><Button type="text" aria-label="布局设置" title="布局设置" icon={<SettingOutlined />} onClick={preferences.open} /><Link aria-label="系统信息" title="系统信息" to="/system-info"><Button type="text" aria-label="系统信息" icon={<InfoCircleOutlined />} /></Link><Button type="text" aria-label="官方参考帮助" title="官方参考帮助" icon={<QuestionCircleOutlined />} href="https://pro.ant.design/zh-CN/" target="_blank" rel="noopener noreferrer" /><AdminActions /></Space>],
    rightContentRender: false,
    menuDataRender: (items) => {
      const business = items.filter(item => ['/organization', '/stores'].includes(item.path ?? '') || item.path?.startsWith('/employees/'));
      const system = items.filter(item => ['/sync', '/logs', '/settings', '/system-info'].includes(item.path ?? ''));
      const examples = items.filter(item => item.path?.startsWith('/examples/'));
      return [
        { path: '/business', name: '业务管理', children: business },
        { path: '/system', name: '系统管理', children: system },
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
