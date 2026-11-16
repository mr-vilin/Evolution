import { useEffect } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App, Button, Modal, theme } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import { ThemeProvider, useThemeColors } from './ThemeProvider';
import { defaultColors, themeStorageKey } from './colors';
import DesignStandardsPage from '../pages/DesignStandardsPage';

afterEach(() => { localStorage.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function Probe({ mount }: { mount: () => void }) {
  const { colors, setColor, saveColor, resetColor, reset, storageError } = useThemeColors();
  const { token } = theme.useToken();
  useEffect(mount, [mount]);
  return <><output data-testid="tokens">{JSON.stringify({ primary: token.colorPrimary, hover: token.colorPrimaryHover, canvas: token.colorBgLayout, surface: token.colorBgElevated, text: token.colorText, muted: token.colorTextSecondary, line: token.colorBorderSecondary, auxiliary: colors.auxiliary, accent: colors.accent })}</output>
    <Button onClick={() => setColor('primary', '#722ED1')}>改主色</Button><Button onClick={() => setColor('accent', '#234567')}>改点睛色</Button><Button onClick={() => saveColor('primary')}>确认主色</Button><Button onClick={() => resetColor('primary')}>重置主色</Button><Button onClick={() => resetColor('accent')}>重置点睛色</Button><Button aria-label="重置颜色" onClick={reset}>重置</Button><p>{storageError}</p>
    <Modal open title="浮层验证" footer={null}><Button type="primary">浮层主按钮</Button></Modal></>;
}

it('动态主题不重新挂载内容，派生色、全局 CSS、弹窗和刷新后的颜色一致', () => {
  const mount = vi.fn();
  const first = render(<ThemeProvider><App><Probe mount={mount} /></App></ThemeProvider>);
  const before = JSON.parse(screen.getByTestId('tokens').textContent!);
  fireEvent.click(screen.getByText('改主色'));
  const after = JSON.parse(screen.getByTestId('tokens').textContent!);
  expect(after.primary.toUpperCase()).toBe('#722ED1');
  expect(after.hover).not.toBe(before.hover);
  expect(document.documentElement.style.getPropertyValue('--app-primary')).toBe('#722ED1');
  expect(document.documentElement.style.getPropertyValue('--color-primary-hover')).toBe(after.hover);
  expect(mount).toHaveBeenCalledTimes(1);
  expect(screen.getByText('浮层主按钮')).toBeTruthy();
  expect(localStorage.getItem(themeStorageKey)).toBeNull();
  fireEvent.click(screen.getByText('确认主色'));
  first.unmount();
  render(<ThemeProvider><App><Probe mount={mount} /></App></ThemeProvider>);
  expect(JSON.parse(screen.getByTestId('tokens').textContent!).primary.toUpperCase()).toBe('#722ED1');
  fireEvent.click(screen.getByRole('button', { name: '重置颜色' }));
  expect(JSON.parse(localStorage.getItem(themeStorageKey)!)).toEqual(defaultColors);
});

it('恢复合法的八种职责色，过滤损坏配置并响应其他标签页恢复默认', () => {
  localStorage.setItem(themeStorageKey, JSON.stringify({ ...defaultColors, primary: 'invalid', canvas: '#f1ede4', surface: '#fffaf0', text: '#182834', muted: '#637788', line: '#d6c9b7', auxiliary: '#205c66', accent: '#a74612' }));
  render(<ThemeProvider><App><Probe mount={() => {}} /></App></ThemeProvider>);
  expect(JSON.parse(screen.getByTestId('tokens').textContent!)).toMatchObject({ primary: defaultColors.primary.toLowerCase(), canvas: '#F1EDE4', surface: '#FFFAF0', text: '#182834', muted: '#637788', line: '#D6C9B7', auxiliary: '#205C66', accent: '#A74612' });
  fireEvent(window, new StorageEvent('storage', { key: themeStorageKey, newValue: null }));
  expect(JSON.parse(screen.getByTestId('tokens').textContent!)).toMatchObject({ canvas: defaultColors.canvas, surface: defaultColors.surface });
});

it('预览刷新会丢弃，确认单个职责不会保存其他草稿，重置恢复最近保存值', () => {
  localStorage.setItem(themeStorageKey, JSON.stringify({ ...defaultColors, primary: '#123456' }));
  const first = render(<ThemeProvider><App><Probe mount={() => {}} /></App></ThemeProvider>);
  fireEvent.click(screen.getByText('改主色'));
  fireEvent.click(screen.getByText('改点睛色'));
  fireEvent.click(screen.getByText('重置主色'));
  expect(document.documentElement.style.getPropertyValue('--app-primary')).toBe('#123456');
  fireEvent.click(screen.getByText('改主色'));
  fireEvent.click(screen.getByText('确认主色'));
  expect(JSON.parse(localStorage.getItem(themeStorageKey)!)).toMatchObject({ primary: '#722ED1', accent: defaultColors.accent });
  expect(document.documentElement.style.getPropertyValue('--app-accent')).toBe('#234567');
  first.unmount();
  render(<ThemeProvider><App><Probe mount={() => {}} /></App></ThemeProvider>);
  expect(document.documentElement.style.getPropertyValue('--app-primary')).toBe('#722ED1');
  expect(document.documentElement.style.getPropertyValue('--app-accent')).toBe(defaultColors.accent);
});

it('其他标签页确认后，保留本页未确认草稿，重置采用最新保存值', () => {
  render(<ThemeProvider><App><Probe mount={() => {}} /></App></ThemeProvider>);
  fireEvent.click(screen.getByText('改点睛色'));
  fireEvent(window, new StorageEvent('storage', { key: themeStorageKey, newValue: JSON.stringify({ ...defaultColors, primary: '#123456', accent: '#ABCDEF' }) }));
  expect(document.documentElement.style.getPropertyValue('--app-primary')).toBe('#123456');
  expect(document.documentElement.style.getPropertyValue('--app-accent')).toBe('#234567');
  fireEvent.click(screen.getByText('重置点睛色'));
  expect(document.documentElement.style.getPropertyValue('--app-accent')).toBe('#ABCDEF');
});

it('存储失败保留预览并允许重试或重置，不把失败值视为已保存', () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('disabled'); });
  render(<ThemeProvider><App><Probe mount={() => {}} /></App></ThemeProvider>);
  fireEvent.click(screen.getByText('改主色'));
  fireEvent.click(screen.getByText('确认主色'));
  expect(JSON.parse(screen.getByTestId('tokens').textContent!).primary.toUpperCase()).toBe('#722ED1');
  expect(screen.getByText(/浏览器无法保存颜色/)).toBeTruthy();
  fireEvent.click(screen.getByText('重置主色'));
  expect(document.documentElement.style.getPropertyValue('--app-primary')).toBe(defaultColors.primary);
  fireEvent.click(screen.getByText('改主色'));
  vi.restoreAllMocks();
  fireEvent.click(screen.getByText('确认主色'));
  expect(JSON.parse(localStorage.getItem(themeStorageKey)!)).toMatchObject({ primary: '#722ED1' });
});

it('色卡移除独立输入，取色仅预览；重置与勾选分别恢复和持久化', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => '原文' }));
  await act(async () => { render(<ThemeProvider><App><DesignStandardsPage /></App></ThemeProvider>); });
  expect(screen.queryAllByRole('textbox', { name: /色值$/ })).toHaveLength(0);
  const picker = screen.getByRole('button', { name: '主题色（主色）取色' });
  expect(picker.previousElementSibling?.textContent).toBe(defaultColors.primary);
  expect(screen.queryByRole('button', { name: '保存主题色（主色）' })).toBeNull();
  fireEvent.click(picker);
  await waitFor(() => expect(document.querySelector('.ant-color-picker-hex-input input')).toBeTruthy());
  const input = document.querySelector('.ant-color-picker-hex-input input')!;
  fireEvent.change(input, { target: { value: '234567' } });
  expect(document.documentElement.style.getPropertyValue('--app-primary')).toBe('#234567');
  expect(localStorage.getItem(themeStorageKey)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '重置主题色（主色）' }));
  expect(document.documentElement.style.getPropertyValue('--app-primary')).toBe(defaultColors.primary);
  expect(localStorage.getItem(themeStorageKey)).toBeNull();
  fireEvent.change(input, { target: { value: '345678' } });
  fireEvent.click(screen.getByRole('button', { name: '保存主题色（主色）' }));
  expect(JSON.parse(localStorage.getItem(themeStorageKey)!)).toMatchObject({ primary: '#345678' });
  expect(screen.queryByRole('button', { name: '保存主题色（主色）' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '查看 page-title 代码' }));
  expect(screen.getByRole('button', { name: '收起 page-title 代码' }).getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(screen.getByRole('button', { name: '恢复默认颜色' }));
  expect(document.documentElement.style.getPropertyValue('--app-primary')).toBe(defaultColors.primary);
});
