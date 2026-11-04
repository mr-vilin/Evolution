import { useRef, useState } from 'react';
import { Button, Card, Form, Input, Modal, Select, Space, Table, Tag } from 'antd';
import { ExampleFrame } from './ExampleFrame';
import { initialItems, type DemoItem } from './localDemo';

export default function ListExample() {
  const [items, setItems] = useState(initialItems);
  const nextId = useRef(13);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<string>();
  const [editing, setEditing] = useState<DemoItem | 'new' | null>(null);
  const [form] = Form.useForm();
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
  return <ExampleFrame title="列表演示" description="体验本地查询、分页与条目增删改。">
    <Card title="演示项目" extra={<Button type="primary" onClick={() => open('new')}>新增演示条目</Button>}>
      <Space wrap className="toolbar">
        <Input aria-label="搜索演示条目" placeholder="搜索条目名称" allowClear value={search} onChange={event => setSearch(event.target.value)} />
        <Select aria-label="演示条目状态" placeholder="全部状态" allowClear value={status} onChange={setStatus} style={{ minWidth: 140 }} options={['进行中', '已完成'].map(value => ({ label: value, value }))} />
        <Button onClick={() => { setSearch(''); setStatus(undefined); }}>重置筛选</Button>
      </Space>
      <Table<DemoItem> rowKey="id" dataSource={filtered} pagination={{ pageSize: 5, showSizeChanger: false }} scroll={{ x: 600 }} columns={[
        { title: '条目名称', dataIndex: 'name' }, { title: '负责人', dataIndex: 'owner' },
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
  </ExampleFrame>;
}
