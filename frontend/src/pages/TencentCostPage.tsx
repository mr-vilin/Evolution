import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, DatePicker, Descriptions, Form, Input, Select, Space, Switch, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import { ReloadOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { TencentCostTableCard } from '../components/TencentCostTableCard';
import { useTencentSort, decimalValue, formatTencentTime } from '../components/tencentPresentation';
import { request } from '../services/http';
import { useResource } from '../services/useResource';
import type { TencentAccount } from './TencentAccountsPage';
import { TencentCostJobDetail, costStatusTag as statusTag, costStatuses as statuses, type CostJob } from '../components/TencentCostJobDetail';

import { TencentCostHistoryPanel } from '../components/TencentCostHistoryPanel';
import { TencentCostPolicyFields, defaultCostPolicy, costPolicyErrors, type CostPolicy } from '../components/TencentCostPolicyFields';

interface CostConfig { run_policy?: CostPolicy; revision: number; is_enabled: boolean; frequency: 'manual' | 'monthly' | 'daily' | 'weekly'; execution_time?: string; next_execution_at?: string | null; last_success_period?: string | null; last_success_month?: string | null; last_success_at?: string | null; currency: 'CNY'; latest_eligible_month: string; latest_eligible_date?: string }
interface CostItem { id: string; source_name: string; business_code: string | null; mapping_status: string; amount: string }
interface Period { granularity?: string; covered_through?: string; missing_dates?: string[]; id: string; month: string; currency: string; total: string; coverage: { status: string; zero_evidence?: string | null }; latest_job_id: string; items: CostItem[] }
function CostAccountPanel({ account }: { account: TencentAccount }) {
  const base = `/admin/api/tencent/accounts/${account.id}`;
  const config = useResource<CostConfig>(`${base}/cost-config`, true);
  const jobs = useResource<CostJob[]>(`${base}/cost-jobs`, true);
  const [frequency,setFrequency]=useState<'manual' | 'monthly' | 'daily' | 'weekly'>('manual');
  const [executionTime,setExecutionTime]=useState('13:30');
  const batchKey=useRef<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [policy,setPolicy] = useState<CostPolicy>(defaultCostPolicy);
  const [month, setMonth] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'info' | 'error'; text: string } | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [historyRevision, setHistoryRevision] = useState(0);
  const keys = useRef(new Map<string,string>());
  const detail = useResource<CostJob>(jobId ? `/admin/api/tencent/cost-jobs/${jobId}` : null, true);
  const period = useResource<Period>(month ? `${base}/cost-periods/${month}` : null, true);
  const { message } = App.useApp();
  useEffect(() => {
    if (config.data) { setEnabled(config.data.is_enabled); setFrequency(config.data.frequency); setExecutionTime(config.data.execution_time ?? '13:30'); setPolicy({...defaultCostPolicy,...config.data.run_policy}); setMonth(value => value ?? config.data!.latest_eligible_month); }
  }, [config.data]);
  useEffect(() => { if (!jobId && jobs.data?.length) setJobId(jobs.data[0].id); }, [jobs.data,jobId]);
  useEffect(() => {
    if (detail.data?.month && ['succeeded','failed'].includes(detail.data.status)) keys.current.delete(detail.data.month);
  }, [detail.data]);
  async function save() {
    if (!config.data) return;
    if (Object.keys(costPolicyErrors(policy)).length) { setFeedback({type:'error',text:'请修正执行策略中的字段错误'}); return; }
    if (!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(executionTime)) { setFeedback({type:'error',text:'请输入有效北京时间，格式为时:分'}); return; }
    setBusy(true); setFeedback(null);
    try {
      await request(`${base}/cost-config`, { method:'PUT', body:{ revision:config.data.revision,is_enabled:enabled,frequency,execution_time:executionTime,currency:'CNY',run_policy:policy } });
      message.success('成本配置已保存'); config.reload(); setHistoryRevision(value=>value+1);
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
  async function submitBatch() {
    if (!config.data?.is_enabled || !['monthly','daily','weekly'].includes(config.data.frequency)) return;
    batchKey.current ??= crypto.randomUUID();
    setBusy(true);setFeedback(null);
    try {
      const accepted=await request<CostJob>(`${base}/cost-batches`,{method:'POST',body:{idempotency_key:batchKey.current}});
      setJobId(accepted.data.id);jobs.reload();
      setFeedback({type:'info',text:`费用复核批次 #${accepted.data.id} 已受理，请查看各期间结果。`});
      batchKey.current=null;
    } catch(error) {setFeedback({type:'error',text:error instanceof Error ? error.message : '受理未确认，请重试核实同一批次'});}
    finally {setBusy(false);}
  }
  const active = detail.data?.month === month && ['pending','running','retry_wait'].includes(detail.data.status);
  const sorting=useTencentSort<CostItem>({amount:row=>decimalValue(row.amount)},()=>setPage(1));
  const rows = sorting.rows((period.data?.items ?? []).filter(row => !search || `${row.source_name} ${row.business_code ?? ''}`.includes(search)));
  const columns: TableColumnsType<CostItem> = [
    {key:'name',title:'产品名称',dataIndex:'source_name',fixed:'left',width:220,ellipsis:true},
    {key:'code',title:'产品编码（BusinessCode）',dataIndex:'business_code',width:220,render:value => value || '-'},
    {key:'mapping',title:'产品映射',dataIndex:'mapping_status',width:140,render:value => <Tag color={value==='mapped' ? 'success' : 'warning'}>{value==='mapped' ? '已映射' : value==='ambiguous' ? '同名歧义' : '未映射'}</Tag>},
    {key:'amount',...sorting.column('amount'),title:'总费用（元）',dataIndex:'amount',align:'right',width:180},
  ];
  return <Space orientation="vertical" size={24} style={{width:'100%'}}>
    <Card title="成本配置">
      <ResourceState {...config}>
        <Form layout="vertical">
          <Form.Item label="成本能力"><Switch aria-label="成本能力" checked={enabled} onChange={setEnabled} disabled={busy || !config.data} checkedChildren="开启" unCheckedChildren="关闭" /></Form.Item>
          <Form.Item label="采集方式"><Select aria-label="采集方式" value={frequency} onChange={setFrequency} options={[{value:'manual',label:'手动采集完整月'},{value:'monthly',label:'每月 3 日自动采集并复核近期两月'},{value:'daily',label:'每日自动采集，截至昨日'},{value:'weekly',label:'每周日自动采集，截至昨日'}]} disabled={busy || !config.data} style={{maxWidth:320}} /></Form.Item>
          {frequency !== 'manual' && <Form.Item label="北京时间执行时刻" help={`${frequency === 'monthly' ? '每月 3 日' : frequency === 'weekly' ? '固定每周日' : '每天'}，Asia/Shanghai；13:30 为可修改建议，按保存时刻执行。`}><Input aria-label="北京时间执行时刻" type="time" value={executionTime} onChange={event => setExecutionTime(event.target.value)} disabled={busy} style={{maxWidth:200}} /></Form.Item>}
          <Descriptions column={{xs:1,md:2}} items={[
            {key:'next',label:'下次计划执行（北京时间）',children:config.data?.next_execution_at ? formatTencentTime(config.data.next_execution_at) : '未启用自动计划'},
            {key:'cutoff',label:frequency==='daily' || frequency==='weekly' ? '费用截止日期' : '费用截止账月',children:(frequency==='daily' || frequency==='weekly' ? config.data?.latest_eligible_date : config.data?.latest_eligible_month) ?? '-'},
            {key:'success',label:frequency==='daily' || frequency==='weekly' ? '最近成功期间' : '最近成功账月',children:(frequency==='daily' || frequency==='weekly' ? config.data?.last_success_period : config.data?.last_success_month) ?? '尚无成功结果'},
            {key:'successTime',label:'最近成功时间（北京时间）',children:config.data?.last_success_at ? formatTencentTime(config.data.last_success_at) : '-'},
          ]} />
          {(frequency==='daily' || frequency==='weekly') && <Alert type="info" showIcon title="按日补缺并复核当月截至昨日及上月；已有完整月按整月复核。" description="空日与全零日尚缺独立就绪证据，保留原费用并显示未确认缺口。" />}
          <p style={{color:'var(--app-muted)'}}>费用账单 · 总费用 · 产品维度 · 人民币（CNY）</p>
          <TencentCostPolicyFields policy={policy} onChange={setPolicy} disabled={busy || !config.data} />
          <Button onClick={() => void save()} disabled={busy || !config.data} loading={busy}>保存配置</Button>
        </Form>
      </ResourceState>
    </Card>
    <TencentCostHistoryPanel accountId={account.id} enabled={!!config.data?.is_enabled && enabled === config.data.is_enabled} refreshRevision={historyRevision} onAccepted={id=>{setJobId(id);jobs.reload();detail.reload();}} />
    <Card title="完整账月采集">
      <Space wrap>
        <DatePicker aria-label="完整账月" picker="month" format="YYYY-MM" value={month ? dayjs(`${month}-01`) : null} maxDate={config.data ? dayjs(`${config.data.latest_eligible_month}-01`).endOf('month') : undefined} minDate={dayjs('1970-01-01')} allowClear={false} onChange={value => {setMonth(value?.format('YYYY-MM') ?? null);setSearch('');setPage(1);setFeedback(null);}} />
        <Button aria-label="采集所选账月" type="primary" loading={busy} disabled={busy || !config.data?.is_enabled || !month || Boolean(active) || enabled !== config.data.is_enabled} onClick={() => void submit()}>采集所选账月</Button>
        {config.data && ['monthly','daily','weekly'].includes(config.data.frequency) && <Button aria-label={config.data.frequency==='monthly' ? '立即执行月度复核' : '立即执行日周复核'} loading={busy} disabled={busy || config.loading || !config.data.is_enabled || enabled !== config.data.is_enabled} onClick={() => void submitBatch()}>{config.data.frequency==='monthly' ? '立即执行月度复核' : '立即执行日周复核'}</Button>}
        <Button aria-label="刷新结果" icon={<ReloadOutlined />} onClick={() => {config.reload();jobs.reload();detail.reload();period.reload();setHistoryRevision(value=>value+1);}}>刷新结果</Button>
      </Space>
      <p style={{color:'var(--app-muted)'}}>按北京时间每月 3 日开放上月。每月 1–2 日最多选择上上月；受理后由后台执行。</p>
      {feedback && <Alert type={feedback.type} showIcon title={feedback.text} style={{marginBottom:16}} />}
      <ResourceState {...jobs}>
        <Form layout="vertical"><Form.Item label="查看任务"><Select aria-label="查看任务" placeholder="暂无采集任务" value={jobId} options={(jobs.data ?? []).map(job => ({value:job.id,label:`${job.kind==='batch' ? '费用父批次' : job.period_key ?? job.month} · #${job.id} · ${statuses[job.status] ?? '未知状态'}`}))} onChange={setJobId} style={{width:'100%',maxWidth:480}} /></Form.Item></Form>
      </ResourceState>
      {jobId && <ResourceState {...detail}>{detail.data && <TencentCostJobDetail job={detail.data}
        canRerun={!!config.data?.is_enabled && account.is_enabled && !busy}
        onRerun={id => { setJobId(id); jobs.reload(); }} />}</ResourceState>}
    </Card>
    <TencentCostTableCard<CostItem> title="所选账月费用" showTable={!period.loading && !period.error && !!period.data} rowKey="id" columns={columns} dataSource={rows} onChange={sorting.onChange} scroll={{x:760}} pagination={{current:Math.min(page,Math.max(1,Math.ceil(rows.length/20))),pageSize:20,showSizeChanger:false,onChange:setPage}}>
      {period.error?.code === 'TENCENT_PERIOD_NOT_FOUND' ? <Alert type="info" showIcon title="该账月尚无完整费用结果" /> : <ResourceState {...period}>
        {period.data && <>
          {period.data.granularity==='day' && <Alert type="info" showIcon title={`原始日费用累计；累计至 ${period.data.covered_through ?? '-'}，缺 ${period.data.missing_dates?.length ?? 0} 日`} style={{marginBottom:16}} />}
          <Descriptions column={{xs:1,md:2}} items={[
            {key:'month',label:'账月',children:period.data.month}, {key:'total',label:'总费用',children:`${period.data.total} ${period.data.currency}`},
            {key:'coverage',label:'覆盖',children:<Tag color={period.data.coverage.status==='complete' ? 'success':'warning'}>{period.data.coverage.status==='complete' ? '完整月已覆盖':'累计未完整'}</Tag>}, {key:'latest',label:'最近成功任务',children:`#${period.data.latest_job_id}`},
            {key:'basis',label:'费用口径',children:'费用账单 / 总费用 / 产品'},
          ]} />
          <Space style={{display:'flex',justifyContent:'flex-end',marginBottom:16}}><Input.Search aria-label="搜索费用产品" placeholder="搜索产品名称或编码" value={search} allowClear onChange={event => {setSearch(event.target.value);setPage(1);}} style={{width:260}} /></Space>

        </>}
      </ResourceState>}
    </TencentCostTableCard>
  </Space>;
}

export function TencentCostPage() {
  const accounts = useResource<TencentAccount[]>('/admin/api/tencent/accounts');
  const [selected, setSelected] = useState<string | null>(null);
  const account = accounts.data?.find(item => item.id === selected) ?? accounts.data?.[0];
  return <PageHeader area="业务管理" title="腾讯云成本" description="按独立账号采集日/月费用，切换自动频率并查看完整产品、精确费用及实际执行结果。">
    <Space orientation="vertical" size={24} style={{width:'100%'}}>
      <Card><ResourceState {...accounts} empty={accounts.data?.length === 0}>
        <Form layout="vertical"><Form.Item label="腾讯云账号" style={{marginBottom:0}}><Select aria-label="腾讯云账号" value={account?.id} options={(accounts.data ?? []).map(item => ({value:item.id,label:`${item.alias}（${item.uin}）${item.is_enabled ? '' : ' · 已停用'}`}))} onChange={setSelected} style={{width:'100%',maxWidth:480}} /></Form.Item></Form>
      </ResourceState></Card>
      {account && <CostAccountPanel key={account.id} account={account} />}
    </Space>
  </PageHeader>;
}
export default TencentCostPage;
