import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import { TencentCostPage } from './TencentCostPage';

afterEach(() => vi.unstubAllGlobals());
it('管理员开启成本、受理单月后查看真实任务结果及精确负退款', async () => {
  let enabled = false; let accepted = false; let finished = false;
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, options: RequestInit) => {
    const method = options?.method ?? 'GET';
    const body = options?.body ? JSON.parse(String(options.body)) : undefined;
    calls.push({ path, method, body });
    let data: unknown;
    if (path === '/admin/api/tencent/accounts') data = [{ id:'1',alias:'主账号',uin:'10001',is_enabled:true,verification_status:'verified' }];
    else if (path.endsWith('/cost-config')) {
      if (method === 'PUT') enabled = body.is_enabled;
      data = { is_enabled:enabled,revision:enabled ? 1 : 0,frequency:'manual',currency:'CNY',latest_eligible_month:'2026-10' };
    } else if (path.endsWith('/cost-jobs') && method === 'POST') { accepted = true; data = { id:'7',month:'2026-10',status:'pending',attempts:[] }; }
    else if (path.endsWith('/cost-jobs')) data = accepted ? [{ id:'7',month:'2026-10',status:finished ? 'succeeded' : 'pending' }] : [];
    else if (path.endsWith('/cost-jobs/7')) data = { id:'7',month:'2026-10',status:finished ? 'succeeded' : 'pending',attempts:finished ? [{ id:'9',attempt_no:1,status:'succeeded',execution_input:{month:'2026-10',begin:'2026-10-01T00:00:00+08:00',end_exclusive:'2026-11-01T00:00:00+08:00'},execution_output:{row_count:2,total:'12.00000000',currency:'CNY',request_ids:['fixture']}}] : [] };
    else if (finished) data = { id:'3',month:'2026-10',currency:'CNY',total:'12.00000000',latest_job_id:'7',coverage:{status:'complete'},items:[{id:'1',source_name:'云服务',business_code:'p_cvm',mapping_status:'mapped',amount:'12.34567890'},{id:'2',source_name:'退款',business_code:null,mapping_status:'unmapped',amount:'-0.34567890'}] };
    else return new Response(JSON.stringify({error:{code:'TENCENT_PERIOD_NOT_FOUND',message:'该月尚无完整费用结果'}}),{status:404});
    return new Response(JSON.stringify({data,meta:{}}),{status:method === 'POST' ? 202 : 200});
  }));
  render(<App><TencentCostPage /></App>);
  expect(await screen.findByRole('switch',{name:'成本能力'})).not.toBeChecked();
  expect(screen.getByRole('button',{name:'采集所选账月'})).toBeDisabled();
  await waitFor(() => expect(screen.getByRole('switch',{name:'成本能力'})).toBeEnabled());
  fireEvent.click(screen.getByRole('switch',{name:'成本能力'}));
  fireEvent.click(screen.getByRole('button',{name:'保存配置'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'采集所选账月'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'采集所选账月'}));
  expect(await screen.findByText(/任务 #7 已受理/)).toBeVisible();
  expect(screen.queryByText('采集成功')).toBeNull();
  finished = true;
  fireEvent.click(screen.getByRole('button',{name:'刷新结果'}));
  expect(await screen.findByText('-0.34567890')).toBeVisible();
  expect(screen.getByText('12.00000000 CNY')).toBeVisible();
  expect(screen.getByText('完整月已覆盖')).toBeVisible();
  const post = calls.find(call => call.method === 'POST');
  expect(post?.body).toMatchObject({month:'2026-10'});
  expect(post?.body).not.toHaveProperty('actor_id');
  expect(screen.queryByRole('textbox',{name:/JSON|密钥/})).toBeNull();
});
