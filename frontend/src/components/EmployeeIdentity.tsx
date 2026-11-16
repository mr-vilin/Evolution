import { Avatar, Button, Tag, theme } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import type { Employee } from '../domain';
import { EmployeeValue } from './EmployeeValue';
import { CopyValue } from './CopyValue';

export function EmployeeIdentity({ name, avatar, onClick }: { name?: string | null; avatar?: string | null; onClick?: () => void }) {
  if (!name?.trim()) return <EmployeeValue />;
  const content = <><Avatar size={28} src={avatar || undefined} icon={<UserOutlined />} alt={`${name}的头像`} /><span className="employee-name" title={name}>{name}</span></>;
  return onClick ? <Button type="link" className="employee-identity-button" style={{ border: 0 }} onClick={onClick}><span className="employee-identity">{content}</span></Button>
    : <span className="employee-identity">{content}</span>;
}

export function CopyUserId({ employee }: { employee: Employee }) {
  return <CopyValue value={employee.user_id} label="用户ID" ariaLabel={`复制${employee.name}的用户ID`}
    failureMessage="复制失败，请在详情中手动复制用户ID" />;
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
  const hasUnknown = ['is_activated', 'is_frozen', 'is_unjoin', 'is_resigned', 'is_exited'].some(key => flags[key as keyof typeof flags] == null);
  return <span className="employee-status-tags">{items.map(([label, color]) => <Tag key={label} variant="filled" color={color}>{label}</Tag>)}
    {(hasUnknown || !items.length) && <EmployeeValue />}</span>;
}
