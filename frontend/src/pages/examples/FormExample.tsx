import { useState } from 'react';
import { Alert, Button, Card, DatePicker, Descriptions, Form, Input, InputNumber, Radio, Select, Space } from 'antd';
import { ExampleFrame } from './ExampleFrame';

export default function FormExample() {
  const [receipt, setReceipt] = useState<{ title: string; goal: string; visibility: string }>();
  const [form] = Form.useForm();
  const visibility = Form.useWatch('visibility', form);
  return <ExampleFrame title="基础表单" description="表单用于收集、校验和提交信息。为工作目标定义标题、起止日期与衡量标准。">
    <Card>
      <Form form={form} layout="vertical" className="example-form example-centered" initialValues={{ visibility: '公开', weight: 100 }} onFinish={setReceipt}>
        <Form.Item label="标题" name="title" rules={[{ required: true, whitespace: true, message: '请输入目标标题' }, { max: 60, message: '标题最多 60 个字符' }]}><Input placeholder="给目标起个名字" maxLength={60} /></Form.Item>
        <Form.Item label="起止日期" name="dates" rules={[{ required: true, message: '请选择起止日期' }]}><DatePicker.RangePicker style={{ width: '100%' }} /></Form.Item>
        <Form.Item label="目标描述" name="goal" rules={[{ required: true, whitespace: true, message: '请输入目标描述' }]}><Input.TextArea rows={4} maxLength={400} showCount placeholder="请输入你的阶段性工作目标" /></Form.Item>
        <Form.Item label="衡量标准" name="criteria" rules={[{ required: true, whitespace: true, message: '请输入衡量标准' }]}><Input.TextArea rows={3} maxLength={300} placeholder="请输入可衡量的完成标准" /></Form.Item>
        <Form.Item label="客户（选填）" name="customer"><Input placeholder="请描述你服务的客户" maxLength={80} /></Form.Item>
        <Form.Item label="邀评人（选填）" name="reviewers"><Select mode="multiple" maxCount={5} options={['演示同事甲', '演示同事乙', '演示同事丙'].map(value => ({ label: value, value }))} /></Form.Item>
        <Form.Item label="权重" name="weight" rules={[{ required: true, message: '请输入权重' }]}><InputNumber min={0} max={100} suffix="%" /></Form.Item>
        <Form.Item label="目标公开" name="visibility"><Radio.Group options={['公开', '部分公开', '不公开']} /></Form.Item>
        {visibility === '部分公开' && <Form.Item label="公开范围" name="visibleTo" rules={[{ required: true, message: '请选择可见同事' }]}><Select mode="multiple" options={['演示同事甲', '演示同事乙', '演示同事丙'].map(value => ({ value, label: value }))} /></Form.Item>}
        <Space wrap><Button type="primary" htmlType="submit">提交演示表单</Button><Button onClick={() => { form.resetFields(); setReceipt(undefined); }}>重置表单</Button></Space>
      </Form>
    </Card>
    {receipt && <Card title="演示提交结果"><Alert type="success" showIcon title={`演示提交成功：${receipt.title}`} /><Descriptions className="block-gap" column={1} items={[{ key: 'goal', label: '目标描述', children: receipt.goal }, { key: 'visibility', label: '目标公开', children: receipt.visibility }]} /></Card>}
  </ExampleFrame>;
}
