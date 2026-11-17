import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import { TencentCostHistoryPanel } from './TencentCostHistoryPanel';

afterEach(() => vi.unstubAllGlobals());
it('管理员区分未知起点与缺口，预览整月扩展后按原意图受理范围重拉', async () => {
  const posts: Array<{path:string;body:Record<string,unknown>}> = [];
  vi.stubGlobal('fetch',vi.fn(async(path:string,options:RequestInit) => {
    const body=options?.body ? JSON.parse(String(options.body)) : null;
    if(body)posts.push({path,body});
    const data=path.endsWith('/cost-history') ? {
      origin_status:'unknown',first_bill_period:null,earlier_history_unknown:true,
      source_window:{day_start:'2026-05-17',month_start:'2025-11',end_exclusive:'2026-11-17',basis:'官方来源能力窗口'},
      target_period_count:180,covered_period_count:2,earliest_success_period:'2026-02',last_success_at:'2026-11-17T03:00:00Z',
      continuous_coverage:null,recent:{required_count:47,covered_count:1},pending_count:3,discovery_status:'partial',
      gaps:[{period_key:'2026-08-01',granularity:'day',reason_code:'TENCENT_COST_ZERO_UNCONFIRMED',category:'zero_unconfirmed',last_attempt_at:null,automatic_failures:3,automatic_paused:true}],
      unexplored:[{period_key:'2026-01',granularity:'month'}],
    } : path.endsWith('/cost-range-preview') ? {
      periods:[{period_key:'2026-02',granularity:'month',month:'2026-02'},{period_key:'2026-03-05',granularity:'day',month:'2026-03'}],
      requested_scope:body,expanded:true,not_due:[],outside_known_source_window:[],total_count:2,preview_token:'preview-fixture',
    } : {id:'80',kind:'batch',month:null,status:'pending',scope_status:'pending',deferred_periods:['2026-03-05']};
    return new Response(JSON.stringify({data,meta:{}}),{status:path.endsWith('/cost-range-batches') ? 202 : 200});
  }));
  const accepted=vi.fn();
  render(<App><TencentCostHistoryPanel accountId="1" enabled onAccepted={accepted} /></App>);
  expect(await screen.findByText('账号费用发生起点未知')).toBeVisible();
  expect(screen.getByText('零费用未确认')).toBeVisible();
  expect(screen.getByText('自动探测已暂停，可人工重探')).toBeVisible();
  expect(screen.getByText(/^尚未探测 1 个期间/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('重拉开始日期'),{target:{value:'2026-02-14'}});
  fireEvent.change(screen.getByLabelText('重拉结束日期'),{target:{value:'2026-03-05'}});
  fireEvent.click(screen.getByRole('button',{name:'预览实际执行范围'}));
  expect(await screen.findByText('命中完整月，实际范围已扩展')).toBeVisible();
  expect(screen.getByText('2026-02（完整月）')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'确认范围重拉'}));
  await waitFor(()=>expect(accepted).toHaveBeenCalledWith('80'));
  expect(posts[1].body).toMatchObject({start_date:'2026-02-14',end_date:'2026-03-05',preview_token:'preview-fixture'});
  expect(posts[1].body.idempotency_key).toBe(posts[0].body.idempotency_key);
  expect(screen.getByText(/范围重拉批次 #80 已受理/)).toBeVisible();
  expect(screen.queryByRole('textbox',{name:/JSON/})).toBeNull();
});


it('受理结果未知时重复确认沿用原请求键，配置冲突后必须重新预览', async () => {
  const accepted=vi.fn(); const attempts:Array<Record<string,unknown>>=[];
  let previews=0;
  vi.stubGlobal('fetch',vi.fn(async(path:string,options:RequestInit)=>{
    const body=options?.body ? JSON.parse(String(options.body)):{};
    if(path.endsWith('/cost-history'))return new Response(JSON.stringify({data:{origin_status:'unknown',first_bill_period:null,earlier_history_unknown:true,source_window:{day_start:'2026-06-01',month_start:'2025-11',end_exclusive:'2026-11-17',basis:'fixture'},target_period_count:1,covered_period_count:0,earliest_success_period:null,last_success_at:null,continuous_coverage:null,recent:{required_count:1,covered_count:0},pending_count:0,discovery_status:'pending',gaps:[],unexplored:[]},meta:{}}));
    if(path.endsWith('/cost-range-preview')){previews++;return new Response(JSON.stringify({data:{periods:[{period_key:'2026-02',granularity:'month',month:'2026-02'}],requested_scope:body,expanded:false,not_due:[],outside_known_source_window:[],total_count:1,preview_token:String(previews)},meta:{}}));}
    attempts.push(body);
    if(attempts.length===1)throw new Error('connection-lost');
    return new Response(JSON.stringify({error:{code:'TENCENT_RANGE_PREVIEW_CHANGED',message:'配置、世代或实际范围已变化，请重新预览'}}),{status:409});
  }));
  render(<App><TencentCostHistoryPanel accountId="1" enabled onAccepted={accepted}/></App>);
  fireEvent.change(screen.getByLabelText('重拉开始日期'),{target:{value:'2026-02-14'}});
  fireEvent.change(screen.getByLabelText('重拉结束日期'),{target:{value:'2026-02-15'}});
  fireEvent.click(screen.getByRole('button',{name:'预览实际执行范围'}));
  fireEvent.click(await screen.findByRole('button',{name:'确认范围重拉'}));
  expect(await screen.findByText('无法连接服务，请检查后端是否启动后重试')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'确认范围重拉'}));
  expect(await screen.findByText('配置、世代或实际范围已变化，请重新预览')).toBeVisible();
  expect(attempts[1].idempotency_key).toBe(attempts[0].idempotency_key);
  expect(screen.queryByRole('button',{name:'确认范围重拉'})).toBeNull();
  expect(accepted).not.toHaveBeenCalled();
});
