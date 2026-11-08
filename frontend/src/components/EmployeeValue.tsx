import { Typography } from 'antd';

/** 人员资料的空值统一展示；不改变接口中的缺失和可读性语义。 */
export function EmployeeValue({ value }: { value?: string | number | null }) {
  return value == null || (typeof value === 'string' && !value.trim())
    ? <Typography.Text type="secondary">-</Typography.Text>
    : <>{value}</>;
}
