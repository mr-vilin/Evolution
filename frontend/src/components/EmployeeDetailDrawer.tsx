import { useState } from 'react';
import { Avatar, Button, Descriptions, Divider, Tag, Tooltip, Typography } from 'antd';
import type { Employee } from '../domain';
import { useResource } from '../services/useResource';
import { ResourceState } from './ResourceState';
import { CopyUserId, EmployeeAccountStatus, EmployeeIdentity } from './EmployeeIdentity';
import { contactLabel, departmentName, departmentPath, personInitial } from './employeePresentation';
import { EmployeeMobile, EmployeeValue } from './EmployeeValue';
import { DetailDrawer } from './DetailDrawer';

function EmployeeDetail({ employee }: { employee: Employee }) {
  const [expanded, setExpanded] = useState(false);
  const departments = [...new Map((employee.departments ?? []).map(row => [row.id, row])).values()];
  const primary = departments.find(row => row.id === employee.primary_department_id);
  return <>
    <div className="employee-detail-heading">
      <Avatar size={56} src={employee.avatar_url || undefined} alt={`${employee.name}的头像`} style={{ fontSize: 14 }}>{personInitial(employee.name)}</Avatar>
      <Typography.Title level={5} style={{ margin: 0 }}>{employee.name}</Typography.Title>
      <EmployeeAccountStatus employee={employee} />
    </div>
    <div className="employee-primary-department"><Typography.Text type="secondary">主部门</Typography.Text>
      <EmployeeValue value={primary ? departmentPath(primary) : employee.primary_department_id === '0' ? '本组织' : undefined} /></div>
    <Divider />
    <Descriptions column={1} colon={false} styles={{ label: { width: 96 }, content: { minWidth: 0, overflowWrap: 'anywhere' } }} items={[
      { key: 'id', label: '用户ID', children: <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><EmployeeValue value={employee.user_id} /><CopyUserId employee={employee} /></span> },
      { key: 'mobile', label: '手机号码', children: <EmployeeMobile value={contactLabel(employee, 'mobile')} /> },
      { key: 'email', label: '邮箱', children: <EmployeeValue value={contactLabel(employee, 'email')} /> },
      { key: 'leader', label: '直属上级', children: <EmployeeIdentity name={employee.leader_name ?? employee.leader_user_id} avatar={employee.leader_avatar_url} /> },
      { key: 'departments', label: '部门', children: <div>
        <div className="employee-detail-departments">{(expanded ? departments : departments.slice(0, 5)).map(row =>
          <Tooltip key={row.id} title={departmentPath(row)}><Tag tabIndex={0}>{departmentName(row)}</Tag></Tooltip>)}{!departments.length && <EmployeeValue />}</div>
        {departments.length > 5 && <Button type="link" className="employee-show-more" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>
          {expanded ? '收起' : `查看更多（共 ${departments.length} 个）`}</Button>}
      </div> },
      { key: 'type', label: '人员类型', children: <EmployeeValue value={employee.employee_type_name || employee.employee_type_id} /> },
      { key: 'joined', label: '入职日期', children: <EmployeeValue value={contactLabel(employee, 'join_time')} /> },
      { key: 'job', label: '职务', children: <EmployeeValue value={employee.job_title} /> },
      { key: 'store', label: '门店属性', children: <EmployeeValue value={employee.store_attribute_name || employee.store_attribute_id} /> },
      { key: 'role', label: '权限角色', children: <EmployeeValue value={employee.permission_role_name || employee.permission_role_id} /> },
    ]} />
  </>;
}

function EmployeeDetailResource({ employeeId }: { employeeId: string }) {
  const resource = useResource<Employee>(`/admin/api/employees/${encodeURIComponent(employeeId)}`);
  return <ResourceState {...resource}>{resource.data && <EmployeeDetail key={resource.data.id} employee={resource.data} />}</ResourceState>;
}

export function EmployeeDetailDrawer({ employeeId, onClose }: { employeeId?: string; onClose: () => void }) {
  return <DetailDrawer title="成员详情" open={Boolean(employeeId)} onClose={onClose}>
    {employeeId && <EmployeeDetailResource key={employeeId} employeeId={employeeId} />}
  </DetailDrawer>;
}
