import { useState } from 'react';
import { App, Button, Modal, Tooltip } from 'antd';
import { CopyOutlined } from '@ant-design/icons';

export function CopyValue({ value, label, ariaLabel = `复制${label}`, missingTip = `${label}未采集` }: {
  value?: string | null; label: string; ariaLabel?: string; missingTip?: string;
}) {
  const { message } = App.useApp();
  const [manualCopy, setManualCopy] = useState(false);
  async function copy() {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      message.success('已复制');
    } catch {
      setManualCopy(true);
    }
  }
  return <><Tooltip title={value ? `复制${label}` : missingTip} trigger={['hover', 'focus']}>
    <Button type="text" size="small" className="employee-copy" style={{ border: 0 }} icon={<CopyOutlined />}
      aria-label={ariaLabel} disabled={!value} onClick={() => void copy()} />
  </Tooltip>
    <Modal centered title={'复制失败，请手动复制' + label} open={manualCopy}
      onCancel={() => setManualCopy(false)} onOk={() => setManualCopy(false)}
      cancelButtonProps={{ hidden: true }} okText="关闭">
      <p className="copy-value-manual">{value}</p>
    </Modal>
  </>;
}
