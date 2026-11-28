import { Progress, Space, Tag, Tooltip, theme } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined, MinusCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import type { SyncJob } from '../domain';

export const syncTypes = { initialize: '初始化任务', full: '全量同步任务', subtree: '局部同步任务', reconcile: '全量校准任务' };
export const syncPhases = { queued: '等待执行', waiting_initialization: '等待初始化', scopes: '读取权限范围', departments: '采集部门', employees: '采集成员', collected: '采集完成', validating: '校验数据', publishing: '汇总入库', published: '执行完成', collection_failed: '采集失败', interrupted: '执行中断', superseded: '已被替代' };
export const syncStatuses = { queued: '排队中', running: '执行中', succeeded: '完成', completed_with_errors: '完成（有异常）', failed: '失败' };
export const resultLabels: Record<string, string> = { create: '新增', update: '更新', delete: '删除', unchanged: '无变化', failed: '失败', pending: '待处理' };
export function label(values: Record<string, string>, value?: string | null) { return value ? values[value] ?? value : '-'; }
export function SyncStatus({ value, result = false }: { value: string; result?: boolean }) {
  const { token } = theme.useToken();
  const color = ['succeeded', 'create'].includes(value) ? token.colorSuccess : value === 'failed' || value === 'delete' ? token.colorError : ['running', 'update'].includes(value) ? token.colorInfo : value === 'completed_with_errors' ? token.colorWarning : token.colorTextSecondary;
  return <Tag variant="filled" color={color}>{label(result ? resultLabels : syncStatuses, value)}</Tag>;
}
export function formatTableTime(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return '-';
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(date);
  const part = (name: string) => parts.find(value => value.type === name)?.value;
  return part('year') + '-' + part('month') + '-' + part('day') + ' ' + part('hour') + ':' + part('minute') + ':' + part('second');
}

export function EventConnectionStatus({ status }: { status: string }) {
  const states = {
    normal: { color: 'success', label: '正常', icon: <CheckCircleOutlined /> },
    warning: { color: 'warning', label: '告警', icon: <ExclamationCircleOutlined /> },
    disconnected: { color: 'error', label: '断开', icon: <CloseCircleOutlined /> },
    unconfigured: { color: 'default', label: '未配置', icon: <MinusCircleOutlined /> },
  };
  const state = states[status as keyof typeof states] ?? { color: 'default', label: '未知', icon: <QuestionCircleOutlined /> };
  return <Tag color={state.color} variant="filled" icon={state.icon} style={{ marginInlineEnd: 0 }}>{state.label}</Tag>;
}

export function SyncProgress({ job, compact = false }: { job: SyncJob; compact?: boolean }) {
  const { token } = theme.useToken();
  const total = job.progress_total === undefined ? job.total_count : job.progress_total;
  const processed = job.processed_count ?? 0;
  const published = job.status === 'succeeded';
  const known = typeof total === 'number';
  const percent = known ? (total > 0 ? Math.min(100, Math.max(0, Math.floor(processed / total * 100))) : (published ? 100 : 0)) : undefined;
  const complete = percent === 100 && job.status !== 'failed';
  const counts = <Space orientation="vertical" size={0}>
    <span>{published ? '已处理 ' : '已采集 '}{processed}{known ? ' / ' + total : '，总量发现中'}</span>
    <span>{published ? '成功 ' : '已入库 '}{job.success_count ?? 0} · {published ? '失败 ' : '待核验 '}{job.failure_count ?? 0}</span>
  </Space>;
  const completedWithErrors = complete && Boolean(job.failure_count);
  const indicator = percent === undefined ? <span>-</span> :
    <Progress size="small" percent={percent}
      status={complete ? 'success' : job.status === 'failed' ? 'exception' : 'normal'}
      strokeColor={completedWithErrors ? token.colorWarning : undefined}
      styles={completedWithErrors ? { indicator: { color: token.colorWarning } } : undefined}
      format={complete ? undefined : value => value + '%'} />;
  const countSummary = [job.success_count ?? 0, job.failure_count ?? 0, known ? total : '-'].join('/');
  return compact ? <Tooltip title={countSummary} trigger={['hover', 'focus']}><div className="sync-progress-cell" tabIndex={0}>{indicator}</div></Tooltip> :
    <div className="sync-progress-detail">{indicator}<div className="sync-caption">{counts}</div></div>;
}
