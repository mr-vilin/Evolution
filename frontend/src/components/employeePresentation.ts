import type { Department, Employee } from '../domain';

export function departmentName(department: Department) {
  return department.id === '0' || department.is_virtual_root ? '本组织' : department.name;
}

export function departmentPath(department: Department) {
  if (department.id === '0' || department.is_virtual_root) return '本组织';
  const path = department.path ?? [];
  // 仅省略路径开头的虚拟组织节点，不替换中间同名的真实部门。
  const visible = path.length > 1 && ['组织', '全公司', '本组织'].includes(path[0]) ? path.slice(1) : path;
  return visible.join(' / ') || department.name;
}

export function contactLabel(employee: Employee, field: 'mobile' | 'email' | 'join_time') {
  const readability = employee.field_readability?.[field];
  const value = field === 'join_time' ? employee.join_date : employee[field];
  return readability === 'readable' ? value || '未填写' : readability === 'unreadable' ? '未知（不可读）' : '未知（未采集）';
}
