import { App } from 'antd';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import type { Employee } from '../domain';
import { EmployeeDetailDrawer } from './EmployeeDetailDrawer';
import { CopyUserId } from './EmployeeIdentity';
import { contactLabel, departmentPath, internationalMobileParts } from './employeePresentation';

const employee: Employee = {
  id: 'internal', user_id: 'feishu-user', name: '测试员工', avatar_url: 'https://example.test/avatar.png',
  leader_name: '测试上级', leader_avatar_url: 'https://example.test/leader.png',
  mobile: '13800000000', email: 'test@example.test', join_date: '2026-11-07',
  field_readability: { mobile: 'readable', email: 'readable', join_time: 'readable' },
  account_status: { is_activated: true, is_frozen: true, is_unjoin: false, is_exited: false, is_resigned: false },
  employee_type_name: '正式员工', primary_department_id: 'd0',
  status: 'active', department_ids: [], stores: [], store_ids: [], primary_store_id: null, primary_store_status: 'unknown',
  departments: Array.from({ length: 7 }, (_, i) => ({ id: `d${i}`, name: `部门${i}`, path: ['组织', '营运中心', `部门${i}`],
    parent_id: '0', status: 'active', is_root: false, is_store: false, store_code: null, notes: null })),
};
const envelope = (data: unknown) => Response.json({ data, meta: {} });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('抽屉展示真实ID、上级头像和入职日期，部门超过5个可展开与收起', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => envelope(employee)));
  render(<App><EmployeeDetailDrawer employeeId="internal" onClose={() => {}} /></App>);
  const drawer = await screen.findByRole('dialog');
  await within(drawer).findByText('feishu-user');
  expect(within(drawer).getByText('2026-11-07')).toBeTruthy();
  expect(within(drawer).getByAltText('测试上级的头像').getAttribute('src')).toBe(employee.leader_avatar_url);
  expect(within(drawer).getByText('营运中心 / 部门0')).toBeTruthy();
  expect(drawer.textContent).not.toContain('组织 /');
  expect(within(drawer).queryByText('部门5')).toBeNull();
  await userEvent.click(within(drawer).getByRole('button', { name: '查看更多（共 7 个）' }));
  expect(within(drawer).getByText('部门6')).toBeTruthy();
  await userEvent.click(within(drawer).getByRole('button', { name: '收起' }));
  expect(within(drawer).queryByText('部门6')).toBeNull();
  expect(within(drawer).getByText('已暂停').closest('.ant-tag')?.className).toContain('filled');
  expect(within(drawer).getByText('正式员工').closest('.ant-tag')).toBeNull();
});

it('切换人员不展示前一个人的资料，读取失败可重试，关闭不再请求', async () => {
  const fetcher = vi.fn(async (url: string) => url.endsWith('/internal') ? envelope(employee)
    : Response.json({ error: { message: '暂时不可用' } }, { status: 500 }));
  vi.stubGlobal('fetch', fetcher);
  const view = render(<App><EmployeeDetailDrawer employeeId="internal" onClose={() => {}} /></App>);
  await screen.findByText('feishu-user');
  view.rerender(<App><EmployeeDetailDrawer employeeId="next" onClose={() => {}} /></App>);
  expect(screen.queryByText('feishu-user')).toBeNull();
  await screen.findByText('暂时不可用');
  fetcher.mockImplementation(async () => envelope({ ...employee, id: 'next', name: '另一个人', user_id: 'next-user' }));
  await userEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  await screen.findByText('next-user');
  const calls = fetcher.mock.calls.length;
  view.rerender(<App><EmployeeDetailDrawer onClose={() => {}} /></App>);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(fetcher).toHaveBeenCalledTimes(calls);
});

it('仅复制飞书 user_id，缺失时禁用，复制失败提示而不报成功', async () => {
  const user = userEvent.setup();
  const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  const view = render(<App><CopyUserId employee={employee} /></App>);
  await user.click(screen.getByRole('button', { name: '复制测试员工的用户ID' }));
  expect(write).toHaveBeenCalledWith('feishu-user');
  write.mockRejectedValue(new Error('denied'));
  await user.click(screen.getByRole('button', { name: '复制测试员工的用户ID' }));
  const fallback = await screen.findByRole('dialog');
  expect(within(fallback).getByText('复制失败，请手动复制用户ID')).toBeTruthy();
  expect(within(fallback).getByText('feishu-user')).toBeTruthy();
  await user.click(within(fallback).getByRole('button', { name: /关\s*闭/ }));
  view.rerender(<App><CopyUserId employee={{ ...employee, user_id: undefined }} /></App>);
  expect(screen.getByRole('button', { name: '复制测试员工的用户ID' })).toHaveProperty('disabled', true);
});

it('虚拟根展示本组织，普通路径只省略开头组织节点', () => {
  expect(departmentPath({ ...employee.departments[0], id: '0' })).toBe('本组织');
  expect(departmentPath({ ...employee.departments[0], path: ['组织', '区域', '组织', '门店'] })).toBe('区域 / 组织 / 门店');
});

it('识别国际手机号区号并保留复制时的原始号码', () => {
  expect(internationalMobileParts('+8613812345678')).toEqual({ callingCode: '+86', number: '13812345678' });
  expect(internationalMobileParts('+12025550101')).toEqual({ callingCode: '+1', number: '2025550101' });
  expect(internationalMobileParts('+85291234567')).toEqual({ callingCode: '+852', number: '91234567' });
  expect(internationalMobileParts('+86 13812345678')).toBeUndefined();
  expect(internationalMobileParts('+99912345678')).toBeUndefined();
  expect(contactLabel({ ...employee, mobile: '+8613812345678' }, 'mobile')).toBe('+8613812345678');
  expect(contactLabel(employee, 'mobile')).toBe(employee.mobile);
  expect(contactLabel({ ...employee, field_readability: undefined }, 'mobile')).toBeUndefined();
});
