import { useState } from 'react';
import { Alert, Button, Card, Col, DatePicker, Form, Input, Row, Select, Space } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { ExampleFrame } from './ExampleFrame';

const people = ['演示成员甲', '演示成员乙', '演示成员丙'].map(value => ({ label: value, value }));
export default function AdvancedFormExample() {
  const [form] = Form.useForm();
  const [result, setResult] = useState('');
  const [errors, setErrors] = useState(0);
  return <ExampleFrame title="高级表单" description="仓库、任务与成员管理组合表单；多行成员可新增、编辑、删除并逐字段校验。">
    <Form form={form} layout="vertical" initialValues={{ members: [{ name: '演示成员甲', workId: 'DEMO001', department: '设计部' }] }} onFinish={values => { setErrors(0); setResult(`演示提交成功：${values.warehouse}，共 ${values.members.length} 名成员`); }} onFinishFailed={info => { setErrors(info.errorFields.length); form.scrollToField(info.errorFields[0].name, { focus: true }); }}>
      <div className="example-stack">{[{ title: '仓库管理', fields: [{ name: 'warehouse', label: '仓库名称', kind: 'input' }, { name: 'domain', label: '仓库域名', kind: 'domain' }, { name: 'owner', label: '仓库管理员', kind: 'person' }, { name: 'approver', label: '审批员', kind: 'person' }, { name: 'warehouseDates', label: '生效日期', kind: 'date' }, { name: 'visibility', label: '仓库类型', kind: 'type' }] }, { title: '任务管理', fields: [{ name: 'task', label: '任务名称', kind: 'input' }, { name: 'description', label: '任务描述', kind: 'input' }, { name: 'executor', label: '执行人', kind: 'person' }, { name: 'responsible', label: '责任人', kind: 'person' }, { name: 'taskDates', label: '任务日期', kind: 'date' }, { name: 'taskType', label: '任务类型', kind: 'task' }] }].map(group => <Card title={group.title} key={group.title}><Row gutter={[24, 0]}>{group.fields.map(field => <Col xs={24} md={12} xl={8} key={field.name}><Form.Item name={field.name} label={field.label} rules={[{ required: true, message: `请填写${field.label}` }, ...(field.kind === 'domain' ? [{ pattern: /^[a-z][a-z0-9-]{2,30}$/, message: '使用 3 至 31 位小写字母、数字或连字符' }] : [])]}>{field.kind === 'date' ? <DatePicker.RangePicker style={{ width: '100%' }} /> : field.kind === 'person' ? <Select options={people} /> : ['type', 'task'].includes(field.kind) ? <Select options={(field.kind === 'type' ? ['私密', '公开'] : ['开发', '设计', '测试']).map(value => ({ label: value, value }))} /> : <Input maxLength={80} />}</Form.Item></Col>)}</Row></Card>)}
        <Card title="成员管理"><Form.List name="members" rules={[{ validator: (_, members) => members?.length ? Promise.resolve() : Promise.reject(new Error('请至少添加一名成员')) }]}>{(fields, { add, remove }, { errors: memberErrors }) => <>{fields.map(field => <div className="demo-member-row" key={field.key}><Form.Item label="成员姓名" name={[field.name, 'name']} rules={[{ required: true, whitespace: true, message: '请输入成员姓名' }]}><Input maxLength={40} /></Form.Item><Form.Item label="工号" name={[field.name, 'workId']} rules={[{ required: true, whitespace: true, message: '请输入工号' }, { validator: (_, value) => (form.getFieldValue('members') ?? []).filter((item: { workId?: string }) => item?.workId === value).length > 1 ? Promise.reject(new Error('工号不能重复')) : Promise.resolve() }]}><Input maxLength={20} /></Form.Item><Form.Item label="所属部门" name={[field.name, 'department']} rules={[{ required: true, message: '请选择部门' }]}><Select options={['设计部', '研发部', '测试部'].map(value => ({ label: value, value }))} /></Form.Item><Button className="member-remove" aria-label={`删除成员 ${field.name + 1}`} danger icon={<MinusCircleOutlined />} onClick={() => remove(field.name)}>删除</Button></div>)}<Form.ErrorList errors={memberErrors} /><Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({})}>新增成员</Button></>}</Form.List></Card>
        {errors > 0 && <Alert type="error" showIcon title={`有 ${errors} 项信息需要补充或修正`} />}
        {result && <Alert type="success" showIcon title={result} />}
        <Card><Space><Button type="primary" htmlType="submit">提交高级表单</Button><Button onClick={() => { form.resetFields(); setResult(''); setErrors(0); }}>重置</Button></Space></Card>
      </div>
    </Form>
  </ExampleFrame>;
}
