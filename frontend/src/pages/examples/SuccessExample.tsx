import { Button, Card, Descriptions, Result, Space, Steps } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';

export default function SuccessExample() {
  return <ExampleFrame title="成功页" description="用于反馈一系列操作任务的处理结果，并展示后续流程。"><Card><Result status="success" title="提交成功" subTitle="演示申请已提交。结果页适合展示复杂任务的反馈、单据信息和接下来的处理步骤。" extra={<Space wrap><Link to="/examples/list"><Button type="primary">返回列表</Button></Link><Link to="/examples/profile/advanced"><Button>查看项目</Button></Link><Link to="/examples/form"><Button>再建一个</Button></Link></Space>}><div className="demo-result-detail"><Descriptions title="项目名称：演示工作台建设" column={{ xs: 1, md: 3 }} items={[{ key: 'id', label: '项目 ID', children: 'DEMO-23421' }, { key: 'owner', label: '负责人', children: '演示成员甲' }, { key: 'time', label: '生效时间', children: '2026-11-01 ~ 2026-12-01' }]} /><Steps current={1} items={[{ title: '创建项目', content: '演示成员甲 · 11-01 10:00' }, { title: '部门初审', content: '等待演示成员乙处理' }, { title: '财务复核' }, { title: '完成' }]} /></div></Result></Card></ExampleFrame>;
}
