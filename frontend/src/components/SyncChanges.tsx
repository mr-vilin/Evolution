import { Table } from 'antd';
import type { ChangeLog } from '../domain';
import { formatTableTime } from './SyncPresentation';

const fields: Record<string, string> = {
  id: '对象 ID', feishu_user_id: '飞书用户 ID', open_id: '飞书开放 ID', feishu_department_id: '飞书部门 ID',
  name: '名称', employee_no: '工号', mobile: '手机号', email: '邮箱', avatar_url: '头像', join_time: '入职时间',
  status: '状态', sync_quality: '同步质量', parent_id: '上级部门', primary_department_id: '主部门', department_ids: '所属部门',
  leader_user_id: '直属上级', job_title: '职务', employee_type_id: '人员类型 ID', employee_type_name: '人员类型',
  permission_role_id: '权限角色 ID', permission_role_name: '权限角色', store_attribute_id: '门店属性 ID', store_attribute_name: '门店属性',
  is_root: '组织根节点', is_virtual_root: '组织根节点', sort_order: '排序', relations: '部门关系（部门、是否主部门、是否有效）',
  department_id: '部门', active: '是否有效', is_primary: '是否主部门', primary_store_status: '主门店状态',
  field_readability: '字段可读性', is_frozen: '是否暂停', is_resigned: '是否离职', is_activated: '是否激活', is_exited: '是否退出', is_unjoin: '是否未加入',
};
const values: Record<string, string> = { active: '有效', inactive: '失效', complete: '完整', pending_verification: '待核验', unknown: '未知', readable: '可读', not_collected: '未采集', unreadable: '不可读', resolved: '已解析', not_in_store: '不在门店', inconsistent: '不一致' };
function show(value: unknown, field?: string): string {
  if (value === undefined) return '未记录';
  if (value === null || value === '') return '空';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (field === 'join_time' && typeof value === 'number') return formatTableTime(new Date(value * 1000).toISOString());
  if (Array.isArray(value)) return value.length ? value.map(item => show(item)).join('；') : '无';
  if (typeof value === 'object') return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${fields[key] ?? key}：${show(item, key)}`).join('；');
  return values[String(value)] ?? String(value);
}
export function SyncChanges({ changes }: { changes: ChangeLog[] }) {
  const rows = changes.flatMap(log => {
    const before = (log.before ?? {}) as Record<string, unknown>;
    const after = (log.after ?? {}) as Record<string, unknown>;
    return [...new Set([...Object.keys(before), ...Object.keys(after)])]
      .filter(key => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
      .map(key => ({ key: `${log.id}:${key}`, field: `${log.object_type === 'membership' ? '部门关系 · ' : ''}${fields[key] ?? key}`, before: show(before[key], key), after: show(after[key], key), log: log.id, time: log.committed_at }));
  });
  return <Table size="small" rowKey="key" dataSource={rows} pagination={false} scroll={{ x: 640 }} columns={[
    { key: 'field', title: '变更字段', dataIndex: 'field', fixed: 'left', width: 140 }, { key: 'before', title: '变更前', dataIndex: 'before' }, { key: 'after', title: '变更后', dataIndex: 'after' },
    { key: 'log', title: '关联记录', dataIndex: 'log', render: value => `#${value}` }, { key: 'time', title: '提交时间', dataIndex: 'time', width: 160, sorter: (a, b) => new Date(a.time ?? 0).valueOf() - new Date(b.time ?? 0).valueOf(), render: value => <span className="sync-caption">{formatTableTime(value)}</span> },
  ]} />;
}
