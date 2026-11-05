import { useState } from 'react';
import { Alert, Button, Card, Form, Input, Progress } from 'antd';
import { Link, useNavigate } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';

export default function RegisterExample() {
  const [captcha, setCaptcha] = useState(false);
  const [form] = Form.useForm();
  const password = Form.useWatch('password', form) as string | undefined;
  const navigate = useNavigate();
  return <ExampleFrame title="注册" description="使用虚构资料体验注册校验和本地演示结果。">
    <Card title="创建演示账户" className="example-account">
      <Form form={form} layout="vertical" autoComplete="off" onFinish={() => { form.resetFields(); navigate('/examples/user/register-result'); }}>
        <Form.Item label="演示邮箱" name="email" rules={[{ required: true, message: '请输入演示邮箱' }, { type: 'email', message: '请输入有效邮箱格式' }]}><Input placeholder="demo@example.com" maxLength={120} /></Form.Item>
        <Form.Item label="演示密码" name="password" rules={[{ required: true, message: '请输入虚构的演示密码' }, { min: 8, message: '演示密码至少 8 位' }]}><Input.Password placeholder="请勿输入真实密码" autoComplete="new-password" maxLength={72} /></Form.Item>
        {password && <Progress percent={Math.min(password.length * 10, 100)} format={() => password.length < 8 ? '太短' : password.length < 12 ? '中' : '强'} />}
        <Form.Item label="确认演示密码" name="confirm" dependencies={['password']} rules={[{ required: true, message: '请确认演示密码' }, ({ getFieldValue }) => ({ validator: (_, value) => !value || value === getFieldValue('password') ? Promise.resolve() : Promise.reject(new Error('两次演示密码不一致')) })]}><Input.Password autoComplete="new-password" maxLength={72} /></Form.Item>
        <Form.Item label="演示手机号" name="mobile" rules={[{ required: true, message: '请输入演示手机号' }, { pattern: /^1\d{10}$/, message: '请输入 11 位演示手机号' }]}><Input maxLength={11} placeholder="虚构手机号" /></Form.Item>
        <Form.Item label="演示验证码" name="captcha" rules={[{ required: true, message: '请输入演示验证码' }, { validator: (_, value) => captcha && value === '123456' ? Promise.resolve() : Promise.reject(new Error('请获取验证码并输入 123456')) }]}><Input maxLength={6} /></Form.Item>
        <Button className="toolbar" onClick={async () => { try { await form.validateFields(['mobile']); setCaptcha(true); } catch { /* 保留字段提示 */ } }}>获取演示验证码</Button>
        {captcha && <Alert className="toolbar" type="info" title="本地演示验证码：123456；未发送短信" />}
        <Button block type="primary" htmlType="submit">演示注册</Button>
      </Form>
      <p><Link to="/examples/login">返回演示登录</Link></p>
    </Card>
  </ExampleFrame>;
}
