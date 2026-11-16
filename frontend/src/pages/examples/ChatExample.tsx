import { useEffect, useRef, useState } from 'react';
import { Button, Card, Form, Input, Space, Tag } from 'antd';
import { ExampleFrame } from './ExampleFrame';
import { chatReply } from './localDemo';

interface Message { role: '演示助手' | '我'; text: string }
interface Conversation { id: number; name: string; messages: Message[] }
const greeting: Message = { role: '演示助手', text: '你好！这里是本地聊天演示，请输入任意虚构内容。' };
export default function ChatExample() {
  const [conversations, setConversations] = useState<Conversation[]>([{ id: 1, name: '新对话', messages: [greeting] }, { id: 2, name: '表单联动校验', messages: [greeting, { role: '我', text: '如何做表单联动校验？' }, { role: '演示助手', text: '使用 Form.Item 的 dependencies 和 validator 表达字段之间的约束。这里是固定的本地知识样本。' }] }]);
  const [active, setActive] = useState(1);
  const [pending, setPending] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const sequence = useRef(3);
  useEffect(() => () => clearTimeout(timer.current), []);
  const current = conversations.find(item => item.id === active)!;
  const messages = current.messages;
  const [form] = Form.useForm();
  function cancel() { clearTimeout(timer.current); setPending(false); }
  function reset() { cancel(); setConversations([{ id: 1, name: '新对话', messages: [greeting] }]); setActive(1); form.resetFields(); }
  function send({ text }: { text: string }) {
    const trimmed = text.trim();
    if (!trimmed || pending) return;
    const id = active;
    setConversations(previous => previous.map(item => item.id === id ? { ...item, name: item.messages.length === 1 ? trimmed.slice(0, 16) : item.name, messages: [...item.messages, { role: '我', text: trimmed }] } : item));
    setPending(true);
    timer.current = setTimeout(() => {
      setConversations(previous => previous.map(item => item.id === id ? { ...item, messages: [...item.messages, { role: '演示助手', text: chatReply(trimmed) }] } : item));
      setPending(false);
    }, 450);
    form.resetFields();
  }
  return <ExampleFrame title="聊天界面" description="体验会话列表、输入、模拟回复和重置；回复只由本地样本生成。">
    <div className="example-chat">
      <Card title="演示会话"><Space orientation="vertical" style={{ width: '100%' }}><Tag color="blue">本地模拟</Tag><span>{messages.filter(item => item.role === '我').length} 轮对话</span><Button block disabled={pending} onClick={() => { const id = sequence.current++; setConversations(items => [...items, { id, name: '新对话', messages: [greeting] }]); setActive(id); form.resetFields(); }}>新建会话</Button>{conversations.map(item => <div className="demo-conversation" key={item.id}><Button type={item.id === active ? 'primary' : 'text'} disabled={pending} onClick={() => { setActive(item.id); form.resetFields(); }}>{item.name}</Button><Button aria-label={`删除会话 ${item.name}`} type="text" disabled={pending} onClick={() => { if (conversations.length === 1) { reset(); return; } setConversations(items => items.filter(value => value.id !== item.id)); if (active === item.id) setActive(conversations.find(value => value.id !== item.id)!.id); }}>×</Button></div>)}<Button danger onClick={reset}>重置全部会话</Button></Space></Card>
      <Card title="演示助手" extra={<Tag color={pending ? 'processing' : 'success'}>{pending ? '正在模拟回复' : '可对话'}</Tag>}>
        <div className="example-messages" role="log" aria-label="演示聊天记录" aria-live="polite">{messages.map((item, index) => <div key={index} className={`example-message${item.role === '我' ? ' example-message-user' : ''}`}><strong>{item.role}</strong><p>{item.text}</p></div>)}</div>
        <Form form={form} layout="vertical" onFinish={send} className="block-gap">
          <Form.Item label="演示消息" name="text" rules={[{ required: true, whitespace: true, message: '请输入演示消息' }, { max: 500, message: '演示消息最多 500 个字符' }]}><Input.TextArea rows={3} maxLength={500} disabled={pending} placeholder="输入虚构内容，Enter 发送，Shift+Enter 换行" onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); form.submit(); } }} /></Form.Item>
          <Space><Button type="primary" htmlType="submit" loading={pending}>发送演示消息</Button>{pending && <Button onClick={cancel}>停止回复</Button>}</Space>
        </Form>
      </Card>
    </div>
  </ExampleFrame>;
}
