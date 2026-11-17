import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, DatePicker, Descriptions, Form, Input, Select, Space, Switch, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import { ReloadOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { ResourceTable } from '../components/ResourceTable';
import { request } from '../services/http';
import { useResource } from '../services/useResource';
import type { TencentAccount } from './TencentAccountsPage';
import { TencentCostJobDetail, costStatusTag as statusTag, costStatuses as statuses, type CostJob } from '../components/TencentCostJobDetail';

import { TencentCostPolicyFields, defaultCostPolicy, costPolicyErrors, type CostPolicy } from '../components/TencentCostPolicyFields';

interface CostConfig { run_policy?: CostPolicy; revision: number; is_enabled: boolean; frequency: 'manual'; currency: 'CNY'; latest_eligible_month: string }
interface CostItem { id: string; source_name: string; business_code: string | null; mapping_status: string; amount: string }
interface Period { id: string; month: string; currency: string; total: string; coverage: { status: string; zero_evidence?: string | null }; latest_job_id: string; items: CostItem[] }
function CostAccountPanel({ account }: { account: TencentAccount }) {
  const base = `/admin/api/tencent/accounts/${account.id}`;
  const config = useResource<CostConfig>(`${base}/cost-config`);
  const jobs = useResource<CostJob[]>(`${base}/cost-jobs`, true);
  const [enabled, setEnabled] = useState(false);
  const [policy,setPolicy] = useState<CostPolicy>(defaultCostPolicy);
  const [month, setMonth] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'info' | 'error'; text: string } | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const keys = useRef(new Map<string,string>());
  const detail = useResource<CostJob>(jobId ? `/admin/api/tencent/cost-jobs/${jobId}` : null, true);
  const period = useResource<Period>(month ? `${base}/cost-periods/${month}` : null, true);
  const { message } = App.useApp();
  useEffect(() => {
    if (config.data) { setEnabled(config.data.is_enabled); setPolicy({...defaultCostPolicy,...config.data.run_policy}); setMonth(value => value ?? config.data!.latest_eligible_month); }
  }, [config.data]);
  useEffect(() => { if (!jobId && jobs.data?.length) setJobId(jobs.data[0].id); }, [jobs.data,jobId]);
  useEffect(() => {
    if (detail.data && ['succeeded','failed'].includes(detail.data.status)) keys.current.delete(detail.data.month);
  }, [detail.data]);
  async function save() {
    if (!config.data) return;
    if (Object.keys(costPolicyErrors(policy)).length) { setFeedback({type:'error',text:'请修正执行策略中的字段错误'}); return; }
    setBusy(true); setFeedback(null);
    try {
      await request(`${base}/cost-config`, { method:'PUT', body:{ revision:config.data.revision,is_enabled:enabled,frequency:'manual',currency:'CNY',run_policy:policy } });
      message.success('成本配置已保存'); config.reload();
    } catch (error) { setFeedback({type:'error',text:error instanceof Error ? error.message : '保存失败，请重试'}); }
    finally { setBusy(false); }
  }
  async function submit() {
    if (!month || !config.data?.is_enabled) return;
    setBusy(true); setFeedback(null);
    const key = keys.current.get(month) ?? crypto.randomUUID(); keys.current.set(month,key);
    try {
      const accepted = await request<CostJob>(`${base}/cost-jobs`, {method:'POST',body:{month,idempotency_key:key}});
      setJobId(accepted.data.id); jobs.reload(); detail.reload();
      setFeedback({type:'info',text:`任务 #${accepted.data.id} 已受理，请刷新查看执行结果。`});
    } catch (error) { setFeedback({type:'error',text:error instanceof Error ? error.message : '受理结果未确认，请重试同一账月核实'}); }
    finally { setBusy(false); }
  }
  const active = detail.data?.month === month && ['pending','running','retry_wait'].includes(detail.data.status);
  const rows = (period.data?.items ?? []).filter(row => !search || `${row.source_name} ${row.business_code ?? ''}`.includes(search));
  const columns: TableColumnsType<CostItem> = [
    {key:'name',title:'产品名称',dataIndex:'source_name',fixed:'left',width:220,ellipsis:true},
    {key:'code',title:'产品编码（BusinessCode）',dataIndex:'business_code',width:220,render:value => value || '-'},
    {key:'mapping',title:'产品映射',dataIndex:'mapping_status',width:140,render:value => <Tag color={value==='mapped' ? 'success' : 'warning'}>{value==='mapped' ? '已映射' : value==='ambiguous' ? '同名歧义' : '未映射'}</Tag>},
    {key:'amount',title:'总费用（元）',dataIndex:'amount',align:'right',width:180},
  ];
  return <Space orientation="vertical" size={24} style={{width:'100%'}}>
    <Card title="成本配置">
      <ResourceState {...config}>
        <Form layout="vertical">
          <Form.Item label="成本能力"><Switch aria-label="成本能力" checked={enabled} onChange={setEnabled} disabled={busy || !config.data} checkedChildren="开启" unCheckedChildren="关闭" /></Form.Item>
          <Form.Item label="采集方式"><Select aria-label="采集方式" value="manual" options={[{value:'manual',label:'手动采集完整月'}]} disabled style={{maxWidth:320}} /></Form.Item>
          <p style={{color:'var(--app-muted)'}}>费用账单 · 总费用 · 产品维度 · 人民币（CNY）</p>
          <TencentCostPolicyFields policy={policy} onChange={setPolicy} disabled={busy || !config.data} />
          <Button onClick={() => void save()} disabled={busy || !config.data} loading={busy}>保存配置</Button>
        </Form>
      </ResourceState>
    </Card>
    <Card title="完整账月采集">
      <Space wrap>
        <DatePicker aria-label="完整账月" picker="month" format="YYYY-MM" value={month ? dayjs(`${month}-01`) : null} maxDate={config.data ? dayjs(`${config.data.latest_eligible_month}-01`).endOf('month') : undefined} minDate={dayjs('1970-01-01')} allowClear={false} onChange={value => {setMonth(value?.format('YYYY-MM') ?? null);setSearch('');setPage(1);setFeedback(null);}} />
        <Button aria-label="采集所选账月" type="primary" loading={busy} disabled={busy || !config.data?.is_enabled || !month || Boolean(active) || enabled !== config.data.is_enabled} onClick={() => void submit()}>采集所选账月</Button>
        <Button aria-label="刷新结果" icon={<ReloadOutlined />} onClick={() => {config.reload();jobs.reload();detail.reload();period.reload();}}>刷新结果</Button>
      </Space>
      <p style={{color:'var(--app-muted)'}}>按北京时间每月 3 日开放上月。每月 1–2 日最多选择上上月；受理后由后台执行。</p>
      {feedback && <Alert type={feedback.type} showIcon title={feedback.text} style={{marginBottom:16}} />}
      <ResourceState {...jobs}>
        <Form layout="vertical"><Form.Item label="查看任务"><Select aria-label="查看任务" placeholder="暂无采集任务" value={jobId} options={(jobs.data ?? []).map(job => ({value:job.id,label:`${job.month} · #${job.id} · ${statuses[job.status] ?? '未知状态'}`}))} onChange={setJobId} style={{width:'100%',maxWidth:480}} /></Form.Item></Form>
      </ResourceState>
      {jobId && <ResourceState {...detail}>{detail.data && <TencentCostJobDetail job={detail.data}
        canRerun={!!config.data?.is_enabled && account.is_enabled && !busy}
        onRerun={id => { setJobId(id); jobs.reload(); }} />}</ResourceState>}
    </Card>
    <Card title="所选账月费用">
      {period.error?.code === 'TENCENT_PERIOD_NOT_FOUND' ? <Alert type="info" showIcon title="该账月尚无完整费用结果" /> : <ResourceState {...period}>
        {period.data && <>
          <Descriptions column={{xs:1,md:2}} items={[
            {key:'month',label:'账月',children:period.data.month}, {key:'total',label:'总费用',children:`${period.data.total} ${period.data.currency}`},
            {key:'coverage',label:'覆盖',children:<Tag color="success">完整月已覆盖</Tag>}, {key:'latest',label:'最近成功任务',children:`#${period.data.latest_job_id}`},
            {key:'basis',label:'费用口径',children:'费用账单 / 总费用 / 产品'},
          ]} />
          <Space style={{display:'flex',justifyContent:'flex-end',marginBottom:16}}><Input.Search aria-label="搜索费用产品" placeholder="搜索产品名称或编码" value={search} allowClear onChange={event => {setSearch(event.target.value);setPage(1);}} style={{width:260}} /></Space>
          <ResourceTable<CostItem> rowKey="id" columns={columns} dataSource={rows} scroll={{x:760}} pagination={{current:Math.min(page,Math.max(1,Math.ceil(rows.length/20))),pageSize:20,showSizeChanger:false,onChange:setPage}} />
        </>}
      </ResourceState>}
    </Card>
  </Space>;
}

export function TencentCostPage() {
  const accounts = useResource<TencentAccount[]>('/admin/api/tencent/accounts');
  const [selected, setSelected] = useState<string | null>(null);
  const account = accounts.data?.find(item => item.id === selected) ?? accounts.data?.[0];
  return <PageHeader area="业务管理" title="腾讯云成本" description="按独立账号采集完整账月，查看该月全部产品、精确费用及后台执行结果。">
    <Space orientation="vertical" size={24} style={{width:'100%'}}>
      <Card><ResourceState {...accounts} empty={accounts.data?.length === 0}>
        <Form layout="vertical"><Form.Item label="腾讯云账号" style={{marginBottom:0}}><Select aria-label="腾讯云账号" value={account?.id} options={(accounts.data ?? []).map(item => ({value:item.id,label:`${item.alias}（${item.uin}）${item.is_enabled ? '' : ' · 已停用'}`}))} onChange={setSelected} style={{width:'100%',maxWidth:480}} /></Form.Item></Form>
      </ResourceState></Card>
      {account && <CostAccountPanel key={account.id} account={account} />}
    </Space>
  </PageHeader>;
}
export default TencentCostPage;
