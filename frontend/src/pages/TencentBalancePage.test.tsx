import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Link } from '@umijs/max';
import { AuthGate } from '../components/AuthGate';
import { act } from '@testing-library/react';
afterEach(() => vi.restoreAllMocks());
import { TencentBalancePage } from './TencentBalancePage';

function result(amount = '90071992547409.9112345678') {
  return {data:{account_id:'1',uin:'10001',alias:'主账号',currency:'CNY',unit:'yuan',currency_source:'国内站财务账本配置',
    queried_at:'2026-11-17T03:04:05Z',amounts:{real_balance:amount,cash_account_balance:'120.005',income_into_account_balance:'1.00',
    present_account_balance:'0.25',freeze_amount:'0.05',owe_amount:'0.00',credit_amount:'200.00',credit_balance:'320.005',real_credit_balance:'319.955'}},meta:{}};
}
function show() {
  return render(<App><MemoryRouter initialEntries={['/tencent/accounts/1/balance']}><Routes>
    <Route path="/tencent/accounts/:id/balance" element={<TencentBalancePage />} />
  </Routes></MemoryRouter></App>);
}

describe('腾讯云实时余额', () => {
  it('进入即查询，精确显示主余额与各资金口径、查询时间；刷新失败后清空旧值', async () => {
    const fetcher = vi.spyOn(globalThis,'fetch').mockResolvedValueOnce(new Response(JSON.stringify(result()),{status:200}));
    show();
    expect(await screen.findByText('90071992547409.9112345678')).toBeInTheDocument();
    expect(screen.getByText('真实可用余额')).toBeInTheDocument();
    expect(screen.getByText('现金账户余额')).toBeInTheDocument();
    expect(screen.getByText('信用额度')).toBeInTheDocument();
    expect(screen.getByText(/2026-11-17 11:04:05/)).toBeInTheDocument();
    expect(screen.getAllByText(/人民币（CNY）/).length).toBeGreaterThan(0);
    expect(fetcher).toHaveBeenCalledTimes(1);
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({error:{code:'TENCENT_TIMEOUT',message:'腾讯云查询超时'}}),{status:504}));
    await waitFor(() => expect(screen.getByRole('button',{name:'刷新余额'})).not.toHaveClass('ant-btn-loading'));
    fireEvent.click(screen.getByRole('button',{name:'刷新余额'}));
    expect(screen.queryByText('90071992547409.9112345678')).not.toBeInTheDocument();
    expect(await screen.findByText('腾讯云查询超时')).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});

it('切换账号后丢弃迟到的旧账号响应，并取消离开页面的请求', async () => {
  let finishOld!: (response:Response) => void;
  let oldSignal:AbortSignal | undefined;
  vi.spyOn(globalThis,'fetch').mockImplementation((path,options) => {
    if (String(path).includes('/1/')) {
      oldSignal = options?.signal as AbortSignal;
      return new Promise(resolve => {finishOld=resolve;});
    }
    const next = result('222.00'); next.data.account_id='2'; next.data.uin='20002';
    return Promise.resolve(Response.json(next));
  });
  const view = render(<App><MemoryRouter initialEntries={['/tencent/accounts/1/balance']}>
    <Link to="/tencent/accounts/2/balance">切换账号</Link>
    <Routes><Route path="/tencent/accounts/:id/balance" element={<TencentBalancePage />} /></Routes>
  </MemoryRouter></App>);
  await waitFor(() => expect(finishOld).toBeTypeOf('function'));
  fireEvent.click(screen.getByRole('link',{name:'切换账号'}));
  expect(await screen.findByText('222.00')).toBeInTheDocument();
  expect(oldSignal?.aborted).toBe(true);
  await act(async () => {finishOld(Response.json(result()));});
  expect(screen.queryByText('90071992547409.9112345678')).not.toBeInTheDocument();
  view.unmount();
});

it('未完成初始化时只呈现初始化向导，不发起余额查询', async () => {
  const fetcher = vi.spyOn(globalThis,'fetch').mockImplementation(async path => Response.json({data:
    path === '/admin/auth/session' ? {open_id:'admin',csrf_token:'csrf',initialization_complete:false}
      : {flow_id:'test',phase:'ready',complete:false,checks:[],settings:{}},meta:{}}));
  render(<App><MemoryRouter><AuthGate><TencentBalancePage /></AuthGate></MemoryRouter></App>);
  expect(await screen.findByText('企业组织数据初始化')).toBeInTheDocument();
  expect(fetcher.mock.calls.every(([path]) => !String(path).includes('/balance'))).toBe(true);
});

it('刷新发现初始化资格失效时移除资金并回到初始化向导', async () => {
  let sessionCalls=0, balanceCalls=0;
  vi.spyOn(globalThis,'fetch').mockImplementation(async path => {
    if (path === '/admin/auth/session') return Response.json({data:{open_id:'admin',csrf_token:'csrf',initialization_complete:++sessionCalls===1},meta:{}});
    if (String(path).includes('/balance')) return ++balanceCalls===1 ? Response.json(result())
      : Response.json({error:{code:'INITIALIZATION_INCOMPLETE',message:'请重新初始化'}},{status:409});
    return Response.json({data:{flow_id:'test',phase:'ready',complete:false,checks:[],settings:{}},meta:{}});
  });
  render(<App><MemoryRouter initialEntries={['/tencent/accounts/1/balance']}><AuthGate><Routes>
    <Route path="/tencent/accounts/:id/balance" element={<TencentBalancePage />} />
  </Routes></AuthGate></MemoryRouter></App>);
  expect(await screen.findByText('90071992547409.9112345678')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole('button',{name:'刷新余额'})).not.toHaveClass('ant-btn-loading'));
  fireEvent.click(screen.getByRole('button',{name:'刷新余额'}));
  expect(await screen.findByText('企业组织数据初始化')).toBeInTheDocument();
  expect(screen.queryByText('90071992547409.9112345678')).not.toBeInTheDocument();
});