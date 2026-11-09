import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { EmployeeTypeSettings } from './EmployeeTypeSettings';
import { request } from '../services/http';

vi.mock('../services/http', async importOriginal => ({
  ...await importOriginal<typeof import('../services/http')>(), request: vi.fn(),
}));
beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  vi.mocked(request).mockReset();
  vi.mocked(request).mockResolvedValue({ data: { permission_role: 'role', store_attribute: 'store', employee_type_options: { '1': '正式', '8': '盟友' } }, meta: {} });
});
afterEach(() => vi.unstubAllGlobals());

it('回显当前 code 对照，支持增删改且仅提交人员类型配置', async () => {
  render(<App><EmployeeTypeSettings /></App>);
  expect(await screen.findByDisplayValue('正式')).toBeTruthy();
  fireEvent.change(screen.getByDisplayValue('正式'), { target: { value: ' 全职人员 ' } });
  fireEvent.click(screen.getByRole('button', { name: '删除第 2 行' }));
  fireEvent.click(screen.getByRole('button', { name: '新增一行' }));
  fireEvent.change(screen.getAllByLabelText('类型代码（code）')[1], { target: { value: '9' } });
  fireEvent.change(screen.getAllByLabelText('显示名称')[1], { target: { value: '兼职人员' } });
  fireEvent.click(screen.getByRole('button', { name: '保存人员类型' }));
  await waitFor(() => expect(request).toHaveBeenLastCalledWith('/admin/api/settings/custom-attrs', {
    method: 'PUT', body: { employee_type_options: { '1': '全职人员', '9': '兼职人员' } },
  }));
});

it('拒绝重复代码并将错误定位到字段', async () => {
  render(<App><EmployeeTypeSettings /></App>);
  await screen.findByDisplayValue('盟友');
  fireEvent.change(screen.getByDisplayValue('8'), { target: { value: ' 1 ' } });
  fireEvent.click(screen.getByRole('button', { name: '保存人员类型' }));
  expect((await screen.findAllByText('类型代码不能重复')).length).toBeGreaterThan(0);
  expect(vi.mocked(request).mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(0);
});

it('保存失败保留填写内容并允许重试', async () => {
  render(<App><EmployeeTypeSettings /></App>);
  await screen.findByDisplayValue('正式');
  fireEvent.change(screen.getByDisplayValue('正式'), { target: { value: '我的名称' } });
  vi.mocked(request).mockRejectedValueOnce(new Error('保存暂不可用'));
  fireEvent.click(screen.getByRole('button', { name: '保存人员类型' }));
  expect(await screen.findByText('保存暂不可用')).toBeTruthy();
  expect(screen.getByDisplayValue('我的名称')).toBeTruthy();
  expect(screen.getByRole('button', { name: '保存人员类型' }).hasAttribute('disabled')).toBe(false);
});
