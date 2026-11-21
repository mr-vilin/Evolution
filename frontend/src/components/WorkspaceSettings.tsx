import { createContext, type ReactNode, useContext, useState } from 'react';
import { Alert, Button, Drawer, Form, Radio, Space, Switch } from 'antd';
import { readRenamedPreference } from '../services/browserPreferences';

const defaults = { contentWidth: 'Fluid' as 'Fluid' | 'Fixed', fixedHeader: true, fixSiderbar: true };
const storageKey = 'evolution.workspace-layout.v1';
function loadSettings() {
  try {
    const saved = JSON.parse(readRenamedPreference(storageKey, 'organization.workspace-layout.v1') ?? 'null');
    if (saved && ['Fluid', 'Fixed'].includes(saved.contentWidth) && typeof saved.fixedHeader === 'boolean' && typeof saved.fixSiderbar === 'boolean') return { contentWidth: saved.contentWidth as 'Fluid' | 'Fixed', fixedHeader: saved.fixedHeader, fixSiderbar: saved.fixSiderbar };
  } catch { /* 浏览器拒绝存储或旧设置损坏时使用默认布局。 */ }
  return defaults;
}
const WorkspaceContext = createContext({ settings: defaults, open: () => {} });
export const useWorkspaceSettings = () => useContext(WorkspaceContext);

export function WorkspaceSettings({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(loadSettings);
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState('');
  function persist(value: typeof defaults) {
    try { localStorage.setItem(storageKey, JSON.stringify(value)); setFeedback('布局已保存到当前浏览器'); }
    catch { setFeedback('浏览器无法保存布局，本次调整仍然有效'); }
  }
  return <WorkspaceContext.Provider value={{ settings, open: () => setOpen(true) }}>
    {children}
    <Drawer title="布局设置" open={open} onClose={() => setOpen(false)} size={340}>
      <p>仅影响当前浏览器的显示，不修改业务配置和权限。</p>
      <Form layout="vertical">
        <Form.Item label="内容宽度"><Radio.Group value={settings.contentWidth} onChange={event => setSettings(previous => ({ ...previous, contentWidth: event.target.value }))} options={[{ label: '流式', value: 'Fluid' }, { label: '固定', value: 'Fixed' }]} /></Form.Item>
        <Form.Item label="固定顶栏"><Switch checked={settings.fixedHeader} onChange={fixedHeader => setSettings(previous => ({ ...previous, fixedHeader }))} /></Form.Item>
        <Form.Item label="固定侧栏"><Switch checked={settings.fixSiderbar} onChange={fixSiderbar => setSettings(previous => ({ ...previous, fixSiderbar }))} /></Form.Item>
        <Space wrap><Button type="primary" onClick={() => persist(settings)}>保存布局</Button><Button onClick={() => { setSettings(defaults); persist(defaults); }}>恢复默认布局</Button></Space>
        {feedback && <Alert className="block-gap" type="info" title={feedback} />}
      </Form>
    </Drawer>
  </WorkspaceContext.Provider>;
}
