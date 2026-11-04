import { useState } from 'react';
import { Button, Card, Form, Input, Result } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';
import { registrationReceipt } from './localDemo';

export default function RegisterExample() {
  const [receipt, setReceipt] = useState('');
  const [form] = Form.useForm();
  return <ExampleFrame title="注册演示" description="使用虚构资料体验注册校验和本地演示结果。">
    <Card title="创建演示账户" className="example-account">
      {receipt ? <Result status="success" title="演示注册成功" subTitle={receipt} extra={<Button onClick={() => setReceipt('')}>再次体验</Button>} /> : <Form form={form} layout="vertical" autoComplete="off" onFinish={values => { setReceipt(registrationReceipt(values.email)); form.resetFields(); }}>
        <Form.Item label="演示邮箱" name="email" rules={[{ required: true, message: '请输入演示邮箱' }, { type: 'email', message: '请输入有效邮箱格式' }]}><Input placeholder="demo@example.com" maxLength={120} /></Form.Item>
        <Form.Item label="演示密码" name="password" rules={[{ required: true, message: '请输入虚构的演示密码' }, { min: 8, message: '演示密码至少 8 位' }]}><Input.Password placeholder="请勿输入真实密码" autoComplete="new-password" maxLength={72} /></Form.Item>
        <Form.Item label="确认演示密码" name="confirm" dependencies={['password']} rules={[{ required: true, message: '请确认演示密码' }, ({ getFieldValue }) => ({ validator: (_, value) => !value || value === getFieldValue('password') ? Promise.resolve() : Promise.reject(new Error('两次演示密码不一致')) })]}><Input.Password autoComplete="new-password" maxLength={72} /></Form.Item>
        <Button block type="primary" htmlType="submit">演示注册</Button>
      </Form>}
      <p><Link to="/examples/login">返回演示登录</Link></p>
    </Card>
  </ExampleFrame>;
}
