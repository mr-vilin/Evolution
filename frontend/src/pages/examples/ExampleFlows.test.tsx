import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import StepFormExample from './StepFormExample';
import LoginExample from './LoginExample';
import RegisterExample from './RegisterExample';
import RegisterResultExample from './RegisterResultExample';
import ChatExample from './ChatExample';

function view(children: ReactNode) { return render(<MemoryRouter><App>{children}</App></MemoryRouter>); }
afterEach(() => vi.unstubAllGlobals());

it('分步表单校验、返回保留输入、口令确认及再转一笔均在本地完成', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  view(<StepFormExample />);
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
  await screen.findByText('请输入收款账户');
  fireEvent.change(screen.getByLabelText('收款账户'), { target: { value: 'receiver@example.com' } });
  fireEvent.change(screen.getByLabelText('收款人姓名'), { target: { value: '演示收款人' } });
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
  await screen.findByLabelText('演示确认口令');
  fireEvent.click(screen.getByRole('button', { name: '上一步' }));
  expect((screen.getByLabelText('收款人姓名') as HTMLInputElement).value).toBe('演示收款人');
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
  fireEvent.change(await screen.findByLabelText('演示确认口令'), { target: { value: 'demo123' } });
  fireEvent.click(screen.getByRole('button', { name: '确认演示转账' }));
  await screen.findByText('演示操作成功');
  fireEvent.click(screen.getByRole('button', { name: '再转一笔' }));
  expect((screen.getByLabelText('收款账户') as HTMLInputElement).value).toBe('');
  expect(fetch).not.toHaveBeenCalled();
});

it('登录模拟不改写身份存储或发送认证请求', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  localStorage.setItem('real-session-marker', 'unchanged');
  view(<LoginExample />);
  fireEvent.change(screen.getByLabelText('演示账号'), { target: { value: 'demo' } });
  fireEvent.change(screen.getByLabelText('演示密码'), { target: { value: 'fake123456' } });
  fireEvent.click(screen.getByRole('button', { name: /^演示登录$/ }));
  await screen.findByText(/演示登录成功：demo/);
  expect((screen.getByLabelText('演示密码') as HTMLInputElement).value).toBe('');
  expect(localStorage.getItem('real-session-marker')).toBe('unchanged');
  expect(fetch).not.toHaveBeenCalled();
});

it('注册校验确认密码并通过独立注册结果路由完成本地流程', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  view(<Routes><Route path="/" element={<RegisterExample />} /><Route path="/examples/user/register-result" element={<RegisterResultExample />} /></Routes>);
  fireEvent.change(screen.getByLabelText('演示邮箱'), { target: { value: 'demo@example.com' } });
  fireEvent.change(screen.getByLabelText('演示密码'), { target: { value: 'fake123456' } });
  fireEvent.change(screen.getByLabelText('确认演示密码'), { target: { value: 'mismatch' } });
  fireEvent.change(screen.getByLabelText('演示手机号'), { target: { value: '13800000000' } });
  fireEvent.click(screen.getByRole('button', { name: '获取演示验证码' }));
  await screen.findByText(/本地演示验证码：123456/);
  fireEvent.change(screen.getByLabelText('演示验证码'), { target: { value: '123456' } });
  fireEvent.click(screen.getByRole('button', { name: /^演示注册$/ }));
  await screen.findByText('两次演示密码不一致');
  fireEvent.change(screen.getByLabelText('确认演示密码'), { target: { value: 'fake123456' } });
  fireEvent.click(screen.getByRole('button', { name: /^演示注册$/ }));
  await screen.findByText('演示账户注册成功');
  expect(fetch).not.toHaveBeenCalled();
});

it('聊天重置会取消等待中的模拟回复，避免旧回复进入新会话', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  view(<ChatExample />);
  fireEvent.change(screen.getByLabelText('演示消息'), { target: { value: '取消此回复' } });
  fireEvent.click(screen.getByRole('button', { name: '发送演示消息' }));
  await screen.findByText('正在模拟回复');
  fireEvent.click(screen.getByRole('button', { name: '重置全部会话' }));
  await waitFor(() => expect(screen.queryByText('正在模拟回复')).toBeNull());
  await new Promise(resolve => setTimeout(resolve, 550));
  expect(screen.queryByText(/已收到“取消此回复”/)).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});
