import { Button, Card, Result, Typography } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';

export default function FailExample() {
  return <ExampleFrame title="失败页" description="用明确的原因和修复入口帮助用户完成失败后的恢复。"><Card><Result status="error" title="提交失败" subTitle="请核对并修改以下信息后，再重新提交。" extra={<Link to="/examples/form"><Button type="primary">返回修改</Button></Link>}><div className="demo-result-detail"><Typography.Title level={4}>您提交的内容有如下错误：</Typography.Title><p>✕ 您的演示账户暂未完成本地验证。<Link to="/examples/settings">查看演示资料 →</Link></p><p>✕ 演示项目的日期信息不完整。<Link to="/examples/form">修改目标起止日期 →</Link></p><p className="muted">以上为合成失败原因，不代表真实管理员账户状态。</p></div></Result></Card></ExampleFrame>;
}
