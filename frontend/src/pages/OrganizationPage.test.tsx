import { App } from 'antd';
import { MemoryRouter } from 'react-router-dom';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { OrganizationPage } from './OrganizationPage';
const department = { id: 'a', parent_id: '0', name: '总部', path: ['组织', '总部'], status: 'active', is_virtual_root: false, is_store: false, store_code: null, notes: null, has_children: true, sort_order: 0 };
const envelope = (data: unknown, meta = {}) => Response.json({ data, meta: { dataset_epoch: 'e', data_version: 1, next_cursor: null, ...meta } });
beforeEach(() => { vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })); vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => vi.unstubAllGlobals());
it('首次仅读一级部门，展开按需读取，点选具体部门才以20人请求直属人员', async () => {
  const urls: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    urls.push(url);
    if (url.startsWith('/admin/api/organization/selection')) return envelope({ selected_ids: [], count: 0, states: {}, departments: [] });
    if (url.startsWith('/admin/api/organization/departments')) return envelope(new URL(url, 'http://local').searchParams.get('parent_id') === 'a' ? [{ ...department, id: 'b', parent_id: 'a', name: '下级', has_children: false }] : [department]);
    if (url.startsWith('/admin/api/organization/employees')) return envelope([], { total_count: 0 });
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  await screen.findByText('总部');
  expect(urls.some(url => url.includes('/employees'))).toBe(false);
  expect(screen.queryByText('下级')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: '展开总部' }));
  await screen.findByText('下级');
  expect(urls.filter(url => url.includes('/departments')).length).toBe(2);
  await userEvent.click(screen.getByText('总部'));
  await waitFor(() => expect(urls.some(url => url.includes('/employees'))).toBe(true));
  const params = new URL(urls.find(url => url.includes('/employees'))!, 'http://local').searchParams;
  expect(params.get('limit')).toBe('20');
  expect(params.get('include_descendants')).toBe('false');
  expect(params.get('dataset_epoch')).toBe('e');
  expect(params.get('data_version')).toBe('1');
  await userEvent.click(screen.getByText('组织'));
  expect(screen.getByText('选择部门以查看人员。')).toBeTruthy();
});

it('完整范围四步切换覆盖未加载下级，搜索并清空后恢复展开与勾选', async () => {
  const selectionBodies: any[] = [];
  const expected = [[], ['a'], ['a', 'b', 'c'], ['b', 'c'], []];
  let step = 0;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (url.startsWith('/admin/api/organization/selection')) {
      const body = JSON.parse(String(init?.body)); selectionBodies.push(body);
      if (body.toggle_id) step++;
      const ids = expected[step];
      return envelope({ selected_ids: ids, count: ids.length, states: { a: { self_selected: ids.includes('a'), descendants: step === 2 || step === 3 ? 'all' : 'none' } }, departments: [] });
    }
    if (url.includes('/organization/search')) return envelope([department, { ...department, id: 'b', parent_id: 'a', name: '区域' }, { ...department, id: 'c', parent_id: 'b', name: '人民路店', has_children: false }], { matched_ids: ['c'] });
    if (url.includes('/organization/departments')) return envelope([department]);
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  const check = await screen.findByRole('checkbox', { name: '选择总部' });
  await waitFor(() => expect((check as HTMLInputElement).disabled).toBe(false));
  for (const count of [1, 3, 2, 0]) {
    await userEvent.click(check);
    await screen.findByText(`已选 ${count} 个部门`);
  }
  expect(selectionBodies.filter(body => body.toggle_id).map(body => body.selected_ids)).toEqual([[], ['a'], ['a', 'b', 'c'], ['b', 'c']]);
  fireEvent.change(screen.getByPlaceholderText('搜索部门名称'), { target: { value: '民路' } });
  await screen.findByText('人民路店');
  expect(screen.getByText('区域')).toBeTruthy();
  fireEvent.change(screen.getByPlaceholderText('搜索部门名称'), { target: { value: '' } });
  await waitFor(() => expect(screen.queryByText('人民路店')).toBeNull());
  expect(screen.getByRole('button', { name: '展开总部' })).toBeTruthy();
  expect(screen.getByText('已选 0 个部门')).toBeTruthy();
}, 120000);

it('批量直接保存冲突保留草稿，重核显式目标后再次保存且不加入新部门', async () => {
  let version = 1; let saves = 0;
  const writes: any[] = [];
  const child = { ...department, id: 'b', name: '未加载分店', parent_id: 'a', path: ['组织', '总部', '未加载分店'], has_children: false };
  const rows = [department, child].map(row => ({ ...row, is_store: true, notes: row.id === 'a' ? '旧备注' : '分店备注' }));
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (url.includes('/organization/departments')) return envelope([department], { data_version: version });
    if (url.includes('/organization/selection')) {
      const body = JSON.parse(String(init?.body));
      const ids = body.toggle_id === '0' ? ['a', 'b'] : body.selected_ids;
      return envelope({ selected_ids: ids, count: ids.length, states: {}, departments: body.include_details ? rows.filter(row => ids.includes(row.id)) : [] }, { data_version: version });
    }
    if (url === '/admin/api/organization/stores') {
      writes.push(JSON.parse(String(init?.body))); saves++;
      if (saves === 1) { version = 2; return Response.json({ error: { code: 'DATASET_CHANGED', message: 'changed' } }, { status: 409 }); }
      return envelope({ saved_count: 2 }, { data_version: 3 });
    }
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  const root = await screen.findByRole('checkbox', { name: '选择组织' });
  await waitFor(() => expect((root as HTMLInputElement).disabled).toBe(false));
  await userEvent.click(root);
  await screen.findByText('已选 2 个部门');
  await userEvent.click(screen.getByRole('button', { name: '批量设置' }));
  fireEvent.change(await screen.findByDisplayValue('旧备注'), { target: { value: '必须保留的草稿' } });
  expect(screen.queryByRole('button', { name: '预览影响' })).toBeNull();
  await userEvent.click(await screen.findByRole('button', { name: /^保\s*存$/ }));
  await screen.findByText('数据已变化，请重新核对目标与数量');
  expect(screen.getByDisplayValue('必须保留的草稿')).toBeTruthy();
  expect(writes).toHaveLength(1);
  const recheck = screen.getByRole('button', { name: '重新核对目标' });
  await waitFor(() => expect((recheck as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(recheck);
  await screen.findByText(/已重新核对：2 个有效部门/);
  await userEvent.click(await screen.findByRole('button', { name: /^保\s*存$/ }));
  await waitFor(() => expect(writes).toHaveLength(2));
  expect(writes[1].dataset_epoch).toBe('e');
  expect(writes[1].data_version).toBe(2);
  expect(writes[1].changes.map((row: any) => row.department_id)).toEqual(['a', 'b']);
  expect(writes[1].changes[0].notes).toBe('必须保留的草稿');
}, 120000);

it('人员跨三批滚动续载，切换条件忽略旧响应并重置列表', async () => {
  const employeeUrls: string[] = [];
  let finishOld: ((response: Response) => void) | undefined;
  const employees = Array.from({ length: 45 }, (_, index) => ({ id: `u${index}`, user_id: `u${index}`, name: `成员${index}`, status: 'active', primary_store_status: 'unknown' }));
  vi.stubGlobal('fetch', async (url: string) => {
    if (url.includes('/organization/selection')) return envelope({ selected_ids: [], count: 0, states: {}, departments: [] });
    if (url.includes('/organization/departments')) return envelope([department]);
    if (url.includes('/organization/employees')) {
      employeeUrls.push(url); const params = new URL(url, 'http://local').searchParams;
      if (params.get('keyword') === '旧') return new Promise<Response>(resolve => { finishOld = resolve; });
      if (params.get('keyword') === '新') return envelope([{ ...employees[0], id: 'new', name: '新结果' }], { total_count: 1 });
      const offset = Number(params.get('cursor') || 0);
      return envelope(employees.slice(offset, offset + 20), { total_count: 45, next_cursor: offset < 40 ? String(offset + 20) : null });
    }
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  await userEvent.click(await screen.findByText('总部'));
  await screen.findByText('共 45 人，已加载 20 人');
  fireEvent.scroll(screen.getByRole('region', { name: '部门人员列表' }));
  await screen.findByText('共 45 人，已加载 40 人');
  fireEvent.scroll(screen.getByRole('region', { name: '部门人员列表' }));
  await screen.findByText('共 45 人，已加载 45 人');
  expect(employeeUrls).toHaveLength(3);
  fireEvent.scroll(screen.getByRole('region', { name: '部门人员列表' }));
  expect(employeeUrls).toHaveLength(3);
  const input = screen.getByPlaceholderText('搜索姓名、完整手机号或 USER_ID');
  fireEvent.change(input, { target: { value: '旧' } });
  await waitFor(() => expect(finishOld).toBeTruthy());
  fireEvent.change(input, { target: { value: '新' } });
  await screen.findByText('新结果');
  await act(async () => { finishOld!(envelope([{ ...employees[1], name: '迟到结果' }], { total_count: 45, next_cursor: '20' })); });
  expect(screen.queryByText('迟到结果')).toBeNull();
  expect(screen.getByText('共 1 人，已加载 1 人')).toBeTruthy();
}, 120000);
