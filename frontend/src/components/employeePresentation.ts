import { parsePhoneNumberFromString } from 'libphonenumber-js/min';
import type { Department, Employee } from '../domain';

export function departmentName(department: Department) {
  return department.id === '0' || department.is_root ? '本组织' : department.name;
}

export function departmentPath(department: Department) {
  if (department.id === '0' || department.is_root) return '本组织';
  const path = department.path ?? [];
  // 仅省略路径开头的虚拟组织节点，不替换中间同名的真实部门。
  const visible = path.length > 1 && ['组织', '全公司', '本组织'].includes(path[0]) ? path.slice(1) : path;
  return visible.join(' / ') || department.name;
}

export function contactLabel(employee: Employee, field: 'mobile' | 'email' | 'join_time') {
  const readability = employee.field_readability?.[field];
  const value = field === 'join_time' ? employee.join_date : employee[field];
  return readability === 'readable' ? value : undefined;
}

export function internationalMobileParts(value: string | null | undefined) {
  if (!value || !/^\+[1-9]\d+$/.test(value)) return undefined;
  const phone = parsePhoneNumberFromString(value);
  if (!phone || phone.number !== value) return undefined;
  const prefixEnd = 1 + phone.countryCallingCode.length;
  return { callingCode: value.slice(0, prefixEnd), number: value.slice(prefixEnd) };
}

export function personInitial(name: string): string {
  const firstWord = name.trim().split(/\s+/)[0] ?? '';
  if (!firstWord) return '?';
  return /^[A-Za-z]+$/.test(firstWord)
    ? firstWord.length > 5 ? firstWord.slice(0, 3) : firstWord
    : Array.from(firstWord)[0];
}
