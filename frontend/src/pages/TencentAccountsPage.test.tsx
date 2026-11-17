import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TencentAccountsPage } from './TencentAccountsPage';
import { request } from '../services/http';

vi.mock('../services/http', async original => ({ ...await original<typeof import('../services/http')>(), request: vi.fn() }));
beforeEach(() => {
  vi.mocked(request).mockImplementation(async (path, options) => {
    if (path === '/admin/api/tencent/credential-options') return {data:[{value:'finance-a',label:'财务只读凭据 A'}],meta:{}};
    if (options?.method === 'POST') return {data:{id:'1',uin:'10001',alias:'主账号',credential_ref:'finance-a',is_enabled:true,verification_status:'verified'},meta:{}};
    return {data:[],meta:{}};
  });
});
describe('腾讯云账号接入', () => {
  it('以中文表单选择受控凭据并验证登记，不录入密钥或JSON', async () => {
    render(<App><TencentAccountsPage /></App>);
    fireEvent.click(await screen.findByRole('button',{name:'登记账号'}));
    fireEvent.change(screen.getByLabelText('账号 UIN'), {target:{value:'10001'}});
    fireEvent.change(screen.getByLabelText('中文别名'), {target:{value:'主账号'}});
    fireEvent.mouseDown(screen.getByLabelText('只读凭据'));
    fireEvent.click(await screen.findByText('财务只读凭据 A'));
    fireEvent.click(screen.getByRole('button',{name:'验证并登记'}));
    await waitFor(() => expect(request).toHaveBeenCalledWith('/admin/api/tencent/accounts', {method:'POST', body:{uin:'10001',alias:'主账号',credential_ref:'finance-a'}}));
    expect(screen.queryByLabelText('SecretKey')).toBeNull();
    expect(screen.queryByRole('textbox',{name:/JSON/})).toBeNull();
  });
});

it('已登记账号提供余额入口，无须先配置成本同步', async () => {
  vi.mocked(request).mockImplementation(async path => ({data:path === '/admin/api/tencent/accounts' ? [{id:'42',uin:'10001',alias:'主账号',credential_ref:'finance-a',is_enabled:true,verification_status:'verified'}] : [],meta:{}}));
  render(<App><TencentAccountsPage /></App>);
  const link = await screen.findByRole('link',{name:'实时余额'});
  expect(link.getAttribute('href')).toBe('/tencent/accounts/42/balance');
});

it('维护别名时固定 UIN，并以当前维护修订保存，不轮换凭据', async () => {
  const account = {id:'42',uin:'10001',alias:'原别名',credential_ref:'finance-a',revision:3,credential_revision:2,is_enabled:true,verification_status:'verified'};
  vi.mocked(request).mockImplementation(async (path, options) => {
    if (path === '/admin/api/tencent/credential-options') return {data:[{value:'finance-a',label:'财务只读凭据 A'}],meta:{}};
    if (options?.method === 'PATCH') return {data:{...account,alias:'新别名',revision:4},meta:{}};
    return {data:[account],meta:{}};
  });
  render(<App><TencentAccountsPage /></App>);
  fireEvent.click(await screen.findByRole('button',{name:'维护账号'}));
  expect(screen.getByLabelText('账号 UIN').getAttribute('readonly')).not.toBeNull();
  fireEvent.change(screen.getByLabelText('中文别名'), {target:{value:'新别名'}});
  fireEvent.click(screen.getByRole('button',{name:'保存维护'}));
  await waitFor(() => expect(request).toHaveBeenCalledWith('/admin/api/tencent/accounts/42', {method:'PATCH',body:{revision:3,alias:'新别名'}}));
});
