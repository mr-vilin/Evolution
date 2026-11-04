import { createContext, type ReactNode, useContext, useState } from 'react';
import { Button, Drawer, Form, Radio, Switch } from 'antd';

const defaults = { contentWidth: 'Fluid' as 'Fluid' | 'Fixed', fixedHeader: true, fixSiderbar: true };
const WorkspaceContext = createContext({ settings: defaults, open: () => {} });
export const useWorkspaceSettings = () => useContext(WorkspaceContext);

export function WorkspaceSettings({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(defaults);
  const [open, setOpen] = useState(false);
  return <WorkspaceContext.Provider value={{ settings, open: () => setOpen(true) }}>
    {children}
    <Drawer title="布局设置" open={open} onClose={() => setOpen(false)} size={340}>
      <Form layout="vertical">
        <Form.Item label="内容宽度"><Radio.Group value={settings.contentWidth} onChange={event => setSettings(previous => ({ ...previous, contentWidth: event.target.value }))} options={[{ label: '流式', value: 'Fluid' }, { label: '固定', value: 'Fixed' }]} /></Form.Item>
        <Form.Item label="固定顶栏"><Switch checked={settings.fixedHeader} onChange={fixedHeader => setSettings(previous => ({ ...previous, fixedHeader }))} /></Form.Item>
        <Form.Item label="固定侧栏"><Switch checked={settings.fixSiderbar} onChange={fixSiderbar => setSettings(previous => ({ ...previous, fixSiderbar }))} /></Form.Item>
        <Button onClick={() => setSettings(defaults)}>恢复默认布局</Button>
      </Form>
    </Drawer>
  </WorkspaceContext.Provider>;
}
