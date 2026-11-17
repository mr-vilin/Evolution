import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import { TencentCostDashboardPage } from './TencentCostDashboardPage';

afterEach(() => vi.unstubAllGlobals());
const data = {account:{id:'1',uin:'10001',alias:'主账号'},start_month:'2026-08',end_month:'2026-10',currency:'CNY',
  known_total:'12.34567890',complete_total:null,coverage_complete:false,
  months:[{month:'2026-08',total:'0.00000000',status:'complete',coverage_complete:true,latest_success_at:'2026-11-01T00:00:00Z',mom:{value:null,reason:'incomplete_coverage'},yoy:{value:null,reason:'incomplete_coverage'}},
    {month:'2026-09',total:'12.34567890',status:'failed_retained',coverage_complete:true,latest_success_at:'2026-11-01T00:00:00Z',mom:{value:null,reason:'zero_denominator'},yoy:{value:null,reason:'incomplete_coverage'}},
    {month:'2026-10',total:null,status:'missing',coverage_complete:false,latest_success_at:null,mom:{value:null,reason:'incomplete_coverage'},yoy:{value:null,reason:'incomplete_coverage'}}],
  products:Array.from({length:12},(_,i)=>({key:String(i),source_name:`产品${i}`,business_code:`code${i}`,mapping_status:'mapped',total:'1.02880657',amounts:{'2026-08':'0.00000000','2026-09':'1.02880657','2026-10':null}}))};

it('呈现精确金额、缺口、有效零和不可比原因；全量产品搜索及刷新保留条件', async () => {
  const paths:string[]=[];
  vi.stubGlobal('fetch',vi.fn(async (path:string) => {paths.push(path); return new Response(JSON.stringify({data:path.endsWith('/accounts') ? [{id:'1',alias:'主账号',uin:'10001',is_enabled:true}] : data,meta:{}}));}));
  render(<App><TencentCostDashboardPage /></App>);
  expect(await screen.findByText('12.34567890 CNY')).toBeVisible();
  expect(screen.getByText('费用存在缺口或待复核结果，完整范围总额暂不可用')).toBeVisible();
  expect(screen.getAllByText('未同步 / 缺口').length).toBeGreaterThan(0);
  expect(screen.getByText('-（对照月为零）')).toBeVisible();
  expect(screen.getAllByText('0.00000000').length).toBeGreaterThan(0);
  fireEvent.change(screen.getByLabelText('搜索费用产品'),{target:{value:'产品11'}});
  expect(await screen.findByText('产品11')).toBeVisible();
  expect(screen.queryByText('产品0')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'刷新看板'}));
  await waitFor(() => expect(paths.filter(path=>path.includes('cost-dashboard')).length).toBe(2));
  expect(await screen.findByLabelText('搜索费用产品')).toHaveValue('产品11');
  expect(screen.getByRole('button',{name:'导出全部产品'})).toBeEnabled();
  expect(paths.every(path=>!path.includes('/balance')&&!path.includes('cost-jobs'))).toBe(true);
});

it('查询失败显示重试并隐藏旧结果，导出不可用', async () => {
  let fail=false;
  vi.stubGlobal('fetch',vi.fn(async (path:string) => {
    if(path.endsWith('/accounts')) return new Response(JSON.stringify({data:[{id:'1',alias:'主账号',uin:'10001',is_enabled:true}],meta:{}}));
    return fail ? new Response(JSON.stringify({error:{code:'FAILED',message:'费用读取失败'}}),{status:503}) : new Response(JSON.stringify({data,meta:{}}));
  }));
  render(<App><TencentCostDashboardPage /></App>);
  expect(await screen.findByText('12.34567890 CNY')).toBeVisible();
  fail=true; fireEvent.click(screen.getByRole('button',{name:'刷新看板'}));
  expect(await screen.findByText('费用读取失败')).toBeVisible();
  expect(screen.queryByText('12.34567890 CNY')).toBeNull();
  expect(screen.getByRole('button',{name:'导出全部产品'})).toBeDisabled();
});
