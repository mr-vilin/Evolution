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
it('默认查看本组织并按总人数限制直属范围，展开继续按需读取', async () => {
  const urls: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    urls.push(url);
    if (url.includes('/organization/summary')) return envelope({ department_id: new URL(url, 'http://local').searchParams.get('department_id'), department_count: 123, employee_count: 45, unactivated_count: 2, unjoin_count: 3, resigned_count: 4, member_count: 45, members_limited: true });
    if (url.startsWith('/admin/api/organization/selection')) return envelope({ selected_ids: [], count: 0, states: {}, departments: [] });
    if (url.startsWith('/admin/api/organization/departments')) return envelope(new URL(url, 'http://local').searchParams.get('parent_id') === 'a' ? [{ ...department, id: 'b', parent_id: 'a', name: '下级', has_children: false }] : [department]);
    if (url.startsWith('/admin/api/organization/employees')) return envelope([], { total_count: 0 });
    if (url.includes('/organization/employees')) return envelope([], { total_count: 0 });
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  await screen.findByText('总部');
  await waitFor(() => expect(urls.some(url => url.includes('/employees') && url.includes('department_id=0'))).toBe(true));
  expect(document.querySelector('.ant-tree-node-selected')?.textContent).toContain('本组织');
  await screen.findByText('123');
  expect(screen.getByRole('region', { name: '部门统计' }).textContent).toContain('已离职4');
  const toggle = screen.getByRole('switch', { name: '显示失效部门' });
  await userEvent.click(toggle);
  await waitFor(() => expect(urls.some(url => url.includes('include_inactive=true'))).toBe(true));
  expect(screen.getByRole('region', { name: '部门统计' })).toBeTruthy();
  expect(screen.getByText('已选 0 个部门')).toBeTruthy();
  expect(screen.queryByText('下级')).toBeNull();
  await userEvent.click(screen.getByRole('img', { name: '展开总部' }));
  await screen.findByText('下级');
  expect(urls.filter(url => url.includes('/departments')).length).toBe(3);
  await userEvent.click(screen.getByText('总部'));
  await waitFor(() => expect(urls.some(url => url.includes('/employees') && url.includes('department_id=a'))).toBe(true));
  const params = new URL(urls.find(url => url.includes('/employees') && url.includes('department_id=a'))!, 'http://local').searchParams;
  expect(params.get('limit')).toBe('20');
  expect(params.get('include_descendants')).toBe('false');
  expect(params.get('dataset_epoch')).toBe('e');
  expect(params.get('data_version')).toBe('1');
  await userEvent.click(screen.getByText('本组织'));
  expect(screen.getByRole('region', { name: '部门统计' })).toBeTruthy();
});

it('完整范围四步切换覆盖未加载下级，搜索并清空后恢复展开与勾选', async () => {
  const selectionBodies: any[] = [];
  const expected = [[], ['a'], ['a', 'b', 'c'], ['b', 'c'], []];
  let step = 0;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (url.includes('/organization/summary')) return envelope({ department_id: new URL(url, 'http://local').searchParams.get('department_id'), department_count: 123, employee_count: 45, unactivated_count: 2, unjoin_count: 3, resigned_count: 4, member_count: 45, members_limited: true });
    if (url.startsWith('/admin/api/organization/selection')) {
      const body = JSON.parse(String(init?.body)); selectionBodies.push(body);
      if (body.toggle_id) step++;
      const ids = expected[step];
      return envelope({ selected_ids: ids, count: ids.length, states: { a: { self_selected: ids.includes('a'), descendants: step === 2 || step === 3 ? 'all' : 'none', selected_count: ids.length } }, departments: [] });
    }
    if (url.includes('/organization/search')) return envelope([department, { ...department, id: 'b', parent_id: 'a', name: '区域' }, { ...department, id: 'c', parent_id: 'b', name: '人民路店', has_children: false }], { matched_ids: ['c'] });
    if (url.includes('/organization/departments')) return envelope([department]);
    if (url.includes('/organization/employees')) return envelope([], { total_count: 0 });
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  const check = await screen.findByRole('checkbox', { name: /总部/ });
  await waitFor(() => expect(check.getAttribute('aria-disabled')).toBe('false'));
  for (const count of [1, 3, 2, 0]) {
    await userEvent.click(check);
    await screen.findByText(`已选 ${count} 个部门`);
    expect(check.getAttribute('aria-checked')).toBe(count === 2 ? 'mixed' : String(count > 0));
    if (count) expect(screen.getByRole('img', { name: new RegExp(`^总部：.*已选 ${count} 个部门$`) }).textContent).toBe(String(count));
    else expect(screen.queryByRole('img', { name: /^总部：/ })).toBeNull();
  }
  expect(selectionBodies.filter(body => body.toggle_id).map(body => body.selected_ids)).toEqual([[], ['a'], ['a', 'b', 'c'], ['b', 'c']]);
  fireEvent.change(screen.getByPlaceholderText('搜索部门名称'), { target: { value: '民路' } });
  await screen.findByText('人民路店');
  expect(screen.getByText('区域')).toBeTruthy();
  fireEvent.change(screen.getByPlaceholderText('搜索部门名称'), { target: { value: '' } });
  await waitFor(() => expect(screen.queryByText('人民路店')).toBeNull());
  expect(screen.getByRole('img', { name: '展开总部' })).toBeTruthy();
  expect(screen.getByText('已选 0 个部门')).toBeTruthy();
}, 120000);

it('批量直接保存冲突保留草稿，重核显式目标后再次保存且不加入新部门', async () => {
  let version = 1; let saves = 0;
  const writes: any[] = [];
  const child = { ...department, id: 'b', name: '未加载分店', parent_id: 'a', path: ['组织', '总部', '未加载分店'], has_children: false };
  const rows = [department, child].map(row => ({ ...row, is_store: true, notes: row.id === 'a' ? '旧备注' : '分店备注' }));
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (url.includes('/organization/summary')) return envelope({ department_id: new URL(url, 'http://local').searchParams.get('department_id'), department_count: 123, employee_count: 45, unactivated_count: 2, unjoin_count: 3, resigned_count: 4, member_count: 45, members_limited: true });
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
    if (url.includes('/organization/employees')) return envelope([], { total_count: 0 });
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  const root = await screen.findByRole('checkbox', { name: /本组织/ });
  await waitFor(() => expect(root.getAttribute('aria-disabled')).toBe('false'));
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
    if (url.includes('/organization/summary')) return envelope({ department_id: new URL(url, 'http://local').searchParams.get('department_id'), department_count: 123, employee_count: 45, unactivated_count: 2, unjoin_count: 3, resigned_count: 4, member_count: 45, members_limited: true });
    if (url.includes('/organization/departments')) return envelope([department]);
    if (url.includes('/organization/employees')) {
      const params = new URL(url, 'http://local').searchParams;
      if (params.get('department_id') === '0') return envelope([], { total_count: 0 });
      employeeUrls.push(url);
      if (params.get('keyword') === '旧') return new Promise<Response>(resolve => { finishOld = resolve; });
      if (params.get('keyword') === '新') return envelope([{ ...employees[0], id: 'new', name: '新结果' }], { total_count: 1 });
      const offset = Number(params.get('cursor') || 0);
      return envelope(employees.slice(offset, offset + 20), { total_count: 45, next_cursor: offset < 40 ? String(offset + 20) : null });
    }
    if (url.includes('/organization/employees')) return envelope([], { total_count: 0 });
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


it('20人默认全部成员，切换直属与人员搜索不改变固定部门统计', async () => {
  const urls: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    urls.push(url);
    if (url.includes('/organization/departments')) return envelope([department]);
    if (url.includes('/organization/selection')) return envelope({ selected_ids: [], count: 0, states: {} });
    if (url.includes('/organization/summary')) return envelope({ department_id: new URL(url, 'http://local').searchParams.get('department_id'), department_count: 5, employee_count: 20, unactivated_count: 2, unjoin_count: 1, resigned_count: 0, member_count: 20, members_limited: false });
    if (url.includes('/organization/employees')) return envelope([], { total_count: 0 });
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  await waitFor(() => expect(urls.some(url => url.includes('/employees') && url.includes('include_descendants=true'))).toBe(true));
  await userEvent.click(screen.getByRole('combobox', { name: '展示成员' }));
  await userEvent.click(screen.getByText('部门直属成员', { selector: '.ant-select-item-option-content' }));
  await waitFor(() => expect(urls.some(url => url.includes('/employees') && url.includes('include_descendants=false'))).toBe(true));
  const summaryRequests = urls.filter(url => url.includes('/summary')).length;
  fireEvent.change(screen.getByPlaceholderText('搜索姓名、完整手机号或 USER_ID'), { target: { value: '不存在' } });
  await waitFor(() => expect(urls.some(url => url.includes('keyword=' + encodeURIComponent('不存在')))).toBe(true));
  expect(urls.filter(url => url.includes('/employees')).at(-1)).toContain('include_descendants=true');
  fireEvent.change(screen.getByPlaceholderText('搜索姓名、完整手机号或 USER_ID'), { target: { value: '' } });
  await waitFor(() => expect(urls.filter(url => url.includes('/employees')).at(-1)).toContain('include_descendants=false'));
  expect(urls.filter(url => url.includes('/summary'))).toHaveLength(summaryRequests);
  expect(screen.getByRole('region', { name: '部门统计' }).textContent).toContain('总人数20');
  expect(screen.queryByRole('radio')).toBeNull();
});

it('超过20人禁用全部成员并在下拉框上方提示，列表包含全部要求的字段', async () => {
  const urls: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    urls.push(url);
    if (url.includes('/organization/departments')) return envelope([department]);
    if (url.includes('/organization/selection')) return envelope({ selected_ids: [], count: 0, states: {} });
    if (url.includes('/organization/summary')) return envelope({ department_id: new URL(url, 'http://local').searchParams.get('department_id'), department_count: 5, employee_count: 21, unactivated_count: 2, unjoin_count: 1, resigned_count: 0, member_count: 21, members_limited: true });
    if (url.includes('/organization/employees')) return envelope([{ id: 'u', name: '测试员工', job_title: '工程师', email: 'person@example.test', mobile: '13800000000', field_readability: { email: 'readable', mobile: 'readable' }, employee_type_name: '正式员工', leader_name: '测试上级', departments: [] }], { total_count: 1 });
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  await screen.findByText('13800000000');
  expect(screen.queryByRole('tooltip')).toBeNull();
  expect(urls.filter(url => url.includes('/employees')).every(url => url.includes('include_descendants=false'))).toBe(true);
  for (const label of ['姓名', '账号状态', '手机号码', '直属上级', '部门', '人员类型', '职务', '门店属性', '权限角色', '操作']) expect(screen.getByRole('columnheader', { name: label })).toBeTruthy();
  expect(screen.getByText('工程师')).toBeTruthy();
  expect(screen.getByText('测试上级')).toBeTruthy();
  await userEvent.click(screen.getByRole('combobox', { name: '展示成员' }));
  expect((await screen.findByRole('tooltip')).textContent).toContain('当前部门人数较多，列表中将只展示部门直属成员，不再展示子部门成员');
  expect(screen.getByRole('option', { name: '部门全部成员' }).getAttribute('aria-disabled')).toBe('true');
  await userEvent.click(screen.getByText('部门直属成员', { selector: '.ant-select-item-option-content' }));
  await waitFor(() => expect(document.querySelector('.ant-tooltip:not(.ant-tooltip-hidden)')).toBeNull(), { timeout: 3000 });
  await userEvent.click(screen.getByRole('combobox', { name: '展示成员' }));
  expect((await screen.findByRole('tooltip')).textContent).toContain('当前部门人数较多，列表中将只展示部门直属成员，不再展示子部门成员');
  fireEvent.change(screen.getByPlaceholderText('搜索姓名、完整手机号或 USER_ID'), { target: { value: '下级' } });
  await waitFor(() => expect(urls.filter(url => url.includes('/employees')).at(-1)).toContain('include_descendants=true'));
  await waitFor(() => expect(document.querySelector('.ant-tooltip:not(.ant-tooltip-hidden)')?.textContent ?? '').not.toContain('当前部门人数较多'), { timeout: 3000 });
});
