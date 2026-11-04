import { useState } from 'react';
import { Alert, Button, Card, Descriptions, Form, Input, Space } from 'antd';
import { ExampleFrame } from './ExampleFrame';

const sample = { name: '演示管理员', email: 'demo@example.com', bio: '探索工作台与组件交互。' };
export default function SettingsExample() {
  const [profile, setProfile] = useState(sample);
  const [saved, setSaved] = useState(false);
  const [form] = Form.useForm();
  return <ExampleFrame title="个人设置演示" description="编辑独立的演示资料，真实管理员资料保持不变。">
    <Card title="演示基本资料">
      <Form form={form} initialValues={sample} layout="vertical" className="example-form" onFinish={values => { setProfile(values); setSaved(true); }}>
        <Form.Item name="name" label="演示昵称" rules={[{ required: true, whitespace: true, message: '请输入演示昵称' }]}><Input maxLength={40} /></Form.Item>
        <Form.Item name="email" label="演示邮箱" rules={[{ required: true, message: '请输入演示邮箱' }, { type: 'email', message: '请输入有效邮箱格式' }]}><Input maxLength={120} /></Form.Item>
        <Form.Item name="bio" label="演示简介"><Input.TextArea rows={3} maxLength={200} /></Form.Item>
        <Space><Button type="primary" htmlType="submit">保存演示资料</Button><Button onClick={() => { form.resetFields(); setProfile(sample); setSaved(false); }}>恢复演示资料</Button></Space>
      </Form>
    </Card>
    <Card title="演示资料预览"><Descriptions column={1} items={[{ key: 'name', label: '昵称', children: profile.name }, { key: 'email', label: '邮箱', children: profile.email }, { key: 'bio', label: '简介', children: profile.bio || '暂无简介' }]} />{saved && <Alert title="演示资料已保存，仅当前页面有效" type="success" showIcon />}</Card>
  </ExampleFrame>;
}
