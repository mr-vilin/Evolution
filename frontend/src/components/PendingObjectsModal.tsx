import { useState } from 'react';
import { Button, Input, Modal, Select, Space, Tooltip } from 'antd';
import { EyeOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from '@umijs/max';
import { useResource } from '../services/useResource';
import { ResourceState } from './ResourceState';
import { ResourceTable } from './ResourceTable';
import { CopyValue } from './CopyValue';
import { EmployeeIdentity } from './EmployeeIdentity';
import { DepartmentDetailDrawer } from './DepartmentDetailDrawer';
import { formatTableTime } from './SyncPresentation';

interface PendingObject { object_type: string; object_id: string; object_name?: string | null; avatar_url?: string | null; reason_code: string; last_sync_at?: string | null; updated_at?: string | null }
const reasons: Record<string, string> = {
  MOBILE_REQUIRED: '手机号缺失或不可读', PRIMARY_DEPARTMENT_INVALID: '主部门不唯一或无效',
  FEISHU_MEMBERSHIP_UNREADABLE: '所属部门不可读', DEPARTMENT_RELATION_UNREADABLE: '所属部门引用无法确认',
  PARENT_DEPARTMENT_UNREADABLE: '上级部门不可读', FEISHU_NAME_UNREADABLE: '名称缺失或不可读',
  FEISHU_STATUS_UNREADABLE: '人员或部门状态不可读', FEISHU_ID_MISMATCH: '对象标识不一致',
  FEISHU_DETAIL_MISSING: '飞书对象详情无法读取', FEISHU_API_ERROR: '飞书读取接口失败',
  FEISHU_REQUIRED_FIELD_INVALID: '对象必填字段格式错误', FEISHU_UNAVAILABLE: '飞书接口暂不可用',
  PENDING_VERIFICATION: '历史待核实，需重新同步确认原因',
};
export function PendingObjectsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const pending = useResource<PendingObject[]>(open ? '/admin/api/sync/pending-objects' : null, true);
  const [kind, setKind] = useState<string>();
  const [reason, setReason] = useState<string>();
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [departmentId, setDepartmentId] = useState<string>();
  const rows = (pending.data ?? []).filter(row => (!kind || row.object_type === kind) && (!reason || row.reason_code === reason) &&
    [row.object_name, row.object_id].some(text => text?.toLocaleLowerCase().includes(keyword.trim().toLocaleLowerCase())));
  return <Modal centered width={1000} title="待核实对象" open={open} onCancel={onClose} footer={null}>
    <div className="sync-toolbar"><Space wrap size={8}>
      <Select aria-label="对象类型" allowClear placeholder="全部对象" value={kind} style={{ width: 120 }} onChange={value => { setKind(value); setPage(1); }} options={[{ value: 'employee', label: '人员' }, { value: 'department', label: '部门' }]} />
      <Select aria-label="待核实原因" allowClear placeholder="全部原因" value={reason} style={{ width: 180 }} onChange={value => { setReason(value); setPage(1); }} options={[...new Set((pending.data ?? []).map(row => row.reason_code))].map(value => ({ value, label: value.split(',').map(code => reasons[code] ?? code).join('、') }))} />
      <Tooltip title="刷新"><Button icon={<ReloadOutlined />} aria-label="刷新待核实对象" onClick={pending.reload} /></Tooltip>
    </Space><Input.Search allowClear value={keyword} onChange={event => { setKeyword(event.target.value); setPage(1); }} placeholder="搜索名称或对象 ID" style={{ maxWidth: 230 }} /></div>
    <ResourceState {...pending} loading={pending.loading && !pending.data}><ResourceTable<PendingObject> rowKey={row => row.object_type + ':' + row.object_id} dataSource={rows} pagination={{ current: Math.min(page, Math.max(1, Math.ceil(rows.length / 10))), pageSize: 10, onChange: setPage, showSizeChanger: false }} scroll={{ x: 780, y: 360 }} columns={[
      { key: 'name', title: '名称', fixed: 'left', width: 180, render: (_, row) => <Space size={4}>{row.object_type === 'employee' ? <EmployeeIdentity name={row.object_name ?? row.object_id} avatar={row.avatar_url} /> : row.object_name ?? row.object_id}<CopyValue value={row.object_id} label="对象 ID" /></Space> },
      { key: 'type', title: '对象类型', render: (_, row) => row.object_type === 'employee' ? '人员' : '部门' },
      { key: 'reason', title: '待核实原因', render: (_, row) => row.reason_code.split(',').map(code => reasons[code] ?? code).join('、') },
      { key: 'time', title: '最近同步时间', width: 160, render: (_, row) => <span className="sync-caption">{formatTableTime(row.last_sync_at ?? row.updated_at)}</span> },
      { key: 'actions', title: '操作', width: 96, render: (_, row) => row.last_sync_at ? <Tooltip title="查看对象详情"><Button type="text" aria-label="查看对象详情" icon={<EyeOutlined />} onClick={() => row.object_type === 'employee' ? navigate('/employees/' + encodeURIComponent(row.object_id)) : setDepartmentId(row.object_id)} /></Tooltip> : '-' },
    ]} /></ResourceState>
    <DepartmentDetailDrawer departmentId={departmentId} onClose={() => setDepartmentId(undefined)} />
  </Modal>;
}
