import { useState } from 'react';
import { Button, Card, Col, Progress, Row, Statistic, Tag } from 'antd';
import { ExampleFrame } from './ExampleFrame';
import { DemoChart, DemoDonut } from './DemoCharts';

export default function MonitorExample() {
  const [tick, setTick] = useState(0);
  const [paused, setPaused] = useState(false);
  return <ExampleFrame title="监控页" description="活动交易、预测、券核效率和资源监控的本地快照。">
    <Card title="活动实时交易情况" extra={<div className="example-filters"><Tag color={paused ? 'default' : 'processing'}>{paused ? '已暂停' : '模拟监控中'}</Tag><Button onClick={() => setPaused(v => !v)}>{paused ? '继续监控' : '暂停监控'}</Button><Button disabled={paused} onClick={() => setTick(v => v + 1)}>刷新模拟快照</Button></div>}><Row gutter={[24, 24]}>{[{ title: '今日交易总额', value: 124543233 + tick * 1234, suffix: '元' }, { title: '销售目标完成率', value: 92, suffix: '%' }, { title: '活动剩余时间', value: '01:28:09', suffix: '' }, { title: '每秒交易总额', value: 234 + tick * 3, suffix: '元' }].map(item => <Col xs={24} sm={12} lg={6} key={item.title}><Statistic {...item} /></Col>)}</Row><div className="demo-map" role="img" aria-label="合成区域交易分布"><div className="map-grid">{Array.from({ length: 70 }, (_, i) => <span key={i} style={{ opacity: (i * 7 % 10 + 1) / 10, background: i % 5 === 0 ? 'var(--app-auxiliary)' : 'var(--color-primary-border)' }} />)}</div><strong>交易区域分布 · 样本快照 {tick + 1}</strong><p>华东 38%　华南 26%　华北 21%　其他 15%</p></div></Card>
    <Row gutter={[24, 24]}><Col xs={24} lg={16}><Card title="活动情况预测"><Statistic title="目标评估" value="有望达到预期" /><DemoChart label="活动交易预测" kind="line" values={[34, 45, 52, 49, 71, 67, 82, 85, 80, 91, 103, 112 + tick]} /></Card></Col><Col xs={24} lg={8}><Card title="券核效率"><DemoDonut label="核销率" percent={87} /></Card></Col></Row>
    <Row gutter={[24, 24]}><Col xs={24} md={8}><Card title="各品类占比"><DemoDonut label="家电" percent={62} /><p>家电 62% · 食品 24% · 其他 14%</p></Card></Col><Col xs={24} md={8}><Card title="热门搜索"><div className="demo-word-cloud">{['设计语言', 'Ant Design', '企业应用', '工作台', '数据可视化', '组件', '表单', '体验', '效率'].map((word, i) => <span key={word} style={{ fontSize: 14 + i % 3 * 7, color: ['var(--app-primary)', 'var(--app-auxiliary)', 'var(--app-accent)'][i % 3] }}>{word}</span>)}</div></Card></Col><Col xs={24} md={8}><Card title="资源剩余"><DemoDonut label="剩余资源" percent={34} /><Progress percent={66} format={value => `已使用 ${value}%`} /></Card></Col></Row>
  </ExampleFrame>;
}
