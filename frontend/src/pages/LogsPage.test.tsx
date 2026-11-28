import { App } from 'antd';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LogsPage } from './LogsPage';

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => vi.unstubAllGlobals());

const record = {
  id: 1, object_id: 'u1', object_name: '测试员工', object_type: 'employee',
  source: 'event', action: 'update', event_id: 'e1',
  committed_at: '2026-11-27T01:00:00Z',
  changes: [
    { field: 'job_title', before: '专员', after: '主管' },
    { field: 'email', before: 'old@example.test', after: null },
    { field: 'avatar_url', before: null, after: 'https://example.test/' + 'a'.repeat(360) },
    { field: 'permission_role_id', before: 'role-old', after: 'role-new' },
    { field: 'employee_type_id', before: 'type-a', after: 'type-b' },
    { field: 'employee_type_name', before: '正式', after: '兼职' },
    { field: 'is_virtual_root', before: false, after: true },
    { field: 'permission_role_name', before: '店员', after: '店长' },
    { field: 'primary_department_id', before: '原门店', after: '新门店' },
    { field: 'membership:d1', before: '主部门', after: null },
    { field: 'name', before: '测试员工', after: '测试员工' },
  ],
  actor: '测试执行人', actor_is_user: true, actor_avatar_url: 'https://example.test/avatar.png',
  department_change: { field: 'departments', before: [
    { id: 'd1', name: '原门店', primary: true }, { id: 'd2', name: '其他门店', primary: false },
  ], after: [{ id: 'd3', name: '新门店', primary: true }] },
  raw_records: [{ id: 1, object_type: 'employee', before: { name: '测试员工', job_title: '专员' }, after: { name: '测试员工', job_title: '主管' } }],
};

const departmentRecord = {
  ...record, id: 2, object_id: 'd1', object_type: 'department', object_name: '运营部',
  changes: [{ field: 'leader_user_id', before: 'unresolved-leader', after: 'leader',
    after_person: { name: '部门负责人', avatar_url: 'https://example.test/leader.png' } }],
  department_change: null,
};

function setup(initialPath = '/logs') {
  const urls: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    urls.push(url);
    const params = new URL(url, 'http://local').searchParams;
    if (url === '/admin/api/status') return Response.json({ data: { connection: { status: 'disconnected' } }, meta: {} });
    if (params.get('object_type') === 'department') return Response.json({ data: [departmentRecord], meta: { total: 1 } });
    if (params.get('view') === 'grouped') return Response.json({ data: [
      { object_id: 'u1', object_name: '测试员工', total: 8, records: [record] },
    ], meta: { total: 1 } });
    return Response.json({ data: [record], meta: { total: 1 } });
  });
  render(<App><MemoryRouter initialEntries={[initialPath]}><Routes><Route path="/logs" element={<LogsPage />} /></Routes></MemoryRouter></App>);
  return urls;
}

it('默认员工，按固定中文来源和操作筛选，部门单独查询', async () => {
  const urls = setup();
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  expect(await screen.findByText('测试员工')).toBeTruthy();
  expect(screen.getByText('人员')).toBeTruthy();
  expect(urls.some(url => url.includes('object_type=employee'))).toBe(true);
  await user.click(screen.getByRole('combobox', { name: '变更来源' }));
  await user.click(screen.getByText('全量校准任务', { selector: '.ant-select-item-option-content' }));
  await user.click(screen.getByRole('combobox', { name: '变更类型' }));
  await user.click(screen.getByText('停用', { selector: '.ant-select-item-option-content' }));
  await waitFor(() => expect(urls.at(-1)).toContain('action=deactivate'));
  expect(urls.at(-1)).toContain('source=reconcile');
  await user.click(screen.getByRole('combobox', { name: '对象类型' }));
  await user.click(screen.getByText('部门', { selector: '.ant-select-item-option-content' }));
  await waitFor(() => expect(urls.at(-1)).toContain('object_type=department'));
  expect(screen.queryByText('测试员工')).toBeNull();
});

it('支持行内部门差异和执行人头像', async () => {
  const urls = setup();
  expect(await screen.findByText('测试员工')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /展开行/ }));
  expect(await screen.findByText('职位')).toBeTruthy();
  const detailTable = document.querySelector<HTMLTableElement>('.change-detail-table table')!;
  expect(detailTable.style.tableLayout).toBe('fixed');
  expect(detailTable.style.width).toBe('620px');
  expect([...detailTable.querySelectorAll('col')].map(col => col.style.width)).toEqual(['180px', '220px', '220px']);
  expect(screen.getByText('专员')).toBeTruthy();
  expect(screen.getByText('权限角色', { selector: 'td' })).toBeTruthy();
  expect(screen.getByText('店员')).toBeTruthy();
  expect(screen.getByText('店长')).toBeTruthy();
  expect(screen.queryByText('权限角色 ID')).toBeNull();
  expect(screen.queryByText('role-old')).toBeNull();
  expect(screen.queryByText('员工类型 ID')).toBeNull();
  expect(screen.queryByText('is_virtual_root')).toBeNull();
  expect(screen.getByText('员工类型', { selector: 'td' })).toBeTruthy();
  expect(screen.getByAltText('变更后头像').getAttribute('src')).toBe(record.changes[2].after);
  expect(screen.queryByText(record.changes[2].after as string)).toBeNull();
  expect(screen.getByText('部门', { selector: 'td' })).toBeTruthy();
  expect(screen.getByText('原门店')).toBeTruthy();
  expect(screen.getByText('其他门店')).toBeTruthy();
  expect(screen.getByText('新门店')).toBeTruthy();
  expect(screen.getAllByText('主部门')).toHaveLength(2);
  expect(screen.getAllByText('主部门')[1].getAttribute('style')).toContain('--app-primary');
  expect(screen.getByText('/', { selector: '[aria-hidden="true"]' })).toBeTruthy();
  const deletedValue = screen.getByText('old@example.test').closest('td')?.nextElementSibling?.querySelector('span');
  expect(deletedValue?.textContent).toBe('-');
  expect(deletedValue?.getAttribute('style')).toContain('--app-accent');
  expect(screen.queryByRole('button', { name: '复制事件 ID' })).toBeNull();
  expect(screen.queryByPlaceholderText('执行人')).toBeNull();
  expect(screen.getByPlaceholderText('开始时间')).toBeTruthy();
  expect(screen.getByPlaceholderText('结束时间')).toBeTruthy();
  expect(screen.getByAltText('测试执行人的头像')).toBeTruthy();
});

it('支持原始记录 JSON 对比和完整 JSON 复制', async () => {
  userEvent.setup();
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText');
  const app = vi.spyOn(App, 'useApp').mockReturnValue({ message: { success: vi.fn() } } as unknown as ReturnType<typeof App.useApp>);
  setup();
  expect(await screen.findByText('测试员工')).toBeTruthy();
  const rawButton = document.querySelector<HTMLButtonElement>('[aria-label="原始记录"]')!;
  expect(rawButton.querySelector('.anticon-file-text')).toBeTruthy();
  fireEvent.mouseEnter(rawButton);
  await waitFor(() => expect(rawButton.classList.contains('ant-tooltip-open')).toBe(true));
  expect(document.querySelector('.ant-tooltip-open')?.getAttribute('aria-label')).toBe('原始记录');
  fireEvent.click(rawButton);
  const title = screen.getByText('原始记录 JSON').closest('.ant-modal-title');
  expect(title?.querySelector('.ant-tag')?.textContent).toBe('1');
  const modal = title?.closest('.ant-modal');
  expect(modal?.querySelector('.raw-change-summary')?.textContent)
    .toBe('测试员工·飞书订阅事件·2026-11-27 09:00:00');
  expect(screen.getByText('人员信息')).toBeTruthy();
  fireEvent.click(modal!.querySelector('[aria-label="复制变更前 JSON"]')!);
  expect(clipboard).toHaveBeenCalledWith(JSON.stringify(record.raw_records[0].before, null, 2));
  fireEvent.click(modal!.querySelector('[aria-label="复制变更后 JSON"]')!);
  expect(clipboard).toHaveBeenCalledWith(JSON.stringify(record.raw_records[0].after, null, 2));
  clipboard.mockRestore();
  app.mockRestore();

  expect(document.querySelector('.raw-change-after')?.textContent).toContain('主管');
  fireEvent.click(document.querySelector('.ant-modal-close')!);
  fireEvent.focus(rawButton);
  await waitFor(() => expect(rawButton.classList.contains('ant-tooltip-open')).toBe(false));
  fireEvent.mouseMove(rawButton);
  await waitFor(() => expect(rawButton.classList.contains('ant-tooltip-open')).toBe(true));
});

it('按对象查看使用主子表、共享差异和原始记录，独立历史可返回聚合列表', async () => {
  const urls = setup();
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  expect(await screen.findByText('测试员工')).toBeTruthy();
  expect(screen.getByText('断开').closest('.ant-tabs-extra-content')).toBeTruthy();
  await user.click(screen.getByRole('combobox', { name: '变更来源' }));
  await user.click(screen.getByText('全量校准任务', { selector: '.ant-select-item-option-content' }));
  await user.click(screen.getByRole('combobox', { name: '变更类型' }));
  await user.click(screen.getByText('停用', { selector: '.ant-select-item-option-content' }));
  fireEvent.click(screen.getByText('按对象查看'));
  expect(await screen.findByText('记录总数', { selector: 'th' })).toBeTruthy();
  const groupedUrl = urls.filter(url => url.includes('view=grouped')).at(-1)!;
  expect(groupedUrl).toBeTruthy();
  expect(groupedUrl).not.toContain('source=');
  expect(groupedUrl).not.toContain('action=');
  expect(document.querySelector('[aria-label="变更来源"]')).toBeNull();
  expect(document.querySelector('[aria-label="变更类型"]')).toBeNull();
  expect(screen.getByText('最近变更时间', { selector: 'th' })).toBeTruthy();
  expect(screen.getByText('断开').closest('.ant-tabs-extra-content')).toBeTruthy();
  fireEvent.click(document.querySelector('[aria-label="展开最近5条"]')!);
  expect(await screen.findByText('飞书订阅事件')).toBeTruthy();
  expect(screen.getAllByText('对象名称', { selector: 'th' })).toHaveLength(1);
  expect(screen.getByText('变更来源', { selector: 'th' })).toBeTruthy();
  expect(screen.getByAltText('测试执行人的头像')).toBeTruthy();
  fireEvent.click(document.querySelector('.ant-table-row-expand-icon-collapsed')!);
  expect(await screen.findByText('新门店')).toBeTruthy();
  expect(screen.getAllByText('主部门')[1].getAttribute('style')).toContain('--app-primary');
  expect(screen.getByText('店长')).toBeTruthy();
  expect(screen.queryByText('权限角色 ID')).toBeNull();
  fireEvent.click(document.querySelector('[aria-label="原始记录"]')!);
  expect(screen.getByText('原始记录 JSON')).toBeTruthy();
  fireEvent.click(document.querySelector('.ant-modal-close')!);
  fireEvent.click(document.querySelector('[aria-label="查看全部 8 条记录"]')!);
  expect(await screen.findByText('对象变更记录')).toBeTruthy();
  await waitFor(() => expect(urls.some(url => url.includes('object_id=u1') && url.includes('view=all'))).toBe(true));
  fireEvent.click(screen.getByText('返回列表'));
  expect(await screen.findByText('记录总数', { selector: 'th' })).toBeTruthy();
});

it('部门负责人使用人员头像和姓名，无法解析时显示原始 ID', async () => {
  setup('/logs?object_type=department');
  expect(await screen.findByText('运营部')).toBeTruthy();
  fireEvent.click(document.querySelector('.ant-table-row-expand-icon-collapsed')!);
  expect(await screen.findByText('部门负责人')).toBeTruthy();
  expect(screen.getByAltText('部门负责人的头像')).toBeTruthy();
  expect(screen.getByText('unresolved-leader')).toBeTruthy();
  expect(screen.queryByText('leader')).toBeNull();
});
