import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import { TencentCostJobDetail } from './TencentCostJobDetail';

afterEach(() => vi.unstubAllGlobals());
it('区分逻辑任务和逐次事实，展示完整脱敏输入及真实回执，人工重跑关联原任务', async () => {
  const requests: Array<{ path: string; body: unknown }> = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, options: RequestInit) => {
    requests.push({ path, body: JSON.parse(String(options.body)) });
    return new Response(JSON.stringify({ data: { id: '8', source_job_id: '7', status: 'pending' }, meta: {} }), { status: 202 });
  }));
  const next = vi.fn();
  render(<App><TencentCostJobDetail canRerun onRerun={next} job={{ id: '7', month: '2026-10', status: 'succeeded', source_job_id: '4', attempts: [
    { id: 'a', attempt_no: 1, status: 'unknown', return_state: 'UNKNOWN', error_code: 'TENCENT_COST_EXECUTOR_LOST', finished_at: null,
      execution_input: { month: '2026-10', policy: { max_attempts: 3 }, upstream_params: { PeriodType: 'month' } }, execution_output: null },
    { id: 'b', attempt_no: 2, status: 'succeeded', return_state: 'VALUE', execution_input: { month: '2026-10', config_revision: 2 },
      execution_output: { status: 'committed', row_count: 2, total: '12.00000000', currency: 'CNY', request_ids: ['original-id-a', 'original-id-b'] } },
  ] }} /></App>);
  expect(screen.getByText('逻辑任务状态')).toBeVisible();
  expect(screen.getAllByText('已成功提交')[0]).toBeVisible();
  expect(screen.getByText('original-id-a')).toBeVisible();
  expect(screen.getByText('original-id-b')).toBeVisible();
  fireEvent.click(screen.getByText(/第 1 次尝试/));
  await waitFor(() => expect(screen.getAllByText('返回结果未知，尚无可核实返回')[0]).toBeVisible());
  expect(screen.getByText('最大总尝试次数')).toBeVisible();
  expect(screen.getByText('TENCENT_COST_EXECUTOR_LOST')).toBeVisible();
  expect(screen.queryByRole('textbox')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '人工重跑' }));
  await waitFor(() => expect(next).toHaveBeenCalledWith('8'));
  expect(requests[0].path).toBe('/admin/api/tencent/cost-jobs/7/rerun');
  expect(requests[0].body).toMatchObject({ reason: 'after_fix' });
  expect(requests[0].body).not.toHaveProperty('actor_id');
});

it('范围批次单片成功仍披露延期及未知历史，不宣称全范围完成', () => {
  render(<App><TencentCostJobDetail canRerun={false} onRerun={vi.fn()} job={{
    id:'90',kind:'batch',month:null,status:'succeeded',scope_status:'pending',earlier_history_unknown:true,
    requested_scope:{scope:'range',start_date:'2026-02-14',end_date:'2026-03-05'},
    periods:[{period_key:'2026-02',month:'2026-02',granularity:'month'}],
    deferred_periods:['2026-03-05'],children:[],
  }} /></App>);
  expect(screen.getByText('本片已完成，申请范围仍未全部覆盖')).toBeVisible();
  expect(screen.getByText('2026-02-14 至 2026-03-05（含结束日）')).toBeVisible();
  expect(screen.getByText('2026-02（完整月）')).toBeVisible();
  expect(screen.getByText('账号费用发生起点仍未知，更早历史待评估')).toBeVisible();
});
