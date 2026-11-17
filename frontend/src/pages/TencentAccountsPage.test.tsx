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
