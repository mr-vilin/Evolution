import { useRef, useState } from 'react';
import { Alert, Avatar, Button, Card, Descriptions, Drawer, Empty, Form, Input, Modal, Pagination, Progress, Radio, Select, Space, Statistic, Tabs, Tag } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';

type Kind = 'standard' | 'cards' | 'articles' | 'projects' | 'applications';
interface Entry { id: number; title: string; description: string; owner: string; status: string; category: string }
const names = ['Ant Design', '企业协作', '设计语言', '研发工作台', '组件实验室', '数据分析'];
export function collectionSamples(): Entry[] { return Array.from({ length: 18 }, (_, i) => ({ id: i + 1, title: `${names[i % names.length]} ${i + 1}`, description: '连接设计与开发，让复杂工作变得清晰易用。这是独立的合成案例资料。', owner: ['演示同事甲', '演示同事乙', '演示同事丙'][i % 3], status: i % 3 === 0 ? '已完成' : '进行中', category: ['设计', '开发', '测试'][i % 3] })); }
const titles: Record<Kind, string> = { standard: '标准列表', cards: '卡片列表', articles: '搜索文章', projects: '搜索项目', applications: '搜索应用' };
export function DemoCollection({ kind }: { kind: Kind }) {
  const [entries, setEntries] = useState(collectionSamples);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('全部');
  const [category, setCategory] = useState<string>();
  const [owner, setOwner] = useState<string>();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Entry | 'new'>();
  const [detail, setDetail] = useState<Entry>();
  const [liked, setLiked] = useState<number[]>([]);
  const [feedback, setFeedback] = useState('');
  const [form] = Form.useForm<Entry>();
  const nextId = useRef(19);
  const searchKind = ['articles', 'projects', 'applications'].includes(kind);
  const filtered = entries.filter(item => item.title.toLowerCase().includes(query.toLowerCase()) && (status === '全部' || item.status === status) && (!category || item.category === category) && (!owner || item.owner === owner));
  const currentPage = Math.min(page, Math.max(1, Math.ceil(filtered.length / 6)));
  const visible = filtered.slice((currentPage - 1) * 6, currentPage * 6);
  function edit(item: Entry | 'new') { form.resetFields(); form.setFieldsValue(item === 'new' ? { owner: '演示同事甲', status: '进行中', category: '设计' } : item); setEditing(item); }
  function save(values: Entry) { if (editing === 'new') setEntries(items => [{ ...values, id: nextId.current++ }, ...items]); else if (editing) setEntries(items => items.map(item => item.id === editing.id ? { ...values, id: item.id } : item)); setEditing(undefined); setPage(1); setFeedback('演示内容已保存'); }
  function remove(item: Entry) { setEntries(items => items.filter(row => row.id !== item.id)); setFeedback(`已删除演示内容：${item.title}`); }
  const actions = (item: Entry) => <Space wrap><Button type="link" onClick={() => setDetail(item)}>查看</Button><Button type="link" onClick={() => edit(item)}>编辑</Button><Button type="link" danger onClick={() => remove(item)}>删除</Button></Space>;
  return <ExampleFrame title={titles[kind]} description={kind === 'standard' ? '展示任务状态、进度与操作，支持搜索、状态筛选和新增任务。' : kind === 'cards' ? '以卡片呈现产品或项目，提供创建入口及本地编辑。' : '按分类、作者检索合成内容，体验不同搜索结果的展示方式。'}>
    {kind === 'standard' && <Card><div className="demo-grid-three"><Statistic title="我的待办" value={entries.filter(i => i.status === '进行中').length} suffix="个任务" /><Statistic title="本周任务平均处理时间" value={32} suffix="分钟" /><Statistic title="已完成任务" value={entries.filter(i => i.status === '已完成').length} suffix="个任务" /></div></Card>}
    {kind === 'cards' && <Card title="卡片列表"><p>段落示意：以一致的信息结构呈现产品介绍、负责人和操作入口，让不同内容易于浏览。</p><Link to="/examples/form">快速开始 →</Link></Card>}
    <Card title={searchKind ? '搜索条件' : '列表筛选'}><div className="example-filters"><Input.Search aria-label="搜索内容" placeholder="搜索名称" value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} allowClear /><Radio.Group aria-label="内容状态" value={status} onChange={e => { setStatus(e.target.value); setPage(1); }} options={['全部', '进行中', '已完成']} /><Select aria-label="所属分类" placeholder="所属分类" allowClear value={category} onChange={v => { setCategory(v); setPage(1); }} options={['设计', '开发', '测试'].map(value => ({ value, label: value }))} /><Select aria-label="内容作者" placeholder="作者" allowClear value={owner} onChange={v => { setOwner(v); setPage(1); }} options={['演示同事甲', '演示同事乙', '演示同事丙'].map(value => ({ value, label: value }))} /><Button onClick={() => { setQuery(''); setStatus('全部'); setCategory(undefined); setOwner(undefined); setPage(1); }}>重置筛选</Button><Button type="primary" onClick={() => edit('new')}>新增{kind === 'articles' ? '文章' : kind === 'applications' ? '应用' : '项目'}</Button></div>
      {searchKind && <Tabs activeKey={kind} items={[{ key: 'articles', label: <Link to="/examples/search/articles">文章</Link> }, { key: 'projects', label: <Link to="/examples/search/projects">项目</Link> }, { key: 'applications', label: <Link to="/examples/search/applications">应用</Link> }]} />}
    </Card>
    {feedback && <Alert type="success" title={feedback} closable={{ onClose: () => setFeedback('') }} />}
    {!visible.length ? <Card><Empty description="没有匹配的演示内容" /></Card> : kind === 'standard' ? <Card title="任务列表"><ul className="demo-standard-list">{visible.map(item => <li key={item.id}><Avatar size={48} shape="square" style={{ background: 'var(--app-primary)' }}>{item.title[0]}</Avatar><div className="demo-list-main"><h3>{item.title}</h3><p>{item.description}</p><small>{item.owner}　开始时间：2026-11-01 10:00</small></div><div className="demo-list-progress"><Progress percent={item.status === '已完成' ? 100 : 30 + item.id * 3 % 60} /><Tag>{item.status}</Tag></div>{actions(item)}</li>)}</ul></Card> : kind === 'articles' ? <Card title={`文章结果 · ${filtered.length} 篇`}><ul className="demo-article-list">{visible.map(item => <li key={item.id}><Button className="article-title" type="link" onClick={() => setDetail(item)}>{item.title}</Button><div><Tag color="processing">{item.category}</Tag><Tag>Ant Design</Tag></div><p>{item.description} 文章内容聚焦企业级界面的设计原则、开发实践与团队协作方法。</p><small>{item.owner} 发布于 2026-11-01</small><div className="example-filters block-gap"><Button type="text" onClick={() => setLiked(ids => ids.includes(item.id) ? ids.filter(id => id !== item.id) : [...ids, item.id])}>{liked.includes(item.id) ? '已点赞' : '点赞'} {item.id * 12 + Number(liked.includes(item.id))}</Button><span>评论 {item.id * 3}</span>{actions(item)}</div></li>)}</ul></Card> : <div className="demo-grid-three">{kind === 'cards' && <Button className="demo-create-card" type="dashed" onClick={() => edit('new')}>＋ 新增产品</Button>}{visible.map(item => <Card key={item.id} title={<Space><Avatar shape="square" style={{ background: ['var(--app-primary)', 'var(--app-auxiliary)', 'var(--app-accent)'][item.id % 3] }}>{item.title[0]}</Avatar>{item.title}</Space>} cover={kind === 'projects' ? <div className={`demo-project-cover cover-${item.id % 3}`}><strong>{item.category}</strong><span>设计连接未来</span></div> : undefined}>
      <p>{item.description}</p>
      {kind === 'applications' ? <div className="demo-grid-two"><Statistic title="活跃用户" value={1700 + item.id * 23} /><Statistic title="新增用户" value={100 + item.id * 7} /></div> : <p className="muted">{item.owner}　·　2026-11-01</p>}
      <Tag color={item.status === '已完成' ? 'success' : 'processing'}>{item.status}</Tag><div className="block-gap">{actions(item)}</div>
    </Card>)}</div>}
    <Pagination aria-label="演示内容分页" current={currentPage} total={filtered.length} pageSize={6} showSizeChanger={false} onChange={setPage} showTotal={total => `共 ${total} 条`} />
    <Modal title={editing === 'new' ? '新增演示内容' : '编辑演示内容'} open={Boolean(editing)} onCancel={() => setEditing(undefined)} footer={null}><Form form={form} layout="vertical" onFinish={save}><Form.Item label="名称" name="title" rules={[{ required: true, whitespace: true, message: '请输入名称' }]}><Input maxLength={60} /></Form.Item><Form.Item label="描述" name="description" rules={[{ required: true, whitespace: true, message: '请输入描述' }]}><Input.TextArea rows={3} maxLength={300} /></Form.Item><Form.Item label="负责人" name="owner" rules={[{ required: true, message: '请选择负责人' }]}><Select options={['演示同事甲', '演示同事乙', '演示同事丙'].map(value => ({ value, label: value }))} /></Form.Item><Form.Item label="分类" name="category" rules={[{ required: true, message: '请选择分类' }]}><Select options={['设计', '开发', '测试'].map(value => ({ value, label: value }))} /></Form.Item><Form.Item label="状态" name="status" rules={[{ required: true, message: '请选择状态' }]}><Radio.Group options={['进行中', '已完成']} /></Form.Item><Button type="primary" htmlType="submit">保存演示内容</Button></Form></Modal>
    <Drawer title="演示内容详情" open={Boolean(detail)} onClose={() => setDetail(undefined)}>{detail && <><h2>{detail.title}</h2><p>{detail.description}</p><Descriptions column={1} items={[{ key: 'owner', label: '负责人', children: detail.owner }, { key: 'category', label: '分类', children: detail.category }, { key: 'status', label: '状态', children: detail.status }]} /></>}</Drawer>
  </ExampleFrame>;
}
