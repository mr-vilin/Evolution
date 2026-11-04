import { useState } from 'react';
import { Button, Card, Form, Input, Space, Tag } from 'antd';
import { ExampleFrame } from './ExampleFrame';
import { chatReply } from './localDemo';

interface Message { role: '演示助手' | '我'; text: string }
const greeting: Message = { role: '演示助手', text: '你好！这里是本地聊天演示，请输入任意虚构内容。' };
export default function ChatExample() {
  const [messages, setMessages] = useState<Message[]>([greeting]);
  const [form] = Form.useForm();
  function send({ text }: { text: string }) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setMessages(previous => [...previous, { role: '我', text: trimmed }, { role: '演示助手', text: chatReply(trimmed) }]);
    form.resetFields();
  }
  return <ExampleFrame title="聊天演示" description="体验输入、对话与会话重置，回复由本地模拟生成。">
    <div className="example-chat">
      <Card title="演示会话"><Space orientation="vertical"><Tag color="blue">本地模拟</Tag><span>{(messages.length - 1) / 2} 轮对话</span><Button onClick={() => { setMessages([greeting]); form.resetFields(); }}>新建会话</Button></Space></Card>
      <Card title="演示助手" extra={<Tag color="success">可对话</Tag>}>
        <div className="example-messages" role="log" aria-label="演示聊天记录" aria-live="polite">{messages.map((item, index) => <div key={index} className={`example-message${item.role === '我' ? ' example-message-user' : ''}`}><strong>{item.role}</strong><p>{item.text}</p></div>)}</div>
        <Form form={form} layout="vertical" onFinish={send} className="block-gap">
          <Form.Item label="演示消息" name="text" rules={[{ required: true, whitespace: true, message: '请输入演示消息' }, { max: 500, message: '演示消息最多 500 个字符' }]}><Input.TextArea rows={3} maxLength={500} placeholder="输入虚构内容，点击发送" /></Form.Item>
          <Button type="primary" htmlType="submit">发送演示消息</Button>
        </Form>
      </Card>
    </div>
  </ExampleFrame>;
}
