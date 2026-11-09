import type { ReactNode } from 'react';
import { Button, Drawer, theme } from 'antd';
import { CloseOutlined } from '@ant-design/icons';

export function DetailDrawer({ title, open, onClose, children }: {
  title: string; open: boolean; onClose: () => void; children: ReactNode;
}) {
  const { token } = theme.useToken();
  return <Drawer title={title} closable={false} placement="right" size="min(600px, 100vw)"
    open={open} onClose={onClose} destroyOnHidden
    extra={<div style={{ borderInlineStart: `1px solid ${token.colorBorder}`, paddingInlineStart: 16, marginInlineStart: 16 }}>
      <Button type="text" aria-label={`关闭${title}`} icon={<CloseOutlined />} onClick={onClose}
        style={{ width: 32, height: 32, padding: 0 }} />
    </div>}>
    {children}
  </Drawer>;
}
