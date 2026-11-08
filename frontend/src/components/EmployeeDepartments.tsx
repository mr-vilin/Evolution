import { Popover, Tag } from 'antd';
import type { Employee } from '../domain';
import { departmentName, departmentPath } from './employeePresentation';

export function EmployeeDepartments({ employee }: { employee: Employee }) {
  const departments = [...new Map((employee.departments ?? []).map(row => [row.id, row])).values()];
  if (!departments.length) return <>—</>;
  const remaining = departments.length - 3;
  return <Popover title="全部所属部门" placement="topLeft" trigger={['hover', 'focus', 'click']}
    content={<ul className="org-memberships-popover">{departments.map(row => <li key={row.id}>
      {departmentPath(row)}
    </li>)}</ul>}>
    <button type="button" className="org-memberships" aria-label={`查看${employee.name}的全部部门，共 ${departments.length} 个`}>
      {departments.slice(0, 3).map(row => <Tag className="org-membership-tag" key={row.id}>{departmentName(row)}</Tag>)}
      {remaining > 0 && <Tag className="org-membership-more">+{remaining}</Tag>}
    </button>
  </Popover>;
}
