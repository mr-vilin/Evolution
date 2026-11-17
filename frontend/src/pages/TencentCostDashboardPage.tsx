import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, DatePicker, Descriptions, Form, Input, Select, Space, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { TencentCostTableCard } from '../components/TencentCostTableCard';
import { query, requestFile } from '../services/http';
import { useResource } from '../services/useResource';
import type { TencentAccount } from './TencentAccountsPage';

interface Change { value: string | null; reason: string | null }
interface Month { month: string; total: string | null; status: string; coverage_complete: boolean;
  due_date: string; latest_success_at: string | null; latest_task_status: string | null; mom: Change; yoy: Change }
interface Product { key: string; source_name: string; business_code: string | null; mapping_status: string;
  amounts: Record<string,string | null>; total: string }
interface Dashboard { account: {id:string;uin:string;alias:string}; currency:string; known_total:string;
  complete_total:string | null; months:Month[]; products:Product[]; start_month:string; end_month:string }
const statuses: Record<string,string> = {complete:'完整月已覆盖',missing:'未同步 / 缺口',not_due:'未到同步日',incomplete:'累计未完整',
  failed_retained:'采集失败，保留上次完整费用',refreshing_retained:'更新中，保留上次完整费用',failed:'采集失败 / 缺口',pending:'等待采集'};
const reasons: Record<string,string> = {incomplete_coverage:'覆盖不完整',zero_denominator:'对照月为零',incomparable_basis:'口径不可比',
  latest_collection_failed:'最近采集失败',latest_collection_pending:'最近采集未完成'};
function change(value: Change) { return value.value === null ? `-（${reasons[value.reason ?? ''] ?? '暂不可比'}）` : `${value.value}%`; }
function status(month: Month) { return <Tag color={month.status==='complete' ? 'success' : month.status.includes('failed') ? 'error' : 'warning'}>{statuses[month.status] ?? '待复核'}</Tag>; }
function units(value: string) { const [whole,fraction=''] = value.split('.'); return BigInt(`${whole}${fraction.padEnd(8,'0')}`); }
function Trend({months,currency}: {months:Month[];currency:string}) {
  const values = months.map(month=>month.total !== null && month.status==='complete' ? units(month.total) : null);
  const maximum = values.reduce<bigint>((max,value)=>value!==null && (value<0n ? -value : value)>max ? (value<0n ? -value : value) : max,1n);
  // BigInt只将正规化比例转为几何坐标，金额显示和汇总始终保留服务端十进制文本。
  const points = values.map((value,i)=>value===null ? null : {x:40+i*80,y:90-Number(value*70n/maximum)});
  return <div style={{overflowX:'auto'}}><svg role="img" aria-label="完整月费用趋势，缺失期间不连线" width={Math.max(320,months.length*80)} height="210">
    <line x1="0" y1="90" x2={Math.max(320,months.length*80)} y2="90" stroke="var(--app-line)" />
    {points.map((point,i)=><g key={months[i].month}>
      {point && i>0 && points[i-1] && <line x1={points[i-1]!.x} y1={points[i-1]!.y} x2={point.x} y2={point.y} stroke="var(--app-primary)" strokeWidth="2" />}
      {point && <circle cx={point.x} cy={point.y} r="4" fill="var(--app-primary)"><title>{`${months[i].month}：${months[i].total} ${currency}`}</title></circle>}
      <text x={40+i*80} y="184" textAnchor="middle" fill="var(--app-muted)" fontSize="12">{months[i].month}</text>
      {!point && <text x={40+i*80} y="110" textAnchor="middle" fill="var(--app-muted)" fontSize="12">缺口 / 待复核</text>}
    </g>)}
  </svg></div>;
}

function DashboardPanel({account}: {account:TencentAccount}) {
  const [start,setStart] = useState(dayjs().subtract(6,'month').format('YYYY-MM'));
  const [end,setEnd] = useState(dayjs().subtract(1,'month').format('YYYY-MM'));
  const [currency,setCurrency] = useState('CNY');
  const [search,setSearch] = useState('');
  const [page,setPage] = useState(1);
  const [exporting,setExporting] = useState(false);
  const [feedback,setFeedback] = useState<string | null>(null);
  const exportController = useRef<AbortController | null>(null);
  const params = query({start_month:start,end_month:end,currency});
  const base = `/admin/api/tencent/accounts/${account.id}`;
  const result = useResource<Dashboard>(`${base}/cost-dashboard${params}`);
  useEffect(()=>{setPage(1);setFeedback(null);setExporting(false);return ()=>exportController.current?.abort();},[params]);
  async function download() {
    const controller = new AbortController(); exportController.current = controller;
    setExporting(true);setFeedback(null);
    try {
      const file = await requestFile(`${base}/cost-export${params}`,controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(file);
      const anchor = document.createElement('a'); anchor.href=url;anchor.download=`tencent-cost-${account.uin}-${start}-${end}.csv`;
      document.body.appendChild(anchor);anchor.click();anchor.remove();URL.revokeObjectURL(url);
    } catch(error) { if (!controller.signal.aborted) setFeedback(error instanceof Error ? error.message : '导出失败，请重试'); }
    finally { if (!controller.signal.aborted) setExporting(false); }
  }
  const data = result.data;
  const rows = (data?.products ?? []).filter(row=>`${row.source_name} ${row.business_code ?? ''}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const productColumns: TableColumnsType<Product> = [
    {key:'name',title:'产品名称',dataIndex:'source_name',fixed:'left',width:200,ellipsis:true},
    {key:'code',title:'产品编码（BusinessCode）',dataIndex:'business_code',width:200,render:value=>value || '-'},
    {key:'mapping',title:'产品映射',dataIndex:'mapping_status',width:120,render:value=><Tag color={value==='mapped' ? 'success':'warning'}>{value==='mapped' ? '已映射':value==='ambiguous' ? '同名歧义':'未映射'}</Tag>},
    ...(data?.months ?? []).map(month=>({key:month.month,title:month.month,width:170,align:'right' as const,render:(_:unknown,row:Product)=>row.amounts[month.month] ?? '-'})),
    {key:'total',title:'已采集小计（元）',dataIndex:'total',align:'right',width:180},
  ];
  const monthColumns: TableColumnsType<Month> = [
    {key:'month',title:'账月',dataIndex:'month',fixed:'left',width:120},
    {key:'total',title:'费用（元）',dataIndex:'total',width:180,align:'right',render:value=>value ?? '-'},
    {key:'status',title:'覆盖状态',width:250,render:(_,row)=>status(row)},
    {key:'mom',title:'环比',dataIndex:'mom',width:220,render:change},
    {key:'yoy',title:'同比',dataIndex:'yoy',width:220,render:change},
    {key:'due',title:'开放采集日（北京时间）',dataIndex:'due_date',width:210,render:value=><span style={{fontSize:12,color:'var(--app-muted)'}}>{value ?? '-'}</span>},
    {key:'success',title:'最近成功（北京时间）',dataIndex:'latest_success_at',width:210,render:value=><span style={{fontSize:12,color:'var(--app-muted)'}}>{value ? new Date(value).toLocaleString('sv-SE',{timeZone:'Asia/Shanghai'}) : '-'}</span>},
  ];
  return <Space orientation="vertical" size={24} style={{width:'100%'}}>
    <Card><Space wrap align="end">
      <Form.Item label="起始账月" style={{marginBottom:0}}><DatePicker aria-label="起始账月" picker="month" value={dayjs(`${start}-01`)} minDate={dayjs('1970-01-01')} maxDate={dayjs()} allowClear={false} onChange={value=>value && setStart(value.format('YYYY-MM'))} /></Form.Item>
      <Form.Item label="结束账月" style={{marginBottom:0}}><DatePicker aria-label="结束账月" picker="month" value={dayjs(`${end}-01`)} minDate={dayjs('1970-01-01')} maxDate={dayjs()} allowClear={false} onChange={value=>value && setEnd(value.format('YYYY-MM'))} /></Form.Item>
      <Form.Item label="币种" style={{marginBottom:0}}><Select aria-label="币种" value={currency} onChange={setCurrency} options={['CNY','USD','HKD'].map(value=>({value,label:value}))} style={{width:100}} /></Form.Item>
      <Button aria-label="刷新看板" icon={<ReloadOutlined />} onClick={result.reload}>刷新看板</Button>
      <Button aria-label="导出全部产品" icon={<DownloadOutlined />} disabled={!data || result.loading || Boolean(result.error)} loading={exporting} onClick={()=>void download()}>导出全部产品</Button>
    </Space><p style={{color:'var(--app-muted)',marginBottom:0}}>费用账单 / 总费用 / 产品维度 / 元；每次最多 120 个月。当月整月费用待下月 3 日开放，缺口不代表零费用。</p></Card>
    {feedback && <Alert showIcon type="error" title={feedback} />}
    <ResourceState {...result}>{data && <>
      <Card title="费用概览"><Descriptions column={{xs:1,md:2}} items={[
        {key:'known',label:'已采集金额',children:`${data.known_total} ${data.currency}`},
        {key:'complete',label:'完整范围总额',children:data.complete_total === null ? '费用存在缺口或待复核结果，完整范围总额暂不可用':`${data.complete_total} ${data.currency}`},
        {key:'account',label:'账号',children:`${data.account.alias}（${data.account.uin}）`},
        {key:'range',label:'账月范围',children:`${data.start_month} 至 ${data.end_month}`},
      ]} /></Card>
      <Card title="完整月费用趋势"><Trend months={data.months} currency={data.currency} /></Card>
      <TencentCostTableCard<Month> title="账月覆盖与比较" rowKey="month" columns={monthColumns} dataSource={data.months} pagination={false} scroll={{x:1510}} />
      <TencentCostTableCard<Product> title="全部产品月度费用" rowKey="key" columns={productColumns} dataSource={rows} scroll={{x:700+data.months.length*170}} pagination={{current:Math.min(page,Math.max(1,Math.ceil(rows.length/10))),pageSize:10,onChange:setPage,showSizeChanger:false}}><Space style={{display:'flex',justifyContent:'flex-end',marginBottom:16}}><Input.Search aria-label="搜索费用产品" placeholder="搜索产品名称或编码" value={search} allowClear onChange={event=>{setSearch(event.target.value);setPage(1);}} /></Space>
        <p style={{color:'var(--app-muted)'}}>已映射产品在完整月缺行显示 0；未映射、同名歧义和未覆盖期间显示 -，不推定产品跨月身份。导出包含全部产品，不受当前搜索与分页限制。</p>
      </TencentCostTableCard>
    </>}</ResourceState>
  </Space>;
}

export function TencentCostDashboardPage() {
  const accounts = useResource<TencentAccount[]>('/admin/api/tencent/accounts');
  const [selected,setSelected] = useState<string | null>(null);
  const account = accounts.data?.find(row=>row.id===selected) ?? accounts.data?.[0];
  return <><PageHeader title="腾讯云费用看板" description="从已采集费用查看多月份趋势、覆盖与全部产品；浏览页面不调用腾讯云。" />
    <Card style={{marginBottom:24}}><ResourceState {...accounts} empty={accounts.data?.length===0}><Form layout="vertical"><Form.Item label="腾讯云账号" style={{marginBottom:0}}><Select aria-label="腾讯云账号" value={account?.id} onChange={setSelected} options={(accounts.data ?? []).map(row=>({value:row.id,label:`${row.alias}（${row.uin}）${row.is_enabled ? '':' · 已停用'}`}))} style={{width:'100%',maxWidth:480}} /></Form.Item></Form></ResourceState></Card>
    {account && !accounts.error && <DashboardPanel key={account.id} account={account} />}
  </>;
}
export default TencentCostDashboardPage;
