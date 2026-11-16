import { App, Button, Tooltip, theme } from 'antd';
import { CopyOutlined } from '@ant-design/icons';

export function CopyValue({ value, label, ariaLabel = `复制${label}`, missingTip = `${label}未采集`, failureMessage = `复制失败，请手动复制${label}` }: {
  value?: string | null; label: string; ariaLabel?: string; missingTip?: string; failureMessage?: string;
}) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  async function copy() {
    if (!value) return;
    try { await navigator.clipboard.writeText(value); message.success('已复制'); }
    catch { message.error(failureMessage); }
  }
  return <Tooltip title={value ? `复制${label}` : missingTip}><Button type="text" size="small" className="employee-copy"
    style={{ color: token.colorTextTertiary, border: 0 }} icon={<CopyOutlined />}
    aria-label={ariaLabel} disabled={!value} onClick={() => void copy()} /></Tooltip>;
}
