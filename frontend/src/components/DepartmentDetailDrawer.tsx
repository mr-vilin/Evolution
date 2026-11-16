import { Alert, Avatar, Button, Descriptions, Divider, Space, Tag, Tooltip, Typography, theme } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import type { DepartmentDetails } from '../domain';
import { useResource } from '../services/useResource';
import { ResourceState } from './ResourceState';
import { DetailDrawer } from './DetailDrawer';
import { EmployeeIdentity } from './EmployeeIdentity';
import { EmployeeValue } from './EmployeeValue';
import { CopyValue } from './CopyValue';

function DepartmentDetailResource({ departmentId }: { departmentId: string }) {
  const { token } = theme.useToken();
  const resource = useResource<DepartmentDetails>(`/admin/api/departments/${encodeURIComponent(departmentId)}/details`);
  const department = resource.data;
  const chatEmpty = department?.chat_status === 'not_set' ? '未设置' : department?.chat_status === 'not_applicable' ? '不适用' : '暂无法读取';
  return <ResourceState {...resource}>{department && <>
    <div className="employee-detail-heading">
      <Typography.Title level={4} style={{ margin: 0 }}>{department.name}</Typography.Title>
      <Tag color={department.status === 'active' ? 'success' : 'default'}>{department.status === 'active' ? '活跃' : '禁用'}</Tag>
    </div>
    <div className="department-leaders-row">
      <Typography.Text type="secondary" style={{ flex: 'none' }}>部门负责人</Typography.Text>
      <div className="department-leaders">{department.leaders.map(leader => <span key={leader.user_id} className="department-person-chip"
        style={{ background: token.colorFillSecondary, borderRadius: 9999 }}>
        <Avatar size={24} src={leader.avatar_url || undefined} icon={<UserOutlined />} alt={`${leader.name}的头像`} />
        <span style={{ overflowWrap: 'anywhere' }}>{leader.name}</span>
        <Tag color={leader.leader_type === 1 ? 'processing' : 'default'}>{leader.leader_type === 1 ? '部门主负责人' : '部门副负责人'}</Tag>
      </span>)}{!department.leaders.length && <EmployeeValue />}</div>
    </div>
    <Divider />
    <Descriptions column={1} colon={false} styles={{ label: { width: 96 }, content: { minWidth: 0, overflowWrap: 'anywhere' } }} items={[
      { key: 'id', label: '部门ID', children: <span className="detail-copy-value"><EmployeeValue value={department.feishu_department_id} /><CopyValue value={department.feishu_department_id} label="部门ID" /></span> },
      { key: 'parent', label: '上级部门', children: <Tooltip title={department.path.slice(0, -1).filter((_, index) => index > 0).join(' / ')}><span><EmployeeValue value={department.parent_name ?? department.parent_id} /></span></Tooltip> },
      { key: 'chat', label: '部门群名称', children: <span className="detail-copy-value">
        {department.chat_name || (department.chat_status === 'available' ? <EmployeeValue /> : chatEmpty)}
        {department.chat_id && <CopyValue value={department.chat_id} label="群id" />}
      </span> },
      { key: 'owner', label: '部门群群主', children: department.chat_owner
        ? <EmployeeIdentity name={department.chat_owner.name} avatar={department.chat_owner.avatar_url} />
        : department.chat_status === 'available' ? <EmployeeValue /> : chatEmpty },
    ]} />
    {!!department.detail_warnings.length && <Space orientation="vertical" style={{ width: '100%', marginTop: 16 }}>
      {department.detail_warnings.map(warning => <Alert key={warning} type="warning" showIcon title={warning} />)}
      <Button onClick={resource.reload}>重新读取</Button>
    </Space>}
  </>}</ResourceState>;
}

export function DepartmentDetailDrawer({ departmentId, onClose }: { departmentId?: string; onClose: () => void }) {
  return <DetailDrawer title="部门详情" open={Boolean(departmentId)} onClose={onClose}>
    {departmentId && <DepartmentDetailResource key={departmentId} departmentId={departmentId} />}
  </DetailDrawer>;
}
