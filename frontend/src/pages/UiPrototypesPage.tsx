import { Card } from 'antd';
import { PageHeader } from '../components/PageHeader';

export default function UiPrototypesPage() {
  return <PageHeader title="UI 原型总览" description="六页静态原型，用于查看页面结构与设计方向；图中数据均为示例，按钮不执行操作。" area="参考案例">
    <Card styles={{ body: { padding: 0, overflow: 'hidden' } }}>
      <iframe
        title="Evolution 六页 UI 原型"
        src="/ui-prototypes/index.html"
        className="ui-prototypes-frame"
        sandbox="allow-popups allow-popups-to-escape-sandbox"
      />
    </Card>
  </PageHeader>;
}
