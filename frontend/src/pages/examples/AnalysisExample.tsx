import { useState } from 'react';
import { Card, Col, DatePicker, Progress, Radio, Row, Segmented, Statistic, Table, Tabs, Tag } from 'antd';
import { ExampleFrame } from './ExampleFrame';
import { DemoChart, DemoPie, monthlySales } from './DemoCharts';

export default function AnalysisExample() {
  const [period, setPeriod] = useState('全年');
  const [metric, setMetric] = useState('销售额');
  const [channel, setChannel] = useState('全部渠道');
  const [range, setRange] = useState(false);
  const factor = range ? 0.48 : period === '本周' ? 0.22 : period === '本月' ? 0.65 : 1;
  return <ExampleFrame title="分析页" description="销售指标、趋势、热门搜索与渠道占比，全部来自本地合成样本。">
    <Row gutter={[24, 24]}>{[
      { title: '总销售额', value: '¥ 126,560', foot: '日销售额 ¥ 12,423', chart: <p>周同比 <Tag color="success">↑ 12%</Tag> 日同比 <Tag color="error">↓ 11%</Tag></p> },
      { title: '访问量', value: '8,846', foot: '日访问量 1,234', chart: <DemoChart label="访问量趋势" kind="line" /> },
      { title: '支付笔数', value: '6,560', foot: '转化率 60%', chart: <DemoChart label="支付笔数趋势" /> },
      { title: '运营活动效果', value: '78%', foot: '周同比 ↑ 12% · 日同比 ↓ 11%', chart: <Progress percent={78} /> },
    ].map(item => <Col xs={24} sm={12} xl={6} key={item.title}><Card className="metric-card"><Statistic title={item.title} value={item.value} /><div className="metric-spark">{item.chart}</div><div className="metric-foot">{item.foot}</div></Card></Col>)}</Row>
    <Card title={<Segmented value={metric} onChange={setMetric} options={['销售额', '访问量']} />} extra={<div className="example-filters"><Radio.Group value={period} onChange={e => { setPeriod(e.target.value); setRange(false); }} options={['本周', '本月', '全年']} /><DatePicker.RangePicker aria-label="分析日期范围" onChange={value => setRange(Boolean(value))} /></div>}>
      <Row gutter={[32, 16]}><Col xs={24} lg={16}><h3>{metric}趋势 · {range ? '自选日期' : period}</h3><DemoChart label={`${metric}趋势`} values={monthlySales.map(v => Math.round(v * factor * (metric === '访问量' ? 0.7 : 1)))} /></Col><Col xs={24} lg={8}><h3>门店{metric}排名（演示）</h3><ol className="demo-ranking">{['工专路 0 号店', '工专路 1 号店', '工专路 2 号店', '工专路 3 号店', '工专路 4 号店', '工专路 5 号店', '工专路 6 号店'].map((name, i) => <li key={name}><span>{name}</span><strong>{Math.round((323234 - i * 23456) * factor).toLocaleString()}</strong></li>)}</ol></Col></Row>
    </Card>
    <Row gutter={[24, 24]}><Col xs={24} lg={12}><Card title="线上热门搜索"><Row gutter={24}><Col span={12}><Statistic title="搜索用户数" value={12321} suffix="↑ 17.1%" /></Col><Col span={12}><Statistic title="人均搜索次数" value={2.7} precision={1} suffix="↑ 26.2%" /></Col></Row><DemoChart label="搜索趋势" kind="line" /><Table rowKey="id" size="small" pagination={{ pageSize: 5 }} dataSource={Array.from({ length: 10 }, (_, i) => ({ id: i + 1, word: `搜索关键词-${i + 1}`, users: 1200 - i * 67, change: `${12 + i}%` }))} columns={[{ title: '排名', dataIndex: 'id' }, { title: '搜索关键词', dataIndex: 'word' }, { title: '用户数', dataIndex: 'users', sorter: (a, b) => a.users - b.users }, { title: '周涨幅', dataIndex: 'change' }]} /></Card></Col><Col xs={24} lg={12}><Card title="销售额类别占比" extra={<Radio.Group size="small" value={channel} onChange={e => setChannel(e.target.value)} options={['全部渠道', '线上', '门店']} />}><DemoPie label={`${channel}销售额类别占比`} names={['家用电器', '食用酒水', '个护健康', '服饰箱包', '母婴产品', '其他']} values={[4544, 3321, 3113, 2341, 1231, 1231].map((value, i) => Math.round(value * (channel === '线上' ? (i % 2 ? 0.8 : 0.5) : channel === '门店' ? (i % 2 ? 0.2 : 0.5) : 1)))} /></Card></Col></Row>
    <Card><Tabs items={['同仁路', '工专路', '公园路'].map((name, i) => ({ key: name, label: <div>{name}店<Progress type="circle" size={40} percent={45 + i * 12} /></div>, children: <><p className="muted">● 客流量　<span style={{ color: 'var(--app-auxiliary)' }}>● 支付笔数</span></p><DemoChart label={`${name}客流趋势`} kind="line" values={monthlySales.map(v => v + i * 18)} secondary={monthlySales.map((v, index) => Math.round(v * (0.5 + index % 3 * 0.1)))} /></> }))} /></Card>
  </ExampleFrame>;
}
