import { Typography } from 'antd';
import { internationalMobileParts } from './employeePresentation';

/** 人员资料的空值统一展示；不改变接口中的缺失和可读性语义。 */
export function EmployeeValue({ value }: { value?: string | number | null }) {
  return value == null || (typeof value === 'string' && !value.trim())
    ? <Typography.Text type="secondary">-</Typography.Text>
    : <>{value}</>;
}

export function EmployeeMobile({ value }: { value?: string | null }) {
  const parts = internationalMobileParts(value);
  if (!parts) return <EmployeeValue value={value} />;
  return <span className="employee-mobile">
    <span className="employee-mobile-prefix">{parts.callingCode}</span><span>{parts.number}</span>
  </span>;
}
