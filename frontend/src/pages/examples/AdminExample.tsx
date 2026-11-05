import { Alert, Button, Card, Descriptions, Typography } from 'antd';
import { useState } from 'react';
import { ExampleFrame } from './ExampleFrame';
import { HeartTwoTone, SmileTwoTone } from '@ant-design/icons';

export default function AdminExample() {
  const [checked, setChecked] = useState(false);
  return <ExampleFrame title="管理示例" description="官方管理页示例：受保护页面、权限说明与代码参考。">
    <Card><Alert type="success" showIcon title="这是一个仅管理员可见的页面" description="此页面与其他案例共用现有管理员和初始化门禁。下方角色为合成演示资料。" /><Typography.Title level={2} style={{ textAlign: 'center', paddingBlock: 24 }}><SmileTwoTone /> Ant Design Pro <HeartTwoTone twoToneColor="#eb2f96" /> You</Typography.Title><Typography.Title level={4}>页面访问控制</Typography.Title><Typography.Paragraph>在路由边界统一判断访问资格，页面内部再按能力组织操作入口。真实系统继续由后端逐接口鉴权。</Typography.Paragraph><Descriptions column={1} items={[{ key: 'role', label: '演示角色', children: '管理员（合成样本）' }, { key: 'scope', label: '案例范围', children: '只操作当前浏览器页面内的演示状态' }, { key: 'access', label: '权限检查', children: checked ? '演示检查已完成：允许查看案例' : '尚未执行演示检查' }]} /><Button type="primary" onClick={() => setChecked(value => !value)}>{checked ? '重置演示检查' : '检查演示权限'}</Button></Card>
    <Card title="开发参考"><Typography.Paragraph>路由声明、布局菜单和服务端权限应保持一致。演示权限反馈用于理解界面状态，不提供身份切换能力。</Typography.Paragraph><Typography.Text code>access: canAdmin</Typography.Text></Card>
  </ExampleFrame>;
}
