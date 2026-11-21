import { fireEvent, render, screen } from '@testing-library/react';
import { App, Button } from 'antd';
import { afterEach, expect, it } from 'vitest';
import { useWorkspaceSettings, WorkspaceSettings } from './WorkspaceSettings';

function Probe() { const value = useWorkspaceSettings(); return <><Button onClick={value.open}>打开布局</Button><output>{value.settings.contentWidth}</output></>; }
afterEach(() => localStorage.clear());
it('浏览器布局保存后重新挂载生效，恢复默认也持久化', () => {
  const first = render(<App><WorkspaceSettings><Probe /></WorkspaceSettings></App>);
  fireEvent.click(screen.getByText('打开布局'));
  fireEvent.click(screen.getByLabelText('固定'));
  fireEvent.click(screen.getByText('保存布局'));
  first.unmount();
  render(<App><WorkspaceSettings><Probe /></WorkspaceSettings></App>);
  expect(screen.getByText('Fixed')).toBeTruthy();
  fireEvent.click(screen.getByText('打开布局'));
  fireEvent.click(screen.getByText('恢复默认布局'));
  expect(screen.getByText('Fluid')).toBeTruthy();
  expect(JSON.parse(localStorage.getItem('evolution.workspace-layout.v1')!).contentWidth).toBe('Fluid');
});

it('迁移已保存的旧布局', () => {
  const legacyKey = 'organization.workspace-layout.v1';
  const saved = JSON.stringify({ contentWidth: 'Fixed', fixedHeader: false, fixSiderbar: true });
  localStorage.setItem(legacyKey, saved);
  render(<App><WorkspaceSettings><Probe /></WorkspaceSettings></App>);
  expect(screen.getByText('Fixed')).toBeTruthy();
  expect(localStorage.getItem('evolution.workspace-layout.v1')).toBe(saved);
  expect(localStorage.getItem(legacyKey)).toBeNull();
});
