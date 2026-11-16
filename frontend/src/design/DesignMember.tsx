import { Avatar } from 'antd';
import { personInitial } from './tableStandardsModel';

/** 规范页人员列：圆形头像与姓名共享 4px 间距。 */
export default function DesignMember({ name }: { name: string }) {
  return <span className="design-member"><Avatar size={24} shape="circle" aria-hidden>{personInitial(name)}</Avatar><span>{name}</span></span>;
}
