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
  await screen.findByText('主账号');
  const link = screen.getByLabelText('实时余额');
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
  await screen.findByText('原别名');
  fireEvent.click(screen.getByLabelText('维护账号'));
  expect(screen.getByLabelText('账号 UIN').getAttribute('readonly')).not.toBeNull();
  fireEvent.change(screen.getByLabelText('中文别名'), {target:{value:'新别名'}});
  fireEvent.click(screen.getByRole('button',{name:'保存维护'}));
  await waitFor(() => expect(request).toHaveBeenCalledWith('/admin/api/tencent/accounts/42', {method:'PATCH',body:{revision:3,alias:'新别名'}}));
});

it('时间按完整数据排序后分页，保留同值顺序、缺失置底及刷新排序', async () => {
  const rows=Array.from({length:22},(_,i)=>({id:String(i+1),uin:String(10000+i),alias:`排序账号${i}`,credential_ref:'finance-a',is_enabled:true,verification_status:'verified',
    verified_at:i===0?null:i<3?'2026-11-17T00:00:01Z':`2026-11-${String(16-i%12).padStart(2,'0')}T00:00:00Z`,create_time:`2026-10-${String(i+1).padStart(2,'0')}T00:00:00Z`}));
  vi.mocked(request).mockImplementation(async path=>({data:path==='/admin/api/tencent/accounts'?rows:[],meta:{}}));
  const {container}=render(<App><TencentAccountsPage /></App>);
  await screen.findByText('排序账号0');
  const names=()=>Array.from(container.querySelectorAll('.ant-table-tbody tr[data-row-key]')).map(row=>row.getAttribute('data-row-key'));
  fireEvent.click(screen.getByRole('columnheader',{name:/验证时间/}));
  expect(names()).toHaveLength(20);expect(names()).not.toContain('1');
  fireEvent.click(screen.getByRole('columnheader',{name:/验证时间/}));
  expect(names().slice(0,2)).toEqual(['2','3']);expect(names()).not.toContain('1');
  fireEvent.click(screen.getByRole('button',{name:'刷新'}));
  await waitFor(()=>expect(names().slice(0,2)).toEqual(['2','3']));
  fireEvent.click(screen.getByRole('columnheader',{name:/登记时间/}));
  expect(names()[0]).toBe('1');
  expect(screen.getAllByText('2026-11-17 08:00:01')).toHaveLength(2);
});
