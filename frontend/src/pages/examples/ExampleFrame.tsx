import type { ReactNode } from 'react';
import { Alert } from 'antd';
import { PageHeader } from '../../components/PageHeader';
import { useLocation } from '@umijs/max';
import { examplePages, officialSource } from '../../../config/examples';
import './examples.css';

export function ExampleFrame({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  const { pathname } = useLocation();
  const source = examplePages.find(page => page.path === pathname)?.source;
  return <PageHeader title={title} description={description} area="参考案例">
    <div className="example-content">
      <Alert type="info" showIcon title="参考案例 / 演示数据" description="请使用虚构资料试用。操作仅在当前页面生效，刷新恢复样本，不修改真实组织资料或管理员账户。" />
      {children}
      <footer className="example-source">参考 Ant Design Pro 6.0.3 · <a href={`${officialSource}${source ?? ''}`} target="_blank" rel="noopener noreferrer">固定官方源码</a> · <a href="/licenses/ant-design-pro-MIT.txt" target="_blank" rel="noopener noreferrer">MIT 许可</a>；本页为本地演示适配。</footer>
    </div>
  </PageHeader>;
}
