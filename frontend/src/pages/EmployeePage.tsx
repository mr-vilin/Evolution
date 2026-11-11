import { ProDescriptions } from '@ant-design/pro-components';
import { Alert, Button, Card, Table, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from '@umijs/max';
import type { Employee } from '../domain';
import { primaryStoreLabel, statusLabel } from '../domain';
import { useResource } from '../services/useResource';
import { ResourceState } from '../components/ResourceState';
import { PageHeader } from '../components/PageHeader';

const quality = (value?: string) => ({ complete: '完整', pending_verification: '保留旧资料，待核实', inconsistent: '关系不一致', unknown: '未知' } as Record<string, string>)[value ?? ''] ?? value ?? '—';
export function EmployeePage() {
  const { id } = useParams();
  const nav = useNavigate();
  const resource = useResource<Employee>(id ? `/admin/api/employees/${encodeURIComponent(id)}` : null);
  const employee = resource.data;
  return <PageHeader title="人员详情" description="查看基本资料、解析状态、部门关系与全部门店归属。" extra={<Button icon={<ArrowLeftOutlined />} onClick={() => nav('/organization')}>返回组织</Button>}>
    <ResourceState {...resource}>{employee && <div className="employee-sections">
      <Card title="基本资料"><ProDescriptions title={employee.name} column={{ xs: 1, md: 2, xl: 3 }} dataSource={employee} columns={[
        { title: '员工 ID', render: () => employee.id },
        { title: '工号', render: () => employee.employee_no ?? '—' },
        { title: '状态', render: () => <Tag>{statusLabel(employee.status)}</Tag> },
        { title: '员工类型', render: () => employee.employee_type_name ? `${employee.employee_type_name}（${employee.employee_type_id ?? '无标识'}）` : employee.employee_type_id ?? '—' },
        { title: '职务', render: () => employee.job_title ?? '—' },
        { title: '直属上级', render: () => employee.leader_name ?? employee.leader_user_id ?? '—' },
        { title: '权限角色', render: () => employee.permission_role_name ?? employee.permission_role_id ?? '—' },
        { title: '门店属性', render: () => employee.store_attribute_name ?? employee.store_attribute_id ?? '—' },
      ]} /></Card>
      <Card title="解析状态"><ProDescriptions column={{ xs: 1, md: 3 }} columns={[
        { title: '同步质量', render: () => <Tag color={employee.sync_quality === 'complete' ? 'green' : 'orange'}>{quality(employee.sync_quality)}</Tag> },
        { title: '主门店解析', render: () => primaryStoreLabel(employee.primary_store_status) },
        { title: '主门店 ID', render: () => employee.primary_store_id ?? '—' },
      ]} /><Alert showIcon type={employee.sync_quality === 'complete' && employee.primary_store_status === 'resolved' ? 'success' : 'info'} title={employee.sync_quality === 'complete' ? primaryStoreLabel(employee.primary_store_status) : quality(employee.sync_quality)} description="主门店仅由唯一飞书主部门向上寻找最近门店派生；数组顺序不代表主归属。" /></Card>
      <Card title="部门关系"><Table size="small" pagination={false} rowKey="id" scroll={{ x: 600 }} dataSource={employee.departments} columns={[{ title: '部门', dataIndex: 'name' }, { title: '完整路径', dataIndex: 'path', render: value => value?.join(' / ') || '—' }, { title: '同步质量', dataIndex: 'sync_quality', render: quality }, { title: '关系', render: (_, row) => row.id === employee.primary_department_id ? <Tag color="processing">主部门</Tag> : '兼任部门' }]} /></Card>
      <Card title="全部门店归属"><Table size="small" pagination={false} rowKey="id" scroll={{ x: 500 }} dataSource={employee.stores} columns={[{ title: '门店', dataIndex: 'name' }, { title: '派生路径', dataIndex: 'path_names', render: value => value?.join(' → ') || '—' }, { title: '归属', dataIndex: 'is_primary', render: value => value ? <Tag color="processing">主门店</Tag> : '其他门店' }]} /></Card>
    </div>}</ResourceState>
  </PageHeader>;
}
export default EmployeePage;
