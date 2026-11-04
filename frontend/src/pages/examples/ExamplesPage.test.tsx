import { fireEvent, render, screen, within } from '@testing-library/react';
import { App } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import ListExample from './ListExample';

afterEach(() => vi.unstubAllGlobals());

it('案例列表可以本地新增和删除，重新打开恢复样本且不发出业务请求', async () => {
  const fetch = vi.fn(() => Promise.reject(new Error('案例不应发出请求')));
  vi.stubGlobal('fetch', fetch);
  const page = () => <App><ListExample /></App>;
  const first = render(page());
  fireEvent.click(screen.getByText('新增演示条目'));
  fireEvent.change(screen.getByLabelText('条目名称'), { target: { value: '独立本地样本' } });
  fireEvent.click(screen.getByText('保存演示条目'));
  await screen.findByText('独立本地样本');
  const row = screen.getByText('独立本地样本').closest('tr')!;
  fireEvent.click(within(row).getByText(/删\s*除/));
  expect(screen.queryByText('独立本地样本')).toBeNull();
  fireEvent.click(within(screen.getByText('演示项目 1').closest('tr')!).getByText(/删\s*除/));
  expect(screen.queryByText('演示项目 1')).toBeNull();
  first.unmount();
  render(page());
  expect(screen.getByText('演示项目 1')).toBeTruthy();
  expect(fetch).not.toHaveBeenCalled();
});
