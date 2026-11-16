import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { OrganizationStoreEditor } from './OrganizationStoreEditor';

afterEach(() => vi.unstubAllGlobals());

it('批量保存阻止重复请求，并将服务端编码错误显示在对应部门行', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  let finish: ((response: Response) => void) | undefined;
  const fetch = vi.fn(() => new Promise<Response>(resolve => { finish = resolve; }));
  vi.stubGlobal('fetch', fetch);
  const departments = ['a', 'b'].map(id => ({ id, parent_id: '0', name: id, path: ['组织', id], status: 'active' as const, is_virtual_root: false, is_store: true, store_code: id, notes: null }));
  render(<App><OrganizationStoreEditor open ready initial={{ departments, meta: { dataset_epoch: 'e', data_version: 1 } }}
    onClose={vi.fn()} onConflict={vi.fn()} onRecheck={vi.fn()} onSaved={vi.fn()} /></App>);
  const save = await screen.findByRole('button', { name: '保存' });
  // 同一事件批次内重复点击，覆盖异步表单验证尚未完成的窗口。
  act(() => { fireEvent.click(save); fireEvent.click(save); });
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  await act(async () => { finish!(Response.json({ error: { code: 'VALIDATION_ERROR', message: '请检查门店设置', fields: [
    { department_id: 'b', code: 'STORE_CODE_DUPLICATE', message: '门店编码已存在' },
  ] } }, { status: 422 })); });
  const error = await screen.findByText('门店编码已存在');
  expect(error.closest('section')?.textContent).toContain('组织 / b');
  expect(screen.getAllByLabelText('门店编码')[1].getAttribute('aria-invalid')).toBe('true');
}, 120000);
