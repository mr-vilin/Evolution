import type { ReactNode } from 'react';
import { Alert } from 'antd';
import { PageHeader } from '../../components/PageHeader';
import './examples.css';

export function ExampleFrame({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <PageHeader title={title} description={description} area="参考案例">
    <div className="example-content">
      <Alert type="info" showIcon title="参考案例 / 演示数据" description="请使用虚构资料试用。操作仅在当前页面生效，刷新恢复样本，不修改真实组织资料或管理员账户。" />
      {children}
    </div>
  </PageHeader>;
}
