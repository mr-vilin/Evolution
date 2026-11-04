import { useState } from 'react';
import { Alert, Button, Card, Form, Input } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';
import { loginReceipt } from './localDemo';

export default function LoginExample() {
  const [receipt, setReceipt] = useState('');
  const [form] = Form.useForm();
  return <ExampleFrame title="登录演示" description="体验账户表单，不切换当前真实管理员身份。">
    <Card title="组织服务 · 演示登录" className="example-account">
      <Form form={form} layout="vertical" autoComplete="off" onFinish={values => { setReceipt(loginReceipt(values.account)); form.setFieldValue('password', ''); }}>
        <Form.Item label="演示账号" name="account" rules={[{ required: true, whitespace: true, message: '请输入虚构的演示账号' }]}><Input placeholder="demo" maxLength={40} /></Form.Item>
        <Form.Item label="演示密码" name="password" rules={[{ required: true, message: '请输入虚构的演示密码' }, { min: 6, message: '演示密码至少 6 位' }]}><Input.Password autoComplete="new-password" placeholder="请勿输入真实密码" maxLength={72} /></Form.Item>
        <Button block type="primary" htmlType="submit">演示登录</Button>
      </Form>
      <p><Link to="/examples/register">体验演示注册</Link></p>
      {receipt && <Alert type="success" title={receipt} showIcon />}
    </Card>
  </ExampleFrame>;
}
