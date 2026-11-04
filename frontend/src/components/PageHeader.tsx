import type { ReactNode } from 'react';
import { PageContainer } from '@ant-design/pro-components';

export function PageHeader({ title, description, extra, children, area = '业务管理' }: { title: string; description: string; extra?: ReactNode; children?: ReactNode; area?: '业务管理' | '系统管理' | '参考案例' }) {
  const items = [{ title: '组织服务' }, { title: area }, { title }];
  return <PageContainer className="page-heading" ghost title={<h1>{title}</h1>} content={description} extra={extra} breadcrumb={{ items }}>{children}</PageContainer>;
}
