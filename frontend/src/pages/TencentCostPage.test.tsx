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
    else if (finished) data = { id:'3',month:'2026-10',currency:'CNY',total:'12.00000000',latest_job_id:'7',coverage:{status:'complete'},items:[{id:'1',source_name:'云服务',business_code:'p_synthetic_a',mapping_status:'mapped',amount:'12.34567890'},{id:'2',source_name:'退款',business_code:null,mapping_status:'unmapped',amount:'-0.34567890'}] };
    else return new Response(JSON.stringify({error:{code:'TENCENT_PERIOD_NOT_FOUND',message:'该月尚无完整费用结果'}}),{status:404});
    return new Response(JSON.stringify({data,meta:{}}),{status:method === 'POST' ? 202 : 200});
  }));
  render(<App><TencentCostPage /></App>);
  expect(await screen.findByRole('switch',{name:'成本能力'})).not.toBeChecked();
  expect(screen.getByRole('button',{name:'采集所选账月'})).toBeDisabled();
  await waitFor(() => expect(screen.getByRole('switch',{name:'成本能力'})).toBeEnabled());
  fireEvent.click(screen.getByRole('switch',{name:'成本能力'}));
  fireEvent.click(screen.getByRole('button',{name:'保存配置'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'采集所选账月'})).toBeEnabled(), { timeout: 5000 });
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


it('管理员用结构化数值设置执行预算并在保存前看到心跳字段校验', async () => {
  const puts: unknown[]=[];
  vi.stubGlobal('fetch',vi.fn(async (path: string,options: RequestInit) => {
    let data: unknown;
    if (path==='/admin/api/tencent/accounts') data=[{id:'1',alias:'主账号',uin:'10001',is_enabled:true}];
    else if (path.endsWith('/cost-config')) {
      if (options?.method==='PUT') puts.push(JSON.parse(String(options.body)));
      data={revision:1,is_enabled:true,frequency:'manual',currency:'CNY',latest_eligible_month:'2026-10'};
    } else if (path.endsWith('/cost-jobs')) data=[];
    else return new Response(JSON.stringify({error:{code:'TENCENT_PERIOD_NOT_FOUND',message:'尚无完整费用'}}),{status:404});
    return new Response(JSON.stringify({data,meta:{}}));
  }));
  render(<App><TencentCostPage /></App>);
  fireEvent.click(await screen.findByText('重试与执行限制'));
  const heartbeat=await screen.findByRole('spinbutton',{name:'心跳间隔（秒）'});
  fireEvent.change(heartbeat,{target:{value:'60'}});
  fireEvent.blur(heartbeat);
  await waitFor(() => expect(screen.getByText('心跳间隔不能超过租约的三分之一')).toBeVisible());
  fireEvent.click(screen.getByRole('button',{name:'保存配置'}));
  await waitFor(() => expect(puts).toHaveLength(0));
  fireEvent.change(heartbeat,{target:{value:'20'}});
  fireEvent.blur(heartbeat);
  fireEvent.click(screen.getByRole('button',{name:'保存配置'}));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(puts[0]).toMatchObject({run_policy:{heartbeat_seconds:20,max_attempts:3,queue_deadline_seconds:86400}});
  expect(screen.queryByRole('textbox',{name:/JSON/})).toBeNull();
});

it('管理员编辑北京时间月计划并立即执行，查看父批次的部分失败和逐月结果', async () => {
  const puts: Array<Record<string,unknown>>=[];
  let accepted=false;
  const batch={id:'40',kind:'batch',month:null,status:'partial_failed',attempts:[],deferred_months:['2024-01'],
    children:[{id:'41',kind:'period',month:'2026-10',status:'succeeded'},{id:'42',kind:'period',month:'2026-09',status:'failed',error_code:'TENCENT_PERMISSION_DENIED'}]};
  vi.stubGlobal('fetch',vi.fn(async (path: string,options: RequestInit) => {
    let data: unknown;
    if (path==='/admin/api/tencent/accounts') data=[{id:'1',alias:'主账号',uin:'10001',is_enabled:true}];
    else if (path.endsWith('/cost-config')) {
      if(options?.method==='PUT')puts.push(JSON.parse(String(options.body)));
      data={revision:1,is_enabled:true,frequency:'monthly',currency:'CNY',execution_time:'13:30',latest_eligible_month:'2026-10',last_success_month:'2026-09',next_execution_at:'2026-12-03T05:30:00+00:00'};
    } else if(path.endsWith('/cost-batches')) {accepted=true;data=batch;}
    else if(path.endsWith('/cost-jobs'))data=accepted?[batch]:[];
    else if(path.endsWith('/cost-jobs/40'))data=batch;
    else if(path.endsWith('/cost-jobs/42'))data={...batch.children[1],attempts:[]};
    else return new Response(JSON.stringify({error:{code:'TENCENT_PERIOD_NOT_FOUND',message:'尚无完整费用'}}),{status:404});
    return new Response(JSON.stringify({data,meta:{}}),{status:options?.method==='POST'?202:200});
  }));
  render(<App><TencentCostPage /></App>);
  const time=await screen.findByLabelText('北京时间执行时刻');
  fireEvent.change(time,{target:{value:'14:20'}});
  fireEvent.click(screen.getByRole('button',{name:'保存配置'}));
  await waitFor(()=>expect(puts[0]).toMatchObject({frequency:'monthly',execution_time:'14:20'}));
  await waitFor(()=>expect(screen.getByLabelText('北京时间执行时刻')).toHaveValue('13:30'));
  expect(screen.getByText('最近成功账月')).toBeVisible();
  await waitFor(()=>expect(screen.getByRole('button',{name:'立即执行月度复核'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'立即执行月度复核'}));
  await waitFor(()=>expect(accepted).toBe(true));
  expect(await screen.findByText('父批次仅汇总账月结果，不产生执行尝试')).toBeVisible();
  expect(screen.getAllByText('部分失败，仍有缺口')[0]).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'查看账月 2026-09'}));
  expect(await screen.findByText('#42 / 2026-09')).toBeVisible();
  expect(screen.queryByRole('textbox',{name:/JSON/})).toBeNull();
});

it('管理员切换每日与每周日计划并查看真实单日失败', async () => {
  let frequency='monthly';const puts: Array<Record<string,unknown>>=[];
  const batch={id:'60',kind:'batch',month:null,status:'partial_failed',attempts:[],
    blocked_periods:[{period_key:'2026-08-01',reason_code:'TENCENT_PERIOD_AUTO_BUDGET_EXHAUSTED'}],
    children:[{id:'61',kind:'period',month:'2026-11',period_key:'2026-11-16',granularity:'day',status:'failed',error_code:'TENCENT_COST_ZERO_UNCONFIRMED'}]};
  vi.stubGlobal('fetch',vi.fn(async(path:string,options:RequestInit)=>{
    let data:unknown;
    if(path==='/admin/api/tencent/accounts')data=[{id:'1',alias:'主账号',uin:'10001',is_enabled:true}];
    else if(path.endsWith('/cost-config')){
      if(options?.method==='PUT'){const body=JSON.parse(String(options.body));puts.push(body);frequency=body.frequency;}
      data={revision:puts.length+1,is_enabled:true,frequency,currency:'CNY',execution_time:'13:30',latest_eligible_month:'2026-10',latest_eligible_date:'2026-11-16'};
    }else if(path.endsWith('/cost-batches'))data=batch;
    else if(path.endsWith('/cost-jobs'))data=[batch];
    else if(path.endsWith('/cost-jobs/60'))data=batch;
    else if(path.endsWith('/cost-jobs/61'))data={...batch.children[0],attempts:[]};
    else return new Response(JSON.stringify({error:{code:'TENCENT_PERIOD_NOT_FOUND',message:'尚无完整费用'}}),{status:404});
    return new Response(JSON.stringify({data,meta:{}}),{status:options?.method==='POST'?202:200});
  }));
  render(<App><TencentCostPage /></App>);
  const select=await screen.findByRole('combobox',{name:'采集方式'});
  fireEvent.mouseDown(select);
  fireEvent.click(await screen.findByText('每日自动采集，截至昨日'));
  fireEvent.click(screen.getByRole('button',{name:'保存配置'}));
  await waitFor(()=>expect(puts[0]).toMatchObject({frequency:'daily'}));
  await waitFor(()=>expect(screen.getByText('空日与全零日尚缺独立就绪证据，保留原费用并显示未确认缺口。')).toBeVisible());
  expect(await screen.findByRole('button',{name:'查看期间 2026-11-16'})).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'查看期间 2026-11-16'}));
  expect(await screen.findByText('#61 / 2026-11-16（单日）')).toBeVisible();
  expect(screen.getByText('TENCENT_COST_ZERO_UNCONFIRMED')).toBeVisible();
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'采集方式'}));
  fireEvent.click(await screen.findByText('每周日自动采集，截至昨日'));
  fireEvent.click(screen.getByRole('button',{name:'保存配置'}));
  await waitFor(()=>expect(puts[1]).toMatchObject({frequency:'weekly'}));
});

it('日模式旧月份详情展示原始日累计和缺口，不误报完整月', async () => {
  vi.stubGlobal('fetch',vi.fn(async(path:string)=>{
    let data:unknown;
    if(path==='/admin/api/tencent/accounts')data=[{id:'1',alias:'主账号',uin:'10001',is_enabled:true}];
    else if(path.endsWith('/cost-config'))data={revision:1,is_enabled:true,frequency:'daily',currency:'CNY',latest_eligible_month:'2026-10',last_success_period:'2026-10-31'};
    else if(path.endsWith('/cost-jobs'))data=[];
    else data={id:'daily:2026-10',month:'2026-10',granularity:'day',currency:'CNY',total:'12.00000000',coverage:{status:'incomplete'},covered_through:'2026-10-31',missing_dates:['2026-10-01'],latest_job_id:'7',items:[]};
    return new Response(JSON.stringify({data,meta:{}}));
  }));
  render(<App><TencentCostPage /></App>);
  expect(await screen.findByText('原始日费用累计；累计至 2026-10-31，缺 1 日')).toBeVisible();
  expect(screen.getByText('累计未完整')).toBeVisible();
  expect(screen.queryByText('完整月已覆盖')).toBeNull();
  expect(screen.getByText('2026-10-31')).toBeVisible();
});
