import { useState } from 'react';
import { Alert, Button, Card, Result, Space } from 'antd';
import { Link } from '@umijs/max';
import { ExampleFrame } from './ExampleFrame';

export function ExceptionResult({ code }: { code: '403' | '404' | '500' }) {
  const [retried, setRetried] = useState(false);
  const descriptions = { '403': '抱歉，你无权访问此演示页面。', '404': '抱歉，你访问的演示页面不存在。', '500': '抱歉，演示服务器发生了错误。' };
  return <ExampleFrame title={code} description="异常页面参考，用于说明当前状态并提供清晰的恢复入口。"><Card><Result status={code} title={code} subTitle={descriptions[code]} extra={<Space><Link to="/examples/welcome"><Button type="primary">返回案例首页</Button></Link><Button onClick={() => setRetried(true)}>重新尝试</Button></Space>} />{retried && <Alert type="info" showIcon title="已重新检查演示状态" description="本页固定展示所选异常样式。真实管理员权限和服务器状态保持原有状态。" />}</Card></ExampleFrame>;
}
