import type { ReactNode } from 'react';
import { PageContainer } from '@ant-design/pro-components';

export function PageHeader({ title, description, extra, children, className }: { className?: string; title: string; description: string; extra?: ReactNode; children?: ReactNode; area?: '业务管理' | '系统管理' | '参考案例' }) {
  return <PageContainer className={['page-heading', className].filter(Boolean).join(' ')} ghost title={<h1>{title}</h1>} content={description} extra={extra} breadcrumbRender={false}>{children}</PageContainer>;
}
