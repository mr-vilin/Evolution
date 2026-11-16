import { useState } from 'react';
import { Alert, Avatar, Button, Card, Descriptions, Form, Input, Modal, Select, Space, Switch, Tabs } from 'antd';
import { ExampleFrame } from './ExampleFrame';

const sample = { name: '演示管理员', email: 'demo@example.com', bio: '探索工作台与组件交互。' };
export default function SettingsExample() {
  const [profile, setProfile] = useState(sample);
  const [saved, setSaved] = useState(false);
  const [form] = Form.useForm();
  const [security, setSecurity] = useState<string>();
  const [securityForm] = Form.useForm();
  const [securityResult, setSecurityResult] = useState('');
  const [bindings, setBindings] = useState<string[]>([]);
  const [notifications, setNotifications] = useState<Record<string, boolean>>({ '账户密码': true, '系统消息': true, '待办任务': false });
  const [avatar, setAvatar] = useState(false);
  const base = <div className="demo-grid-two"><div><Form form={form} initialValues={{ ...sample, country: '中国', province: '示例省', city: '示例市', address: '示例街道 1 号' }} layout="vertical" className="example-form" onFinish={values => { setProfile(values); setSaved(true); }}>
        <Form.Item name="name" label="演示昵称" rules={[{ required: true, whitespace: true, message: '请输入演示昵称' }]}><Input maxLength={40} /></Form.Item>
        <Form.Item name="email" label="演示邮箱" rules={[{ required: true, message: '请输入演示邮箱' }, { type: 'email', message: '请输入有效邮箱格式' }]}><Input maxLength={120} /></Form.Item>
        <Form.Item name="bio" label="演示简介"><Input.TextArea rows={3} maxLength={200} /></Form.Item>
        <Form.Item name="country" label="国家/地区"><Select options={[{ label: '中国', value: '中国' }]} /></Form.Item>
        <Form.Item name="province" label="所在省份"><Select options={[{ label: '示例省', value: '示例省' }]} /></Form.Item>
        <Form.Item name="city" label="所在城市"><Select options={[{ label: '示例市', value: '示例市' }]} /></Form.Item>
        <Form.Item name="address" label="街道地址"><Input maxLength={120} /></Form.Item>
        <Form.Item name="phone" label="联系电话（演示）" rules={[{ pattern: /^1\d{10}$/, message: '请输入 11 位演示手机号' }]}><Input maxLength={11} placeholder="请勿输入真实电话" /></Form.Item>
        <Space><Button type="primary" htmlType="submit">保存演示资料</Button><Button onClick={() => { form.resetFields(); setProfile(sample); setSaved(false); }}>恢复演示资料</Button></Space>
      </Form>
      <Descriptions className="block-gap" column={1} items={[{ key: 'name', label: '昵称', children: profile.name }, { key: 'email', label: '邮箱', children: profile.email }, { key: 'bio', label: '简介', children: profile.bio || '暂无简介' }]} />{saved && <Alert title="演示资料已保存，仅当前页面有效" type="success" showIcon />}</div><div className="demo-avatar-profile"><p>头像</p><Avatar size={128} style={{ background: avatar ? 'var(--app-auxiliary)' : 'var(--app-primary)' }}>{avatar ? '样本' : '演示'}</Avatar><p><Button onClick={() => setAvatar(value => !value)}>更换演示头像</Button></p></div></div>;
  return <ExampleFrame title="个人设置" description="基本设置、安全设置、账户绑定和新消息通知均为页面内演示。">
    <Card><Tabs tabPlacement="start" className="demo-settings-tabs" items={[
      { key: 'base', label: '基本设置', children: base },
      { key: 'security', label: '安全设置', children: <><h3>安全设置</h3><ul className="demo-settings-list">{[{ name: '账户密码', description: '当前演示密码强度：强' }, { name: '密保手机', description: '已绑定：138****0000（合成）' }, { name: '密保问题', description: '未设置密保问题' }, { name: '备用邮箱', description: '已绑定：demo@example.com' }, { name: 'MFA 设备', description: '未绑定演示设备' }].map(item => <li key={item.name}><div><strong>{item.name}</strong><p>{item.description}</p></div><Button type="link" onClick={() => { securityForm.resetFields(); setSecurity(item.name); }}>修改</Button></li>)}</ul>{securityResult && <Alert type="success" title={securityResult} />}</> },
      { key: 'binding', label: '账户绑定', children: <><h3>账户绑定</h3><ul className="demo-settings-list">{['演示协作平台', '演示代码平台', '演示社区'].map(name => <li key={name}><div><strong>{name}</strong><p>{bindings.includes(name) ? '已绑定合成账户' : '当前未绑定'}</p></div><Button type="link" onClick={() => setBindings(value => value.includes(name) ? value.filter(item => item !== name) : [...value, name])}>{bindings.includes(name) ? '解除绑定' : '绑定'}</Button></li>)}</ul></> },
      { key: 'notifications', label: '新消息通知', children: <><h3>新消息通知</h3><ul className="demo-settings-list">{Object.entries(notifications).map(([name, checked]) => <li key={name}><div><strong>{name}</strong><p>开启后显示对应的演示通知状态。</p></div><Switch aria-label={`${name}通知`} checked={checked} onChange={value => setNotifications(previous => ({ ...previous, [name]: value }))} /></li>)}</ul></> },
    ]} /></Card>
    <Modal title={`修改演示${security ?? ''}`} open={Boolean(security)} onCancel={() => setSecurity(undefined)} footer={null}><Form form={securityForm} layout="vertical" onFinish={() => { setSecurityResult(`演示${security}已更新，真实账户保持原状态`); securityForm.resetFields(); setSecurity(undefined); }}><Form.Item name="value" label={`新的演示${security ?? '信息'}`} rules={[{ required: true, whitespace: true, message: '请输入演示内容' }]}><Input.Password autoComplete="new-password" maxLength={80} placeholder="仅输入虚构资料" /></Form.Item><Button type="primary" htmlType="submit">保存演示安全设置</Button></Form></Modal>
  </ExampleFrame>;
}
