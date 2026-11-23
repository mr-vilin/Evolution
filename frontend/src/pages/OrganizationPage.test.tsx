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
  expect(screen.queryByRole('checkbox')).toBeNull();
  expect(screen.queryByRole('button', { name: '批量设置' })).toBeNull();
  expect(urls.some(url => url.includes('/organization/selection'))).toBe(false);
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

it('搜索展开匹配部门及其祖先，清空后恢复原展开状态', async () => {
  vi.stubGlobal('fetch', async (url: string) => {
    if (url.includes('/organization/summary')) return envelope({ department_id: '0', member_count: 0 });
    if (url.includes('/organization/search')) return envelope([
      department,
      { ...department, id: 'b', parent_id: 'a', name: '区域' },
      { ...department, id: 'c', parent_id: 'b', name: '人民路店', has_children: false },
    ], { matched_ids: ['c'] });
    if (url.includes('/organization/departments')) return envelope([department]);
    if (url.includes('/organization/employees')) return envelope([], { total_count: 0 });
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  await screen.findByText('总部');
  const input = screen.getByPlaceholderText('搜索部门名称');
  fireEvent.change(input, { target: { value: '民路' } });
  await screen.findByText('人民路店');
  expect(screen.getByText('区域')).toBeTruthy();
  fireEvent.change(input, { target: { value: '' } });
  await waitFor(() => expect(screen.queryByText('人民路店')).toBeNull());
  expect(screen.getByRole('img', { name: '展开总部' })).toBeTruthy();
}, 120000);

it('人员跨三批滚动续载，切换条件忽略旧响应并重置列表', async () => {
  const employeeUrls: string[] = [];
  let finishOld: ((response: Response) => void) | undefined;
  const employees = Array.from({ length: 45 }, (_, index) => ({ id: `u${index}`, user_id: `u${index}`, name: `成员${index}`, status: 'active', primary_store_status: 'unknown' }));
  vi.stubGlobal('fetch', async (url: string) => {
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
  await screen.findByText('共45人');
  await screen.findByText('成员19');
  const tableBody = screen.getByRole('region', { name: '部门人员列表' }).querySelector('.ant-table-body')!;
  fireEvent.scroll(tableBody);
  await screen.findByText('成员39');
  fireEvent.scroll(tableBody);
  await screen.findByText('成员44');
  expect(employeeUrls).toHaveLength(3);
  fireEvent.scroll(tableBody);
  expect(employeeUrls).toHaveLength(3);
  const input = screen.getByPlaceholderText('搜索姓名、完整手机号或user_id');
  fireEvent.change(input, { target: { value: '旧' } });
  await waitFor(() => expect(finishOld).toBeTruthy());
  fireEvent.change(input, { target: { value: '新' } });
  await screen.findByText('新结果');
  await act(async () => { finishOld!(envelope([{ ...employees[1], name: '迟到结果' }], { total_count: 45, next_cursor: '20' })); });
  expect(screen.queryByText('迟到结果')).toBeNull();
  expect(screen.getByText('共1人')).toBeTruthy();
}, 120000);


it('20人默认全部成员，切换直属与人员搜索不改变固定部门统计', async () => {
  const urls: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    urls.push(url);
    if (url.includes('/organization/departments')) return envelope([department]);
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
  fireEvent.change(screen.getByPlaceholderText('搜索姓名、完整手机号或user_id'), { target: { value: '不存在' } });
  await waitFor(() => expect(urls.some(url => url.includes('keyword=' + encodeURIComponent('不存在')))).toBe(true));
  // 展示范围保持直属；后端搜索独立扩展到下级。
  expect(urls.filter(url => url.includes('/employees')).at(-1)).toContain('include_descendants=false');
  fireEvent.change(screen.getByPlaceholderText('搜索姓名、完整手机号或user_id'), { target: { value: '' } });
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
  fireEvent.change(screen.getByPlaceholderText('搜索姓名、完整手机号或user_id'), { target: { value: '下级' } });
  await waitFor(() => expect(urls.filter(url => url.includes('/employees')).at(-1)).toContain('keyword=' + encodeURIComponent('下级')));
  await waitFor(() => expect(document.querySelector('.ant-tooltip:not(.ant-tooltip-hidden)')?.textContent ?? '').not.toContain('当前部门人数较多'), { timeout: 3000 });
});

it('部门下拉数标按成员范围更新，面板始终显示全组织汇总', async () => {
  const summaryUrls: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    const params = new URL(url, 'http://local').searchParams;
    if (url.includes('/organization/departments')) return envelope([department]);
    if (url.includes('/organization/summary')) {
      summaryUrls.push(url);
      const root = params.get('department_id') === '0';
      return envelope({ department_id: params.get('department_id'), department_count: root ? 99 : 2, employee_count: root ? 120 : 10,
        unactivated_count: root ? 25 : 1, unjoin_count: root ? 4 : 0, resigned_count: root ? 3 : 0, member_count: root ? 120 : 10, members_limited: root });
    }
    if (url.includes('/organization/employees')) return envelope([], { total_count: 0, account_status_counts:
      { activated: params.get('include_descendants') === 'true' ? 8 : 2, unactivated: 1, frozen: 0, unjoin: 0, unknown: 1 } });
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  await userEvent.click(await screen.findByText('总部'));
  await screen.findByRole('button', { name: '查看部门详情' });
  expect(screen.getByRole('region', { name: '部门统计' }).textContent).toContain('总人数120');
  expect(summaryUrls.filter(url => url.includes('department_id=0'))).toHaveLength(1);
  await userEvent.click(screen.getByRole('combobox', { name: '账号状态' }));
  await waitFor(() => expect(document.querySelector('.org-account-option')?.textContent).toBe('全部账号状态'));
  expect(document.querySelectorAll('.org-account-option .ant-badge')).toHaveLength(5);
  expect([...document.querySelectorAll('.org-account-option')].find(el => el.textContent?.startsWith('已激活'))?.textContent).toBe('已激活8');
  await userEvent.click(screen.getByText('全部账号状态', { selector: '.org-account-option > span' }));
  await userEvent.click(screen.getByRole('combobox', { name: '展示成员' }));
  await userEvent.click(screen.getByText('部门直属成员', { selector: '.ant-select-item-option-content' }));
  await userEvent.click(screen.getByRole('combobox', { name: '账号状态' }));
  await waitFor(() => expect([...document.querySelectorAll('.org-account-option')].find(el => el.textContent?.startsWith('已激活'))?.textContent).toBe('已激活2'));
  expect(screen.getByRole('region', { name: '部门统计' }).textContent).toContain('总人数120');
});

it('面板状态查看锁定筛选，20人滚动加载、状态内搜索，再次点击恢复本组织', async () => {
  const urls: string[] = [];
  const employees = Array.from({ length: 45 }, (_, i) => ({ id: `p${i}`, name: `面板人员${i}`, status: 'inactive' }));
  let finishOld: ((response: Response) => void) | undefined;
  vi.stubGlobal('fetch', async (url: string) => {
    urls.push(url);
    const params = new URL(url, 'http://local').searchParams;
    if (url.includes('/organization/departments')) return envelope([department]);
    if (url.includes('/organization/summary')) return envelope({ department_id: params.get('department_id'), department_count: 5,
      employee_count: 45, unactivated_count: 45, unjoin_count: 1, resigned_count: 0, member_count: 45, members_limited: true });
    if (url.includes('/organization/employees')) {
      if (params.get('view_status') === 'unactivated') {
        if (params.get('keyword') === '迟到') return new Promise<Response>(resolve => { finishOld = resolve; });
        if (params.get('keyword')) return envelope([employees[3]], { total_count: 1 });
        const offset = Number(params.get('cursor') || 0);
        return envelope(employees.slice(offset, offset + 20), { total_count: 45, next_cursor: offset < 40 ? String(offset + 20) : null });
      }
      return envelope([], { total_count: 0 });
    }
    throw new Error(url);
  });
  render(<App><MemoryRouter><OrganizationPage /></MemoryRouter></App>);
  await userEvent.click(await screen.findByText('总部'));
  const view = screen.getByRole('button', { name: '查看未激活人员' });
  await userEvent.hover(view);
  expect((await screen.findByRole('tooltip')).textContent).toBe('查看全组织未激活人员');
  await userEvent.click(view);
  await screen.findByText('面板人员19');
  expect(screen.getByRole('heading', { name: '未激活' })).toBeTruthy();
  expect(screen.getByText('共45人')).toBeTruthy();
  expect(view.getAttribute('aria-pressed')).toBe('true');
  expect(view.closest('.org-stat-cell')?.classList.contains('org-stat-selected')).toBe(true);
  expect((screen.getByRole('combobox', { name: '账号状态' }) as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByRole('combobox', { name: '展示成员' }) as HTMLInputElement).disabled).toBe(true);
  expect(urls.filter(url => url.includes('/employees')).at(-1)).toContain('department_id=0');
  const body = screen.getByRole('region', { name: '部门人员列表' }).querySelector('.ant-table-body')!;
  fireEvent.scroll(body); await screen.findByText('面板人员39');
  fireEvent.scroll(body); await screen.findByText('面板人员44');
  const input = screen.getByPlaceholderText('搜索姓名、完整手机号或user_id');
  fireEvent.change(input, { target: { value: '查找' } });
  await screen.findByText('共1人');
  expect(screen.queryByText('面板人员19')).toBeNull();
  expect(urls.filter(url => url.includes('/employees')).at(-1)).toContain('view_status=unactivated');
  fireEvent.change(input, { target: { value: '迟到' } });
  await waitFor(() => expect(finishOld).toBeTruthy());
  await userEvent.click(screen.getByRole('button', { name: '查看未加入人员' }));
  await screen.findByRole('heading', { name: '未加入' });
  await act(async () => { finishOld!(envelope([employees[44]], { total_count: 45, next_cursor: '20' })); });
  expect(screen.queryByText('面板人员44')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: '查看已离职人员' }));
  await screen.findByRole('heading', { name: '已离职' });
  expect(screen.getByText('共0人')).toBeTruthy();
  await userEvent.click(screen.getByRole('button', { name: '查看已离职人员' }));
  await screen.findByRole('heading', { name: '本组织' });
  expect((screen.getByRole('combobox', { name: '账号状态' }) as HTMLInputElement).disabled).toBe(false);
  expect((screen.getByRole('combobox', { name: '展示成员' }) as HTMLInputElement).disabled).toBe(false);
  expect((input as HTMLInputElement).value).toBe('');
  await waitFor(() => expect(urls.filter(url => url.includes('/employees')).at(-1)).toContain('view_status=none'));
  expect(urls.filter(url => url.includes('/employees')).every(url => url.includes('limit=20'))).toBe(true);
}, 120000);
