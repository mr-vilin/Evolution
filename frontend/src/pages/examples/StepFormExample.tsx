import { useState } from 'react';
import { Alert, Button, Card, Descriptions, Divider, Form, Input, InputNumber, Result, Select, Space, Steps } from 'antd';
import { ExampleFrame } from './ExampleFrame';

interface Transfer { payer: string; account: string; name: string; amount: number }
export default function StepFormExample() {
  const [step, setStep] = useState(0);
  const [values, setValues] = useState<Transfer>();
  const [form] = Form.useForm<Transfer>();
  const [confirm] = Form.useForm();
  const descriptions = values && <Descriptions column={1} items={[{ key: 'payer', label: '付款账户', children: values.payer }, { key: 'account', label: '收款账户', children: values.account }, { key: 'name', label: '收款人姓名', children: values.name }, { key: 'amount', label: '转账金额', children: `${values.amount.toFixed(2)} 元（演示）` }]} />;
  return <ExampleFrame title="分步表单" description="将复杂流程拆分为清晰步骤。本例仅模拟转账，不产生实际资金操作。">
    <Card><Steps className="example-step" current={step} items={[{ title: '填写转账信息' }, { title: '确认转账信息' }, { title: '完成' }]} />
      <div className="example-form example-centered block-gap">
        {step === 0 && <Form form={form} layout="vertical" initialValues={{ payer: 'demo@example.com', amount: 500 }} onFinish={data => { setValues(data); setStep(1); }}>
          <Form.Item label="付款账户" name="payer" rules={[{ required: true, message: '请选择付款账户' }]}><Select options={[{ value: 'demo@example.com', label: 'demo@example.com（演示账户）' }]} /></Form.Item>
          <Form.Item label="收款账户" name="account" rules={[{ required: true, message: '请输入收款账户' }, { type: 'email', message: '请输入有效的演示邮箱' }]}><Input placeholder="receiver@example.com" /></Form.Item>
          <Form.Item label="收款人姓名" name="name" rules={[{ required: true, whitespace: true, message: '请输入收款人姓名' }]}><Input maxLength={40} /></Form.Item>
          <Form.Item label="转账金额（元）" name="amount" rules={[{ required: true, message: '请输入金额' }, { type: 'number', min: 0.01, max: 100000, message: '金额应为 0.01 至 100000 元' }]}><InputNumber min={0.01} max={100000} precision={2} /></Form.Item>
          <Button type="primary" htmlType="submit">下一步</Button>
        </Form>}
        {step === 1 && <><Alert type="warning" showIcon title="确认后只生成本地演示结果，无真实转账。" />{descriptions}<Divider /><Form form={confirm} layout="vertical" onFinish={() => { confirm.resetFields(); setStep(2); }}><Form.Item label="演示确认口令" name="password" rules={[{ required: true, message: '请输入演示口令' }, { pattern: /^demo123$/, message: '演示口令为 demo123' }]} extra="本地示例口令：demo123，请勿输入真实密码。"><Input.Password autoComplete="new-password" /></Form.Item><Space><Button type="primary" htmlType="submit">确认演示转账</Button><Button onClick={() => { confirm.resetFields(); setStep(0); }}>上一步</Button></Space></Form></>}
        {step === 2 && <><Result status="success" title="演示操作成功" subTitle="预计两小时内到账（样本文案）；未执行实际转账。" extra={<Button type="primary" onClick={() => { form.resetFields(); setValues(undefined); setStep(0); }}>再转一笔</Button>} />{descriptions}</>}
      </div><Divider /><h3>说明</h3><p className="muted">转账到演示账户：仅用来体验资料录入、确认、完成三个步骤。返回上一步保留输入，刷新恢复初始状态。</p>
    </Card>
  </ExampleFrame>;
}
