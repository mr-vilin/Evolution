import { useState } from 'react';
import { Alert, Badge, Button, Card, Descriptions, Divider, Table } from 'antd';
import { ExampleFrame } from './ExampleFrame';

const products = [{ id: 'DEMO-001', name: '矿泉水 550ml', barcode: 'DEMO-BAR-01', price: 2, count: 4 }, { id: 'DEMO-002', name: '凉茶 300ml', barcode: 'DEMO-BAR-02', price: 3, count: 2 }, { id: 'DEMO-003', name: '好吃的薯片', barcode: 'DEMO-BAR-03', price: 5, count: 1 }];
export default function BasicProfileExample() {
  const [refreshed, setRefreshed] = useState(false);
  return <ExampleFrame title="基础详情" description="退货申请的基本资料、用户信息、商品明细和处理进度。">
    <Card extra={<Button onClick={() => setRefreshed(true)}>刷新演示进度</Button>}>
      {refreshed && <Alert className="block-gap" type="success" title="演示进度已刷新，样本退货已完成" />}
      <Descriptions title="退款申请" column={{ xs: 1, md: 3 }} items={[{ key: 'id', label: '取货单号', children: 'DEMO-1000000000' }, { key: 'status', label: '状态', children: <Badge status={refreshed ? 'success' : 'processing'} text={refreshed ? '已完成' : '已取货'} /> }, { key: 'order', label: '销售单号', children: 'DEMO-1234123421' }, { key: 'child', label: '子订单', children: 'DEMO-3214321432' }]} /><Divider />
      <Descriptions title="用户信息" column={{ xs: 1, md: 3 }} items={[{ key: 'name', label: '用户姓名', children: '演示用户' }, { key: 'phone', label: '联系电话', children: '虚构号码 138****0000' }, { key: 'delivery', label: '常用快递', children: '演示快递' }, { key: 'address', label: '取货地址', children: '示例市示例区示例街道 1 号（合成地址）' }, { key: 'note', label: '备注', children: '请在工作时间取件（样本）' }]} /><Divider />
      <h3>退货商品</h3><Table rowKey="id" pagination={false} scroll={{ x: 700 }} dataSource={products} columns={[{ title: '商品编号', dataIndex: 'id' }, { title: '商品名称', dataIndex: 'name' }, { title: '商品条码', dataIndex: 'barcode' }, { title: '单价', dataIndex: 'price', render: value => `¥ ${value.toFixed(2)}` }, { title: '数量（件）', dataIndex: 'count' }, { title: '金额', render: (_, row) => `¥ ${(row.price * row.count).toFixed(2)}` }]} summary={() => <Table.Summary.Row><Table.Summary.Cell index={0} colSpan={4}>总计</Table.Summary.Cell><Table.Summary.Cell index={4}>7 件</Table.Summary.Cell><Table.Summary.Cell index={5}>¥ 19.00</Table.Summary.Cell></Table.Summary.Row>} /><Divider />
      <h3>退货进度</h3><Table rowKey="id" pagination={false} scroll={{ x: 650 }} dataSource={['联系客户', '取货员出发', '取货完成', ...(refreshed ? ['退款完成'] : [])].map((name, i) => ({ id: i, name, time: `2026-11-01 ${10 + i}:00:00`, operator: `演示操作员 ${i + 1}` }))} columns={[{ title: '时间', dataIndex: 'time' }, { title: '当前进度', dataIndex: 'name' }, { title: '状态', render: () => <Badge status="success" text="完成" /> }, { title: '操作员 ID', dataIndex: 'operator' }, { title: '耗时', render: () => '1 小时' }]} />
    </Card>
  </ExampleFrame>;
}
