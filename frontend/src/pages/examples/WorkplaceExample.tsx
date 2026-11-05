import { useState } from 'react';
import { Avatar, Button, Card, Col, Input, Row, Space, Statistic, Timeline } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';
import { DemoRadar } from './DemoCharts';

export const demoProjects = ['Alipay', 'Angular', 'Ant Design', 'Ant Design Pro', 'Bootstrap', 'React'];
export default function WorkplaceExample() {
  const [links, setLinks] = useState(['操作一', '操作二', '操作三', '操作四', '操作五', '操作六']);
  const [label, setLabel] = useState('');
  return <ExampleFrame title="工作台" description="早安，演示成员，祝你开心每一天！交互专家 | 合成设计团队。">
    <Card><Row gutter={[24, 24]}><Col xs={24} md={12}><Space><Avatar size={64} style={{ background: '#1677ff' }}>演</Avatar><div><h2>让协作更简单</h2><p>今天有 3 项演示任务等待处理。</p></div></Space></Col>{[{ title: '项目数', value: 56 }, { title: '团队内排名', value: '8 / 24' }, { title: '项目访问', value: 2223 }].map(item => <Col xs={8} md={4} key={item.title}><Statistic {...item} /></Col>)}</Row></Card>
    <Row gutter={[24, 24]}><Col xs={24} lg={16}><div className="example-stack"><Card title="进行中的项目" extra={<Link to="/examples/search/projects">全部项目</Link>}><div className="demo-grid-three">{demoProjects.map((name, i) => <div className="demo-project" key={name}><Space><Avatar shape="square" style={{ background: ['#1677ff', '#13c2c2', '#722ed1'][i % 3] }}>{name[0]}</Avatar><strong>{name}</strong></Space><p>为团队提供一致、易用的企业级设计与研发工具。</p><small>演示团队　·　{i + 1} 小时前</small></div>)}</div></Card><Card title="动态"><Timeline items={['在 Ant Design 项目创建了设计稿', '提交了基础表单的交互设计', '邀请演示成员加入协作团队', '完成了查询表格的评审', '更新了工作台项目说明', '发布了新的本地演示快照'].map((content, i) => ({ content: <><strong>演示成员 {i + 1}</strong> {content}<p className="muted">{i + 1} 小时前</p></> }))} /></Card></div></Col><Col xs={24} lg={8}><div className="example-stack"><Card title="快速开始 / 便捷导航"><Space wrap>{links.map(name => <Link key={name} to="/examples/form">{name}</Link>)}</Space><div className="example-filters block-gap"><Input aria-label="快捷入口名称" value={label} maxLength={16} onChange={e => setLabel(e.target.value)} placeholder="新入口名称" /><Button disabled={!label.trim() || links.length >= 10} onClick={() => { setLinks(v => [...v, label.trim()]); setLabel(''); }}>添加入口</Button></div></Card><Card title="团队协作指数"><DemoRadar /></Card><Card title="团队"><Space orientation="vertical">{['设计语言团队', '计算科学中心', '中台体验团队', '开源社区', '交互研究团队'].map(name => <Space key={name}><Avatar size="small">团</Avatar>{name}</Space>)}</Space></Card></div></Col></Row>
  </ExampleFrame>;
}
