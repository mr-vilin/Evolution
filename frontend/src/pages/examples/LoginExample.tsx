import { useState } from 'react';
import { Alert, Button, Card, Checkbox, Form, Input, Space, Tabs } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';
import { loginReceipt } from './localDemo';

export default function LoginExample() {
  const [receipt, setReceipt] = useState('');
  const [form] = Form.useForm();
  const [mode, setMode] = useState('account');
  const [captcha, setCaptcha] = useState(false);
  return <ExampleFrame title="登录" description="体验账户和手机号登录表单，不切换当前真实管理员身份。">
    <Card title="Evolution · 演示登录" className="example-account">
      <p className="muted">企业级中后台界面的本地模拟流程</p>
      <Tabs activeKey={mode} onChange={value => { setMode(value); setReceipt(''); setCaptcha(false); form.resetFields(); }} items={[{ key: 'account', label: '账户密码登录' }, { key: 'mobile', label: '手机号登录' }]} />
      <Form form={form} layout="vertical" autoComplete="off" onFinish={values => { setReceipt(loginReceipt(values.account ?? '演示手机号')); form.setFieldValue('password', ''); form.setFieldValue('code', ''); }}>
        {mode === 'account' ? <>
        <Form.Item label="演示账号" name="account" rules={[{ required: true, whitespace: true, message: '请输入虚构的演示账号' }]}><Input placeholder="demo" maxLength={40} /></Form.Item>
        <Form.Item label="演示密码" name="password" rules={[{ required: true, message: '请输入虚构的演示密码' }, { min: 6, message: '演示密码至少 6 位' }]}><Input.Password autoComplete="new-password" placeholder="请勿输入真实密码" maxLength={72} /></Form.Item>
        </> : <><Form.Item label="演示手机号" name="mobile" rules={[{ required: true, message: '请输入演示手机号' }, { pattern: /^1\d{10}$/, message: '请输入 11 位演示手机号' }]}><Input maxLength={11} /></Form.Item><Form.Item label="演示验证码" name="code" rules={[{ required: true, message: '请输入演示验证码' }, { validator: (_, value) => captcha && value === '123456' ? Promise.resolve() : Promise.reject(new Error('请获取验证码并输入 123456')) }]}><Input maxLength={6} /></Form.Item><Button className="toolbar" onClick={async () => { try { await form.validateFields(['mobile']); setCaptcha(true); } catch { /* 字段保留校验反馈 */ } }}>获取演示验证码</Button>{captcha && <Alert className="toolbar" type="info" title="本地验证码：123456；未发送短信" />}</>}
        <Space className="toolbar" wrap><Checkbox>自动登录（演示）</Checkbox><Button type="link" onClick={() => setReceipt('演示找回密码提示：请联系合成服务台；未发送请求。')}>忘记密码</Button></Space>
        <Button block type="primary" htmlType="submit">演示登录</Button>
      </Form>
      <p><Link to="/examples/register">体验演示注册</Link></p>
      {receipt && <Alert type="success" title={receipt} showIcon />}
    </Card>
  </ExampleFrame>;
}
