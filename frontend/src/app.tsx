import type { ReactNode } from 'react';
import type { RunTimeLayoutConfig } from '@umijs/max';
import { Link } from '@umijs/max';
import { Button, Space } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
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
    actionsRender: () => [<Space key="admin" className="workspace-actions" size={0}><Button type="text" icon={<SettingOutlined />} onClick={preferences.open}>布局设置</Button><AdminActions /></Space>],
    rightContentRender: false,
    menuDataRender: (items) => {
      const business = items.filter(item => ['/organization', '/stores'].includes(item.path ?? '') || item.path?.startsWith('/employees/'));
      const system = items.filter(item => ['/sync', '/logs', '/settings', '/system-info'].includes(item.path ?? ''));
      const examples = items.filter(item => item.path?.startsWith('/examples/'));
      return [
        { path: '/business', name: '业务管理', children: business },
        { path: '/system', name: '系统管理', children: system },
        { path: '/examples', name: '参考案例', children: [
          { name: '表单', path: '/examples/forms', children: examples.filter(item => item.path === '/examples/form') },
          { name: '列表', path: '/examples/lists', children: examples.filter(item => item.path === '/examples/list') },
          { name: '账户', path: '/examples/account', children: examples.filter(item => item.path === '/examples/settings') },
          { name: '用户页面', path: '/examples/user', children: examples.filter(item => ['/examples/login', '/examples/register'].includes(item.path ?? '')) },
          { name: '聊天', path: '/examples/conversations', children: examples.filter(item => item.path === '/examples/chat') },
        ] },
      ];
    },
    menuItemRender: (item, dom) => item.path ? <Link to={item.path} onClick={item.isMobile ? item.onClick : undefined}>{dom}</Link> : dom,
    menuFooterRender: () => <span>内部管理工作台</span>,
    links: [],
    footerRender: false,
    breadcrumbRender: false,
  };
};
