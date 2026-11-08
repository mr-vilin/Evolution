import { App, Avatar, Button, Tag, Tooltip, theme } from 'antd';
import { CopyOutlined, UserOutlined } from '@ant-design/icons';
import type { Employee } from '../domain';

export function EmployeeIdentity({ name, avatar, onClick }: { name?: string | null; avatar?: string | null; onClick?: () => void }) {
  if (!name) return <>—</>;
  const content = <><Avatar size={28} src={avatar || undefined} icon={<UserOutlined />} alt={`${name}的头像`} /><span className="employee-name" title={name}>{name}</span></>;
  return onClick ? <Button type="link" className="employee-identity employee-identity-button" onClick={onClick}>{content}</Button>
    : <span className="employee-identity">{content}</span>;
}

export function CopyUserId({ employee }: { employee: Employee }) {
  const { message } = App.useApp();
  const userId = employee.user_id;
  async function copy() {
    if (!userId) return;
    try { await navigator.clipboard.writeText(userId); message.success('已复制'); }
    catch { message.error('复制失败，请在详情中手动复制用户ID'); }
  }
  return <Tooltip title={userId ? '复制用户ID' : '用户ID未采集'}><Button type="text" size="small" icon={<CopyOutlined />}
    aria-label={`复制${employee.name}的用户ID`} disabled={!userId} onClick={() => void copy()} /></Tooltip>;
}

export function EmployeeAccountStatus({ employee }: { employee: Employee }) {
  const { token } = theme.useToken();
  const flags = employee.account_status ?? {};
  const items: Array<[string, string]> = [];
  if (flags.is_activated === true) items.push(['已激活', token.colorSuccess]);
  if (flags.is_activated === false) items.push(['未激活', token.colorWarning]);
  if (flags.is_frozen === true) items.push(['已暂停', token.colorError]);
  if (flags.is_unjoin === true) items.push(['未加入', token.colorWarning]);
  if (flags.is_resigned === true) items.push(['已离职', token.colorTextSecondary]);
  if (flags.is_exited === true) items.push(['已退出', token.colorTextSecondary]);
  if (['is_activated', 'is_frozen', 'is_unjoin', 'is_resigned', 'is_exited'].some(key => flags[key as keyof typeof flags] == null)) items.push(['状态未知', token.colorTextSecondary]);
  return <span className="employee-status-tags">{items.map(([label, color]) => <Tag key={label} variant="solid" color={color}>{label}</Tag>)}</span>;
}
