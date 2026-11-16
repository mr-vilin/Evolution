import { Progress, Space, Tag, theme } from 'antd';
import type { SyncJob } from '../domain';

export const syncTypes = { initialize: '初始化任务', full: '全量同步任务', subtree: '局部同步任务', reconcile: '全量校准任务' };
export const syncPhases = { queued: '等待执行', waiting_initialization: '等待初始化', scopes: '读取权限范围', departments: '采集部门', employees: '采集成员', collected: '采集完成', validating: '校验数据', publishing: '汇总入库', published: '执行完成', collection_failed: '采集失败', interrupted: '执行中断', superseded: '已被替代' };
export const syncStatuses = { queued: '排队中', running: '执行中', succeeded: '成功', failed: '失败' };
export const resultLabels: Record<string, string> = { create: '新增', update: '更新', delete: '删除', unchanged: '无变化', failed: '失败', pending: '待处理' };
export function label(values: Record<string, string>, value?: string | null) { return value ? values[value] ?? value : '—'; }
export function SyncStatus({ value, result = false }: { value: string; result?: boolean }) {
  const { token } = theme.useToken();
  const color = ['succeeded', 'create'].includes(value) ? token.colorSuccess : value === 'failed' || value === 'delete' ? token.colorError : ['running', 'update'].includes(value) ? token.colorInfo : value === 'queued' || value === 'pending' ? token.colorWarning : token.colorTextSecondary;
  return <Tag variant="outlined" color={color}>{label(result ? resultLabels : syncStatuses, value)}</Tag>;
}
export function SyncProgress({ job }: { job: SyncJob }) {
  const total = job.progress_total;
  const processed = job.processed_count ?? 0;
  const complete = job.status === 'succeeded';
  const known = typeof total === 'number';
  const percent = complete ? 100 : known && total > 0 ? Math.min(99, Math.floor(processed / total * 100)) : 0;
  return <div style={{ minWidth: 176 }}>
    <Progress size="small" percent={percent} status={job.status === 'failed' ? 'exception' : complete ? 'success' : 'active'} showInfo={known || complete} />
    <Space orientation="vertical" size={0}>
      <span>{complete ? `已处理 ${processed} / ${total ?? job.total_count ?? processed}` : `已采集 ${processed}${known ? ` / ${total}` : '，总量发现中'}`}</span>
      <span>{complete ? `成功 ${job.success_count ?? 0} · 失败 ${job.failure_count ?? 0}` : `已入库 ${job.success_count ?? 0} · 待核验 ${job.failure_count ?? 0}`}</span>
    </Space>
  </div>;
}
