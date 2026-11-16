import { Link, useNavigate, useSearchParams } from '@umijs/max';
import { useEffect, useState } from 'react';
import { App, Button, Card, Descriptions, Select, Space, Tooltip } from 'antd';
import { QuestionCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import type { SyncJob } from '../domain';
import { formatTime } from '../domain';
import { request, query } from '../services/http';
import { useResource } from '../services/useResource';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { ResourceTable } from '../components/ResourceTable';
import { label, SyncProgress, SyncStatus, syncPhases, syncStatuses, syncTypes } from '../components/SyncPresentation';

interface Status { initialized_at: string | null; coverage_status: string; connection: { status: string; checked_at: string | null } }
export function SyncPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const status = useResource<Status>('/admin/api/status', true);
  const [filters, setFilters] = useState<{ status?: string; type?: string; phase?: string }>({});
  const jobs = useResource<SyncJob[]>('/admin/api/sync/jobs' + query({ ...filters, limit: 200 }), true);
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
  const help = (text: string) => <Tooltip title={text}><QuestionCircleOutlined tabIndex={0} aria-label={text} /></Tooltip>;
  return <PageHeader area="系统管理" title="同步中心" description="查看同步进度与结果；同步按批次入库，可在任务完成前查看已更新的数据。" extra={<Button type="primary" icon={<ReloadOutlined />} loading={busy} onClick={create}>一键全量更新</Button>}>
    <Card><ResourceState {...status} loading={status.loading && !status.data}>{current && <Descriptions column={{ xs: 1, md: 2, xl: 4 }} items={[
      { key: 'initialized', label: '初始化日期', children: current.initialized_at ? formatTime(current.initialized_at) : '暂无历史日期' },
      { key: 'full', label: '最近全量完成', children: formatTime(status.meta.last_full_sync_at as string | null) },
      { key: 'coverage', label: <Space>通讯录覆盖{help('确认应用能读取全部成员及无部门成员后，才可认定覆盖完整。待核验表示缺少有效覆盖证明或授权范围发生变化，不代表同步失败。')}</Space>, children: label({ complete: '覆盖完整', incomplete: '覆盖不完整', unknown: '待核验' }, current.coverage_status) },
      { key: 'connection', label: <Space>飞书事件连接{help('根据最近重连或收到事件的时间判断。90 秒内有证据显示近期连接正常，超时仅表示暂无近期证据。可检查监听进程和飞书应用事件订阅，并通过一次真实通讯录变更确认事件收到及处理；同步成功只能证明读取接口可用。')}</Space>, children: <Tooltip title={`最近连接证据：${formatTime(current.connection.checked_at)}`}><span>{label({ connected: '近期连接正常', degraded: '暂无近期连接证据', unconfigured: '未配置' }, current.connection.status)}</span></Tooltip> },
    ]} />}</ResourceState></Card>
    <Card className="block-gap" title="同步任务" extra={<Button icon={<ReloadOutlined />} onClick={() => { jobs.reload(); status.reload(); }}>刷新</Button>}>
      <Space wrap size="middle">
        <label>类型 <Select aria-label="类型" allowClear placeholder="全部类型" style={{ width: 168 }} value={filters.type} onChange={type => setFilters(value => ({ ...value, type }))} options={options(syncTypes)} /></label>
        <label>阶段 <Select aria-label="阶段" allowClear placeholder="全部阶段" style={{ width: 168 }} value={filters.phase} onChange={phase => setFilters(value => ({ ...value, phase }))} options={options(syncPhases)} /></label>
        <label>状态 <Select aria-label="状态" allowClear placeholder="全部状态" style={{ width: 144 }} value={filters.status} onChange={state => setFilters(value => ({ ...value, status: state }))} options={options(syncStatuses)} /></label>
        {help('阶段表示当前执行步骤。普通任务按批次入库，采集完成后汇总结果；初始化额外校验数据。失败或中断时保留已提交批次，可重试补齐。')}
      </Space>
      <ResourceState {...jobs} loading={jobs.loading && !jobs.data} empty={!jobs.loading && !jobs.data?.length}>
        <ResourceTable<SyncJob> className="block-gap" rowKey={row => row.job_id ?? row.id ?? ''} dataSource={jobs.data ?? []} pagination={{ pageSize: 20 }} scroll={{ x: 1200 }} columns={[
          { title: '类型', dataIndex: 'type', render: value => label(syncTypes, value) },
          { title: '触发机制', dataIndex: 'trigger_label', render: value => value || '其他触发' },
          { title: '执行人', dataIndex: 'executor_name', render: value => value || '—' },
          { title: '范围', render: (_, row) => row.root_department_name ? `${row.root_department_name}及后代` : row.root_department_id ? `${row.root_department_id}及后代` : '全企业' },
          { title: '阶段', dataIndex: 'phase', render: value => label(syncPhases, value) },
          { title: '状态', dataIndex: 'status', render: value => <SyncStatus value={value} /> },
          { title: '进度', width: 220, render: (_, row) => <SyncProgress job={row} /> },
          { title: '创建时间', dataIndex: 'created_at', render: formatTime },
          { title: '操作', fixed: 'right', width: 96, render: (_, row) => <Link to={`/sync/jobs/${encodeURIComponent(row.job_id ?? row.id ?? '')}`}>查看详情</Link> },
        ]} />
      </ResourceState>
      {jobs.meta.next_cursor && <p>仅展示最近 200 个匹配任务，可使用筛选缩小范围。</p>}
    </Card>
  </PageHeader>;
}
export default SyncPage;
