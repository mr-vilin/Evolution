import { useState } from 'react';
import { Avatar, Button, Card, Col, Divider, Input, Row, Space, Tabs, Tag } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';
import { collectionSamples } from './DemoCollection';

export default function AccountCenterExample() {
  const [tags, setTags] = useState(['很有想法的', '专注设计', '热爱学习', '团队协作', '开源爱好者']);
  const [input, setInput] = useState('');
  const [following, setFollowing] = useState(false);
  const items = collectionSamples().slice(0, 6);
  return <ExampleFrame title="个人中心" description="本地演示成员资料、标签、团队及文章、应用、项目。">
    <Row gutter={[24, 24]}><Col xs={24} lg={8}><Card><div className="demo-avatar-profile"><Avatar size={104} style={{ background: '#1677ff' }}>演示</Avatar><h2>演示成员</h2><p>海纳百川，有容乃大</p></div><p>交互专家</p><p>合成设计团队 · 企业体验部</p><p>示例市 · 示例区</p><Divider /><h3>标签</h3><Space wrap>{tags.map(tag => <Tag key={tag} closable onClose={() => setTags(value => value.filter(item => item !== tag))}>{tag}</Tag>)}</Space><div className="example-filters block-gap"><Input aria-label="新标签" value={input} maxLength={16} placeholder="添加演示标签" onChange={e => setInput(e.target.value)} /><Button disabled={!input.trim() || tags.includes(input.trim()) || tags.length >= 12} onClick={() => { setTags(value => [...value, input.trim()]); setInput(''); }}>添加标签</Button></div><Divider /><h3>团队</h3><Space orientation="vertical">{['科学搬砖组', '中台设计团队', '高逼格设计天团', '程序员日常'].map(name => <Space key={name}><Avatar size="small">团</Avatar>{name}</Space>)}</Space><Divider /><Button type={following ? 'default' : 'primary'} onClick={() => setFollowing(value => !value)}>{following ? '已关注演示成员' : '关注演示成员'}</Button></Card></Col>
      <Col xs={24} lg={16}><Card><Tabs items={['文章', '应用', '项目'].map((name, i) => ({ key: name, label: `${name} (${items.length})`, children: <><div className={i === 0 ? 'example-stack' : 'demo-grid-two'}>{items.map(item => <Card size="small" key={item.id} title={item.title}><p>{item.description}</p><Space><Tag color="blue">{item.category}</Tag><span>{i === 0 ? `点赞 ${item.id * 12} · 评论 ${item.id * 3}` : `${item.owner} · ${item.status}`}</span></Space></Card>)}</div><Link to={['/examples/search/articles', '/examples/search/applications', '/examples/search/projects'][i]}><Button className="block-gap">查看全部{name}</Button></Link></> }))} /></Card></Col>
    </Row>
  </ExampleFrame>;
}
