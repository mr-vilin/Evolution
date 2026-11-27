import { useNavigate, useSearchParams } from '@umijs/max';
import { useEffect, useState } from 'react';
import { App, Button, Input, Select, Space, Tooltip } from 'antd';
import { ExclamationCircleOutlined, EyeOutlined, InfoCircleOutlined, QuestionCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import type { SyncJob } from '../domain';
import { request, query } from '../services/http';
import { useResource } from '../services/useResource';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { AdaptiveTableCard } from '../components/AdaptiveTableCard';
import { CopyValue } from '../components/CopyValue';
import { EmployeeIdentity } from '../components/EmployeeIdentity';
import { PendingObjectsModal } from '../components/PendingObjectsModal';
import { formatTableTime, label, SyncProgress, SyncStatus, syncPhases, syncStatuses, syncTypes } from '../components/SyncPresentation';

interface Status {
  initialized_at: string | null;
  sync_summary?: { pending_object_count: number };
}
export function SyncPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const status = useResource<Status>('/admin/api/status', true);
  const [filters, setFilters] = useState<{ status?: string; type?: string }>({});
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [sort, setSort] = useState<'asc' | 'desc' | undefined>();
  const [pendingOpen, setPendingOpen] = useState(false);
  const jobs = useResource<SyncJob[]>('/admin/api/sync/jobs' + query({ ...filters, limit: 20, page, keyword: keyword.trim(), sort }), true);
  const total = Number(jobs.meta.total_count ?? jobs.data?.length ?? 0);
  useEffect(() => {
    if (!jobs.loading && jobs.data && page > Math.max(1, Math.ceil(total / 20))) setPage(Math.max(1, Math.ceil(total / 20)));
  }, [jobs.loading, jobs.data, page, total]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { const job = params.get('job'); if (job) navigate(`/sync/jobs/${encodeURIComponent(job)}`, { replace: true }); }, [params, navigate]);
  useEffect(() => { const timer = window.setInterval(() => { jobs.reload(); status.reload(); }, 3000); return () => clearInterval(timer); }, [jobs.reload, status.reload]);
  async function create() {
    setBusy(true);
    try {
      const result = await request<{ job_id: string; reused?: boolean }>('/admin/api/sync/jobs', { method: 'POST', body: { type: 'full' } });
      message.success(result.data.reused ? '已打开相同范围的活动任务' : '全量同步任务已创建');
      navigate(`/sync/jobs/${encodeURIComponent(result.data.job_id)}`);
    } catch (error) { message.error(error instanceof Error ? error.message : '创建失败'); }
    finally { setBusy(false); }
  }
  const current = status.data;
  const options = (values: Record<string, string>) => Object.entries(values).map(([value, text]) => ({ value, label: text }));
  const initialization = current?.initialized_at ? formatTableTime(current.initialized_at) : status.error ? '读取失败' : status.loading ? '读取中' : '暂无历史日期';
  const title = <span className="sync-title">组织同步<Tooltip title={'初始化日期：' + initialization} trigger={['hover', 'focus']}><InfoCircleOutlined className="sync-title-info" tabIndex={0} aria-label="初始化日期" /></Tooltip></span>;
  const pending = <Space size={4} className="sync-pending">待核实对象<Tooltip title="统计当前已发现且待核实的部门和人员" trigger={['hover', 'focus']}><QuestionCircleOutlined tabIndex={0} aria-label="待核实对象说明" /></Tooltip>{current?.sync_summary ? <Button type="link" style={{ padding: 0, height: 'auto' }} onClick={() => setPendingOpen(true)}>{current.sync_summary.pending_object_count}</Button> : '-'}</Space>;
  return <PageHeader className="sync-page sync-list-page" area="组织管理" title={title} description="查看同步进度与结果；同步按批次入库，可在任务完成前查看已更新的数据。">
    <div className="sync-list-section">
      <AdaptiveTableCard<SyncJob> title="同步任务" headerExtra={pending} rowKey={row => row.job_id ?? row.id ?? ''} dataSource={jobs.data ?? []}
        showTable={!jobs.error && Boolean(jobs.data)} pagination={{ current: page, pageSize: 20, total, showSizeChanger: false }}
        scroll={{ x: 1080 }} onChange={(pagination, _, sorter, extra) => {
          if (extra.action === 'sort') {
            const value = Array.isArray(sorter) ? sorter[0] : sorter;
            setSort(value.order === 'ascend' ? 'asc' : value.order === 'descend' ? 'desc' : undefined); setPage(1);
          } else setPage(pagination.current ?? 1);
        }} columns={[
          { key: 'type', title: '类型', dataIndex: 'type', fixed: 'left', width: 180, render: (value, row) => <Space size={4}><span>{label(syncTypes, value)}</span><CopyValue value={row.job_id ?? row.id} label="任务 ID" /></Space> },
          { key: 'trigger', title: '触发机制', dataIndex: 'trigger_label', render: value => value || '其他触发' },
          { key: 'executor', title: '执行人', dataIndex: 'executor_name', render: (value, row) => value === '系统' ? value : value ? <EmployeeIdentity name={value} avatar={row.executor_avatar_url} /> : '-' },
          { key: 'scope', title: '范围', ellipsis: true, render: (_, row) => <Tooltip title={row.root_department_name ?? row.root_department_id}><span tabIndex={0}>{row.root_department_name ? row.root_department_name + '及后代' : row.root_department_id ? row.root_department_id + '及后代' : '全企业'}</span></Tooltip> },
          { key: 'phase', title: '阶段', dataIndex: 'phase', render: value => label(syncPhases, value) },
          { key: 'status', title: '状态', width: 120, dataIndex: 'status', render: (value, row) => <SyncStatus value={(row.display_status as string | undefined) ?? (value === 'succeeded' && row.failure_count ? 'completed_with_errors' : value)} /> },
          { key: 'progress', title: <span className="sync-progress-heading">进度<Tooltip title="成功/失败/总数" trigger={['hover', 'focus']}><ExclamationCircleOutlined className="sync-title-info" tabIndex={0} aria-label="进度说明" /></Tooltip></span>, width: 160, render: (_, row) => <SyncProgress job={row} compact /> },
          { key: 'create_time', title: '创建时间', dataIndex: 'create_time', width: 160, sorter: true, sortOrder: sort === 'asc' ? 'ascend' : sort === 'desc' ? 'descend' : null, render: value => <span className="sync-caption">{formatTableTime(value)}</span> },
          { key: 'actions', title: '操作', fixed: 'right', width: 96, render: (_, row) => <Tooltip title="查看详情"><Button type="text" aria-label="查看详情" icon={<EyeOutlined />} onClick={() => navigate('/sync/jobs/' + encodeURIComponent(row.job_id ?? row.id ?? ''))} /></Tooltip> },
        ]}>
        <div className="sync-toolbar">
          <Space wrap size={8}>
          <Select aria-label="类型" allowClear placeholder="全部类型" style={{ width: 168 }} value={filters.type} onChange={type => { setFilters(value => ({ ...value, type })); setPage(1); }} options={options(syncTypes)} />
          <Select aria-label="状态" allowClear placeholder="全部状态" style={{ width: 144 }} value={filters.status} onChange={state => { setFilters(value => ({ ...value, status: state })); setPage(1); }} options={options(syncStatuses)} />
          <Button type="primary" loading={busy} onClick={create}>全量更新</Button>
          <Tooltip title="刷新"><Button aria-label="刷新" icon={<ReloadOutlined />} onClick={() => { jobs.reload(); status.reload(); }} /></Tooltip>
          </Space>
          <Input.Search allowClear aria-label="搜索任务" placeholder="搜索任务名称或 ID" style={{ maxWidth: 260 }} onSearch={value => { setKeyword(value); setPage(1); }} onChange={event => { if (!event.target.value) { setKeyword(''); setPage(1); } }} />
        </div>
        <ResourceState {...jobs} loading={jobs.loading && !jobs.data}>{null}</ResourceState>
      </AdaptiveTableCard>
    </div>
    <PendingObjectsModal open={pendingOpen} onClose={() => setPendingOpen(false)} />
  </PageHeader>;
}
export default SyncPage;
