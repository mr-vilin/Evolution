import { Link, useParams } from '@umijs/max';
import { useEffect, useState } from 'react';
import { Alert, App, Button, Card, Descriptions, Select, Space } from 'antd';
import type { SyncJob, SyncJobDetail } from '../domain';
import { formatTime } from '../domain';
import { request } from '../services/http';
import { useResource } from '../services/useResource';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { ResourceTable } from '../components/ResourceTable';
import { SyncChanges } from '../components/SyncChanges';
import { label, SyncProgress, SyncStatus, syncPhases, syncTypes } from '../components/SyncPresentation';

export function SyncJobPage() {
  const { id } = useParams<{ id: string }>();
  const { message } = App.useApp();
  const detail = useResource<SyncJob>(id ? `/admin/api/sync/jobs/${encodeURIComponent(id)}` : null, true);
  const [objectType, setObjectType] = useState('employee');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!detail.data || !['queued', 'running'].includes(detail.data.status)) return;
    const timer = window.setInterval(detail.reload, 3000);
    return () => clearInterval(timer);
  }, [detail.data?.status, detail.reload]);
  async function retry() {
    setBusy(true);
    try { await request(`/admin/api/sync/jobs/${encodeURIComponent(id ?? '')}/retry`, { method: 'POST' }); message.success('重试任务已提交'); detail.reload(); }
    catch (error) { message.error(error instanceof Error ? error.message : '重试失败'); }
    finally { setBusy(false); }
  }
  const job = detail.data;
  const rows = job?.details ?? [];
  return <PageHeader area="组织管理" title="同步任务详情" description="按对象查看处理结果与已提交的字段变更。" extra={<Space><Link to="/sync">返回组织同步</Link>{job?.status === 'failed' && job.type !== 'initialize' && <Button danger loading={busy} onClick={retry}>重试任务</Button>}<Button onClick={detail.reload}>刷新</Button></Space>}>
    <ResourceState {...detail} loading={detail.loading && !job}>{job && <>
      <Card><Descriptions column={{ xs: 1, md: 2, xl: 3 }} items={[
        { key: 'type', label: '类型', children: label(syncTypes, job.type) },
        { key: 'trigger', label: '触发机制', children: job.trigger_label ?? '—' },
        { key: 'executor', label: '执行人', children: job.executor_name ?? '—' },
        { key: 'status', label: '状态', children: <SyncStatus value={job.status} /> },
        { key: 'phase', label: '阶段', children: label(syncPhases, job.phase) },
        { key: 'scope', label: '范围', children: job.root_department_name ? `${job.root_department_name}及后代` : job.root_department_id ?? '全企业' },
        { key: 'start', label: '开始时间', children: formatTime(job.started_at) },
        { key: 'end', label: '结束时间', children: formatTime(job.finished_at) },
        { key: 'retry', label: '重试次数', children: job.retry_count ?? 0 },
        { key: 'progress', label: '进度', span: 'filled', children: <SyncProgress job={job} /> },
      ]} /></Card>
      {(job.error_code || (job.failure_count ?? 0) > 0) && <Alert className="block-gap" showIcon type="warning" title={job.status === 'failed' ? '任务未全部完成，已入库的批次保留' : '存在异常对象，请检查处理结果'} description={job.error_detail || job.error_code || `有 ${job.failure_count} 个对象待核验`} />}
      <Card className="block-gap" title="对象处理结果">
        <div style={{ marginBottom: 16 }}><label>对象类型 <Select aria-label="对象类型" style={{ width: 168 }} value={objectType} onChange={setObjectType} options={[
        { value: 'employee', label: `成员（${rows.filter(row => row.object_type === 'employee').length}）` },
        { value: 'department', label: `部门（${rows.filter(row => row.object_type === 'department').length}）` },
        ]} /></label></div>
        <ResourceTable<SyncJobDetail> key={objectType} rowKey={row => String(row.id ?? `${row.object_type}:${row.object_id}`)} dataSource={rows.filter(row => row.object_type === objectType)} pagination={{ pageSize: 20 }} scroll={{ x: 720 }} expandable={{
          rowExpandable: row => Boolean(row.changes?.length),
          expandedRowRender: row => <SyncChanges changes={row.changes ?? []} />,
          columnTitle: '变更',
        }} columns={[
          { title: objectType === 'employee' ? '成员' : '部门', render: (_, row) => row.object_name || row.object_id },
          { title: '对象 ID', dataIndex: 'object_id' },
          { title: '处理结果', render: (_, row) => <SyncStatus result value={row.action ?? (row.status === 'failed' ? 'failed' : 'pending')} /> },
          { title: '关联记录', render: (_, row) => row.changes?.length ? `${row.changes.length} 条（展开查看字段差异）` : row.status === 'succeeded' ? '无内容变更' : '暂无已提交变更' },
          { title: '错误信息', render: (_, row) => row.error_message || row.error_code || '—' },
        ]} />
      </Card>
    </>}</ResourceState>
  </PageHeader>;
}
export default SyncJobPage;
