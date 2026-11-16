import { App } from 'antd';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { DepartmentDetailDrawer } from './DepartmentDetailDrawer';

const details = {
  id: 'd', feishu_department_id: 'od_real', name: '测试部门', status: 'active', parent_name: '营运中心', path: ['组织', '营运中心', '测试部门'],
  leaders: [{ user_id: 'a', name: '负责人甲', avatar_url: 'https://example.test/a.png', leader_type: 1 },
    { user_id: 'b', name: '负责人乙', avatar_url: null, leader_type: 2 }],
  chat_id: 'oc_real_chat', chat_name: '门店沟通群', chat_owner: { user_id: 'owner', name: '群主丙', avatar_url: null }, chat_status: 'available', detail_warnings: [],
};
const envelope = (data: unknown) => Response.json({ data, meta: {} });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('展示主次负责人、群信息和可复制部门ID，关闭按钮为独立正方形', async () => {
  const user = userEvent.setup();
  const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  const close = vi.fn();
  const fetcher = vi.fn(async () => envelope(details));
  vi.stubGlobal('fetch', fetcher);
  render(<App><DepartmentDetailDrawer departmentId="d" onClose={close} /></App>);
  await screen.findByText('门店沟通群');
  expect(screen.getByText('部门主负责人')).toBeTruthy();
  expect(screen.getByText('部门副负责人')).toBeTruthy();
  expect(screen.getByText('群主丙')).toBeTruthy();
  expect(screen.getByText('营运中心')).toBeTruthy();
  expect(screen.getByText('活跃')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: '复制部门ID' }));
  expect(copy).toHaveBeenCalledWith('od_real');
  await user.click(screen.getByRole('button', { name: '复制群id' }));
  expect(copy).toHaveBeenLastCalledWith('oc_real_chat');
  const button = screen.getByRole('button', { name: '关闭部门详情' });
  expect(button.style.width).toBe('32px');
  expect(button.style.height).toBe('32px');
  expect(button.parentElement?.style.paddingInlineStart).toBe('16px');
  await user.click(button);
  expect(close).toHaveBeenCalledOnce();
});

it('切换部门清除旧资料，失败可重试，关闭停止读取', async () => {
  const fetcher = vi.fn(async () => envelope(details));
  vi.stubGlobal('fetch', fetcher);
  const view = render(<App><DepartmentDetailDrawer departmentId="d" onClose={() => {}} /></App>);
  await screen.findByText('门店沟通群');
  fetcher.mockImplementation(async () => Response.json({ error: { message: '读取失败' } }, { status: 500 }));
  view.rerender(<App><DepartmentDetailDrawer departmentId="next" onClose={() => {}} /></App>);
  expect(screen.queryByText('门店沟通群')).toBeNull();
  await screen.findAllByText('读取失败');
  fetcher.mockImplementation(async () => envelope({ ...details, chat_name: null, chat_owner: null,
    status: 'inactive', chat_status: 'unavailable', detail_warnings: ['群信息暂无权限'] }));
  await userEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  await screen.findByText('群信息暂无权限');
  expect(within(screen.getByRole('dialog')).getAllByText('暂无法读取')).toHaveLength(2);
  expect(screen.queryByText('未设置')).toBeNull();
  expect(screen.getByText('禁用')).toBeTruthy();
  expect(screen.getByRole('button', { name: '复制群id' })).toHaveProperty('disabled', false);
  const calls = fetcher.mock.calls.length;
  view.rerender(<App><DepartmentDetailDrawer onClose={() => {}} /></App>);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(fetcher).toHaveBeenCalledTimes(calls);
});
