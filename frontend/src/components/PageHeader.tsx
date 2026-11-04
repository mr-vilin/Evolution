import type { ReactNode } from 'react';
import { PageContainer } from '@ant-design/pro-components';

export function PageHeader({ title, description, extra, children, area = ['同步中心', '变更日志', '管理设置', '系统信息'].includes(title) ? '系统管理' : '业务管理' }: { title: string; description: string; extra?: ReactNode; children?: ReactNode; area?: string }) {
  const items = [{ title: <a href="/organization">组织服务</a> }, { title: area }, { title }];
  return <PageContainer className="page-heading" ghost title={<h1>{title}</h1>} content={description} extra={extra} breadcrumb={{ items }}>{children}</PageContainer>;
}
