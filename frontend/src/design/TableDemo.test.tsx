import '@testing-library/jest-dom/vitest';
import { App, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import TableDemo from './TableDemo';

describe('表格演示的样本切换与新增', () => {
  it('零基础样本新增后立即可见，切换样本保留记录和查询条件', async () => {
    const user = userEvent.setup();
    const view = (count: number) => <ConfigProvider locale={zhCN}><App><TableDemo recordLimit={count} /></App></ConfigProvider>;
    const { rerender } = render(view(0));
    expect(screen.getByText('暂无数据', { selector: '.ant-empty-description' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /新\s*增/ }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByRole('textbox', { name: '名称' }), '新增可见记录');
    await user.click(within(dialog).getByRole('button', { name: /保\s*存/ }));
    await waitFor(() => expect(document.querySelector('tr[data-row-key="demo-local-1"]')).toHaveTextContent('新增可见记录'));
    expect(screen.queryByText('暂无数据', { selector: '.ant-empty-description' })).not.toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('搜索名称或负责人'), '新增可见记录{Enter}');
    rerender(view(2));
    await waitFor(() => expect(document.querySelectorAll('tr[data-row-key]')).toHaveLength(1));
    expect(screen.getByPlaceholderText('搜索名称或负责人')).toHaveValue('新增可见记录');
    rerender(view(0));
    expect(document.querySelector('tr[data-row-key="demo-local-1"]')).toHaveTextContent('新增可见记录');
  });
});
