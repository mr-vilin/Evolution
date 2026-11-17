import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { expect, it, vi } from 'vitest';
import { TencentAccountMaintenance } from './TencentAccountMaintenance';
import { request } from '../services/http';
import type { TencentAccount } from './TencentAccountsPage';

vi.mock('../services/http', async original => ({...await original<typeof import('../services/http')>(), request:vi.fn()}));
const account: TencentAccount = {id:'42',uin:'10001',alias:'主账号',credential_ref:'finance-a',revision:7,credential_revision:4,is_enabled:true,verification_status:'verified',verified_at:'2026-11-17T00:00:00Z',create_time:'2026-11-17T00:00:00Z',update_time:'2026-11-17T00:00:00Z'};

it('账号总开关说明在途隔离与历史保留，并只提交启停变化', async () => {
  vi.mocked(request).mockResolvedValue({data:{...account,is_enabled:false},meta:{}});
  const saved = vi.fn();
  render(<App><TencentAccountMaintenance account={account} onCancel={() => {}} onSaved={saved} /></App>);
  expect(screen.getByText(/停用将阻止新的余额查询和成本执行/)).not.toBeNull();
  fireEvent.click(screen.getByRole('switch',{name:'账号总开关'}));
  fireEvent.click(screen.getByRole('button',{name:'保存维护'}));
  await waitFor(() => expect(request).toHaveBeenCalledWith('/admin/api/tencent/accounts/42',{method:'PATCH',body:{revision:7,is_enabled:false}}));
  await waitFor(() => expect(saved).toHaveBeenCalled());
});

it('从受控选项轮换同一 UIN 的凭据，并区分辅助账单准备中', async () => {
  vi.mocked(request).mockResolvedValue({data:{...account,credential_ref:'finance-b'},meta:{verification:{auxiliary_readiness:'not_ready'}}});
  const saved = vi.fn();
  render(<App><TencentAccountMaintenance account={account} credentialOptions={[{value:'finance-b',label:'财务只读凭据 B'}]} onCancel={() => {}} onSaved={saved} /></App>);
  fireEvent.mouseDown(screen.getByLabelText('轮换只读凭据'));
  fireEvent.click(await screen.findByText('财务只读凭据 B'));
  fireEvent.click(screen.getByRole('button',{name:'保存维护'}));
  await waitFor(() => expect(request).toHaveBeenCalledWith('/admin/api/tencent/accounts/42',{method:'PATCH',body:{revision:7,credential_ref:'finance-b'}}));
  await waitFor(() => expect(saved).toHaveBeenCalledWith('凭据轮换成功；辅助账单仍在准备中，后续成本采集会单独核验就绪状态。'));
  expect(screen.queryByLabelText('SecretKey')).toBeNull();
});

it('并发冲突保留输入并要求刷新，防止用过时维护修订覆盖账号', async () => {
  const { ApiError } = await import('../services/http');
  vi.mocked(request).mockRejectedValue(new ApiError(409,'TENCENT_ACCOUNT_CONFLICT','账号已变更，请刷新后重试'));
  const saved = vi.fn();
  const reload = vi.fn();
  render(<App><TencentAccountMaintenance account={account} onCancel={() => {}} onSaved={saved} onReload={reload} /></App>);
  fireEvent.change(screen.getByLabelText('中文别名'),{target:{value:'待保存别名'}});
  fireEvent.click(screen.getByRole('button',{name:'保存维护'}));
  expect(await screen.findByText('账号已变更，请刷新后重试')).not.toBeNull();
  expect((screen.getByLabelText('中文别名') as HTMLInputElement).value).toBe('待保存别名');
  expect((screen.getByRole('button',{name:'保存维护'}) as HTMLButtonElement).disabled).toBe(true);
  expect(saved).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'刷新账号后重新维护'}));
  expect(reload).toHaveBeenCalledOnce();
});
