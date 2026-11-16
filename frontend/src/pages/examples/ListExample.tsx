import { useRef, useState } from 'react';
import { Alert, Button, Card, Descriptions, Drawer, Form, Input, Modal, Select, Space, Table, Tag } from 'antd';
import { ExampleFrame } from './ExampleFrame';
import { initialItems, type DemoItem } from './localDemo';

export default function ListExample() {
  const [items, setItems] = useState(initialItems);
  const nextId = useRef(13);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<string>();
  const [editing, setEditing] = useState<DemoItem | 'new' | null>(null);
  const [form] = Form.useForm();
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [detail, setDetail] = useState<DemoItem>();
  function open(item: DemoItem | 'new') {
    form.resetFields();
    form.setFieldsValue(item === 'new' ? { status: '进行中', owner: '演示成员' } : item);
    setEditing(item);
  }
  function save(values: Omit<DemoItem, 'id'>) {
    if (editing === 'new') {
      const item = { ...values, id: nextId.current++ };
      setItems(previous => [item, ...previous]);
    }
    else if (editing) setItems(previous => previous.map(item => item.id === editing.id ? { ...values, id: editing.id } : item));
    setEditing(null);
  }
  const filtered = items.filter(item => item.name.includes(search) && (!status || item.status === status));
  return <ExampleFrame title="查询表格" description="规则查询、批量操作、条目详情与结构化编辑，体验完整列表工作流。">
    <Card title="查询规则" extra={<Button type="primary" onClick={() => open('new')}>新增演示条目</Button>}>
      <Space wrap className="toolbar">
        <Input aria-label="搜索演示条目" placeholder="搜索条目名称" allowClear value={search} onChange={event => setSearch(event.target.value)} />
        <Select aria-label="演示条目状态" placeholder="全部状态" allowClear value={status} onChange={setStatus} style={{ minWidth: 140 }} options={['进行中', '已完成'].map(value => ({ label: value, value }))} />
        <Button onClick={() => { setSearch(''); setStatus(undefined); }}>重置筛选</Button>
      </Space>
      <Alert type="info" title={<Space wrap>已选择 {selected.length} 项<Button type="link" disabled={!selected.length} onClick={() => { setItems(previous => previous.map(item => selected.includes(item.id) ? { ...item, status: '已完成' } : item)); setSelected([]); }}>批量完成</Button><Button type="link" onClick={() => setSelected([])}>清空选择</Button></Space>} />
      <Table<DemoItem> rowKey="id" dataSource={filtered} rowSelection={{ selectedRowKeys: selected, onChange: setSelected }} pagination={{ pageSize: 5, showSizeChanger: false }} scroll={{ x: 800 }} columns={[
        { title: '规则名称', dataIndex: 'name', render: (value, item) => <Button type="link" onClick={() => setDetail(item)}>{value}</Button> }, { title: '负责人', dataIndex: 'owner' },
        { title: '描述', render: () => '这是一条合成的演示规则' },
        { title: '调用次数', render: (_, item) => item.id * 102, sorter: (a, b) => a.id - b.id },
        { title: '状态', dataIndex: 'status', render: value => <Tag color={value === '已完成' ? 'success' : 'processing'}>{value}</Tag> },
        { title: '操作', render: (_, item) => <Space><Button type="link" onClick={() => open(item)}>编辑</Button><Button danger type="link" onClick={() => setItems(previous => previous.filter(row => row.id !== item.id))}>删除</Button></Space> },
      ]} />
    </Card>
    <Modal title={editing === 'new' ? '新增演示条目' : '编辑演示条目'} open={editing !== null} onCancel={() => setEditing(null)} footer={null}>
      <Form form={form} layout="vertical" onFinish={save}>
        <Form.Item name="name" label="条目名称" rules={[{ required: true, whitespace: true, message: '请输入条目名称' }, { max: 80, message: '最多 80 个字符' }]}><Input maxLength={80} /></Form.Item>
        <Form.Item name="owner" label="负责人" rules={[{ required: true, whitespace: true, message: '请输入负责人' }]}><Input maxLength={40} /></Form.Item>
        <Form.Item name="status" label="状态" rules={[{ required: true, message: '请选择状态' }]}><Select options={['进行中', '已完成'].map(value => ({ label: value, value }))} /></Form.Item>
        <Button type="primary" htmlType="submit">保存演示条目</Button>
      </Form>
    </Modal>
    <Drawer title="规则详情" open={Boolean(detail)} onClose={() => setDetail(undefined)}><Descriptions column={1} items={detail ? [{ key: 'name', label: '规则名称', children: detail.name }, { key: 'owner', label: '负责人', children: detail.owner }, { key: 'status', label: '状态', children: detail.status }, { key: 'schedule', label: '调度周期', children: '每日（本地样本文案）' }] : []} /></Drawer>
  </ExampleFrame>;
}
