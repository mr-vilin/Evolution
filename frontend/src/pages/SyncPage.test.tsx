import { App } from 'antd';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { SyncPage } from './SyncPage';
import { SyncJobPage } from './SyncJobPage';

function Address() { return <output aria-label="当前地址">{useLocation().pathname}</output>; }
afterEach(() => vi.unstubAllGlobals());
const meta = { dataset_epoch: 'e', data_version: 1, next_cursor: null };
function setup(path = '/sync') {
  render(<App><MemoryRouter initialEntries={[path]}><Address /><Routes><Route path="/sync" element={<SyncPage />} /><Route path="/sync/jobs/:id" element={<SyncJobPage />} /></Routes></MemoryRouter></App>);
}
it('旧任务链接进入独立详情，默认成员并能查看新增及关系变更', async () => {
  vi.stubGlobal('fetch', async (url: string) => {
    if (url === '/admin/api/sync/jobs/j1') return Response.json({ data: { job_id: 'j1', type: 'full', status: 'succeeded', phase: 'published', processed_count: 2, progress_total: 2, details: [
      { id: 1, object_type: 'employee', object_id: 'u', object_name: '测试成员', status: 'succeeded', action: 'create', changes: [{ id: 10, object_type: 'employee', before: null, after: { name: '测试成员' } }] },
      { id: 2, object_type: 'department', object_id: 'd', object_name: '测试部门', status: 'succeeded', action: 'unchanged', changes: [] },
    ] }, meta });
    if (url === '/admin/api/status') return Response.json({ data: { initialized_at: '2026-11-01T00:00:00Z', coverage_status: 'unknown', connection: { status: 'degraded' } }, meta });
    return Response.json({ data: [], meta });
  });
  setup('/sync?job=j1');
  expect(await screen.findByText('测试成员')).toBeTruthy();
  expect(screen.getByLabelText('当前地址').textContent).toBe('/sync/jobs/j1');
  expect(screen.getByText('新增')).toBeTruthy();
  expect(screen.queryByText('测试部门')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /展开行/ }));
  expect(await screen.findByRole('columnheader', { name: '变更字段' })).toBeTruthy();
  expect(screen.getByText('#10')).toBeTruthy();
  const user = userEvent.setup();
  await user.click(screen.getByRole('combobox', { name: '对象类型' }));
  await user.click(screen.getByText('部门（1）', { selector: '.ant-select-item-option-content' }));
  expect(await screen.findByText('测试部门')).toBeTruthy();
  expect(screen.getByText('无变化')).toBeTruthy();
});
it('列表显示业务信息及筛选，不再展示内部任务 ID 和事件面板', async () => {
  const paths: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    paths.push(url);
    if (url === '/admin/api/status') return Response.json({ data: { initialized_at: '2026-11-01T00:00:00Z', coverage_status: 'complete', sync_summary: { latest_job: { job_id: 'recent', status: 'succeeded' }, pending_object_count: 3 }, connection: { status: 'degraded' } }, meta });
    return Response.json({ data: [{ job_id: 'random-internal-id', type: 'full', status: 'running', phase: 'employees', trigger_label: '手动', executor_name: '测试人员', processed_count: 15, progress_total: 30, success_count: 10 }], meta });
  });
  setup();
  expect(await screen.findByText('测试人员')).toBeTruthy();
  expect(screen.getByText('已采集 15 / 30')).toBeTruthy();
  expect(screen.queryByText(/random-internal-id/)).toBeNull();
  expect(screen.queryByText('同步事件')).toBeNull();
  expect(screen.queryByText('连接摘要')).toBeNull();
  expect(screen.getByText('初始化日期')).toBeTruthy();
  expect(screen.getByRole('link', { name: '成功' }).getAttribute('href')).toBe('/sync/jobs/recent');
  expect(screen.getByText('待核实对象')).toBeTruthy();
  expect(screen.getByText('3')).toBeTruthy();
  expect(screen.queryByText('通讯录覆盖')).toBeNull();
  const user = userEvent.setup();
  await user.click(screen.getByRole('combobox', { name: '类型' }));
  await user.click(screen.getByText('局部同步任务', { selector: '.ant-select-item-option-content' }));
  await waitFor(() => expect(paths.some(path => path.includes('type=subtree'))).toBe(true));
  expect(paths.some(path => path.includes('/sync/events'))).toBe(false);
});
it('活动详情轮询到完成后停止，保留分批入库信息', async () => {
  let reads = 0;
  vi.stubGlobal('fetch', async () => {
    reads += 1;
    return Response.json({ data: { job_id: 'j1', type: 'reconcile', status: reads === 1 ? 'running' : 'succeeded', details: [], success_count: 50 }, meta });
  });
  setup('/sync/jobs/j1');
  expect(await screen.findByText('执行中')).toBeTruthy();
  expect(screen.getByText('已入库 50 · 待核验 0')).toBeTruthy();
  await waitFor(() => expect(screen.getByText('成功')).toBeTruthy(), { timeout: 10000 });
});
