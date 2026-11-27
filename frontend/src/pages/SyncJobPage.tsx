import { Link, useParams } from '@umijs/max';
import { useEffect, useState, type Key } from 'react';
import { Alert, App, Button, Card, Descriptions, Input, Select, Space, Tooltip } from 'antd';
import type { SyncJob, SyncJobDetail } from '../domain';
import { request } from '../services/http';
import { useResource } from '../services/useResource';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { AdaptiveTableCard } from '../components/AdaptiveTableCard';
import { CopyValue } from '../components/CopyValue';
import { EmployeeIdentity } from '../components/EmployeeIdentity';
import { ReloadOutlined } from '@ant-design/icons';
import { SyncChanges } from '../components/SyncChanges';
import { formatTableTime, label, resultLabels, SyncProgress, SyncStatus, syncPhases, syncTypes } from '../components/SyncPresentation';

export function SyncJobPage() {
  const { id } = useParams<{ id: string }>();
  const { message } = App.useApp();
  const detail = useResource<SyncJob>(id ? `/admin/api/sync/jobs/${encodeURIComponent(id)}` : null, true);
  const [objectType, setObjectType] = useState('employee');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string>();
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<readonly Key[]>([]);
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
  const displayed = rows.filter(row => row.object_type === objectType && (!result || row.action === result) && [row.object_name, row.object_id].some(value => value?.toLocaleLowerCase().includes(keyword.trim().toLocaleLowerCase())));
  return <PageHeader className="sync-page" area="组织管理" title="同步任务详情" description="按对象查看处理结果与已提交的字段变更。" extra={<Space><Link to="/sync">返回组织同步</Link>{job?.status === 'failed' && job.type !== 'initialize' && <Button danger loading={busy} onClick={retry}>重试任务</Button>}<Button onClick={detail.reload}>刷新</Button></Space>}>
    <ResourceState {...detail} loading={detail.loading && !job}>{job && <>
      <Card><Descriptions column={{ xs: 1, md: 2, xl: 3 }} items={[
        { key: 'type', label: '类型', children: label(syncTypes, job.type) },
        { key: 'trigger', label: '触发机制', children: job.trigger_label ?? '—' },
        { key: 'executor', label: '执行人', children: job.executor_name ?? '—' },
        { key: 'status', label: '状态', children: <SyncStatus value={job.status === 'succeeded' && job.failure_count ? 'completed_with_errors' : job.status} /> },
        { key: 'phase', label: '阶段', children: label(syncPhases, job.phase) },
        { key: 'scope', label: '范围', children: job.root_department_name ? `${job.root_department_name}及后代` : job.root_department_id ?? '全企业' },
        { key: 'start', label: '开始时间', children: formatTableTime(job.started_at) },
        { key: 'end', label: '结束时间', children: formatTableTime(job.finished_at) },
        { key: 'retry', label: '重试次数', children: job.retry_count ?? 0 },
        { key: 'progress', label: '进度', span: 'filled', children: <SyncProgress job={job} /> },
      ]} /></Card>
      {(job.error_code || (job.failure_count ?? 0) > 0) && <Alert className="block-gap" showIcon type="warning" title={job.status === 'failed' ? '任务未全部完成，已入库的批次保留' : '存在异常对象，请检查处理结果'} description={job.error_detail || job.error_code || `有 ${job.failure_count} 个对象待核验`} />}
      <div className="sync-section">
        <AdaptiveTableCard<SyncJobDetail> title="对象处理结果" rowKey={row => String(row.id ?? row.object_type + ':' + row.object_id)}
          dataSource={displayed} pagination={{ current: Math.min(page, Math.max(1, Math.ceil(displayed.length / 20))), pageSize: 20, onChange: setPage, showSizeChanger: false }}
          scroll={{ x: 850 }} expandable={{
            rowExpandable: row => Boolean(row.changes?.length),
            expandedRowKeys: expanded, onExpandedRowsChange: setExpanded,
            expandedRowRender: row => <SyncChanges changes={row.changes ?? []} />,
            columnTitle: '变更',
          }} columns={[
            { key: 'name', title: objectType === 'employee' ? '成员' : '部门', fixed: 'left', width: 180, render: (_, row) => <Space size={4}>{objectType === 'employee' ? <EmployeeIdentity name={row.object_name ?? row.object_id} /> : row.object_name || row.object_id}<CopyValue label="对象 ID" value={row.object_id} /></Space> },
            { key: 'result', title: '处理结果', render: (_, row) => <SyncStatus result value={row.action ?? (row.status === 'failed' ? 'failed' : 'pending')} /> },
            { key: 'changes', title: '关联记录', render: (_, row) => <span className="sync-caption">{row.changes?.length ? row.changes.length + ' 条（展开查看字段差异）' : row.status === 'succeeded' ? '无内容变更' : '暂无已提交变更'}</span> },
            { key: 'error', title: '错误信息', ellipsis: true, render: (_, row) => <Tooltip title={row.error_message || row.error_code}><span tabIndex={0}>{row.error_message || row.error_code || '-'}</span></Tooltip> },
          ]}>
          <div className="sync-toolbar">
            <Space size={8} wrap><Select aria-label="对象类型" style={{ width: 168 }} value={objectType} onChange={value => { setObjectType(value); setPage(1); setExpanded([]); }} options={[
              { value: 'employee', label: '成员（' + rows.filter(row => row.object_type === 'employee').length + '）' },
              { value: 'department', label: '部门（' + rows.filter(row => row.object_type === 'department').length + '）' },
            ]} />
            <Select aria-label="处理结果" allowClear placeholder="全部结果" value={result} style={{ width: 140 }} onChange={value => { setResult(value); setPage(1); }} options={Object.entries(resultLabels).map(([value, label]) => ({ value, label }))} />
            <Tooltip title="刷新"><Button icon={<ReloadOutlined />} aria-label="刷新处理结果" onClick={detail.reload} /></Tooltip></Space>
            <Input.Search allowClear value={keyword} onChange={event => { setKeyword(event.target.value); setPage(1); }} placeholder="搜索名称或对象 ID" style={{ maxWidth: 260 }} />
          </div>
        </AdaptiveTableCard>
      </div>
    </>}</ResourceState>
  </PageHeader>;
}
export default SyncJobPage;
