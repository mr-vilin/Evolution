import { useState } from 'react';
import { Alert, Button, Card, Result, Space } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';

export default function RegisterResultExample() {
  const [sent, setSent] = useState(false);
  return <ExampleFrame title="注册结果" description="注册流程的成功反馈与后续操作，使用固定合成账户。"><Card><Result status="success" title="演示账户注册成功" subTitle="demo@example.com 已完成本地注册演示。激活邮件为样本文案，不发送邮件，也未创建真实账户。" extra={<Space wrap><Link to="/examples/login"><Button type="primary">查看演示登录</Button></Link><Button onClick={() => setSent(true)}>重新发送演示邮件</Button><Link to="/examples/register"><Button>再次注册演示</Button></Link></Space>} />{sent && <Alert type="success" showIcon title="演示激活邮件已模拟发送" description="本地反馈已生成，没有调用邮件服务。" />}</Card></ExampleFrame>;
}
