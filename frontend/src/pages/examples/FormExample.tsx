import { useState } from 'react';
import { Alert, Button, Card, Form, Input, Select, Space } from 'antd';
import { ExampleFrame } from './ExampleFrame';
import { formReceipt } from './localDemo';

export default function FormExample() {
  const [receipt, setReceipt] = useState('');
  const [form] = Form.useForm();
  return <ExampleFrame title="表单演示" description="填写虚构项目资料，体验字段校验与演示提交反馈。">
    <Card title="项目资料">
      <Form form={form} layout="vertical" className="example-form" initialValues={{ type: '内部协作' }} onFinish={values => setReceipt(formReceipt(values.name))}>
        <Form.Item label="项目名称" name="name" rules={[{ required: true, whitespace: true, message: '请输入项目名称' }, { max: 60, message: '项目名称最多 60 个字符' }]}><Input placeholder="例如：演示工作台" maxLength={60} /></Form.Item>
        <Form.Item label="项目类型" name="type" rules={[{ required: true, message: '请选择项目类型' }]}><Select options={['内部协作', '界面设计', '技术研究'].map(value => ({ label: value, value }))} /></Form.Item>
        <Form.Item label="联系邮箱" name="email" rules={[{ required: true, message: '请输入演示邮箱' }, { type: 'email', message: '请输入有效邮箱格式' }]}><Input placeholder="demo@example.com" /></Form.Item>
        <Form.Item label="项目目标" name="goal" rules={[{ required: true, whitespace: true, message: '请输入项目目标' }]}><Input.TextArea rows={4} maxLength={400} showCount /></Form.Item>
        <Space><Button type="primary" htmlType="submit">提交演示表单</Button><Button onClick={() => { form.resetFields(); setReceipt(''); }}>重置表单</Button></Space>
      </Form>
    </Card>
    {receipt && <Alert type="success" showIcon title={receipt} description="资料仅用于当前页面的演示结果。" />}
  </ExampleFrame>;
}
