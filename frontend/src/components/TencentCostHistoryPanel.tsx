import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Descriptions, Form, Input, Select, Space, Tag, Tooltip } from 'antd';
import type { TableColumnsType } from 'antd';
import { ReloadOutlined, RedoOutlined } from '@ant-design/icons';
import { ResourceState } from './ResourceState';
import { TencentCostTableCard } from './TencentCostTableCard';
import { ApiError, request } from '../services/http';
import { useResource } from '../services/useResource';
import type { CostJob } from './TencentCostJobDetail';

export interface CostHistoryPeriod { period_key: string; granularity: 'day' | 'month'; month?: string; begin?: string; end_exclusive?: string; expansion_reason?: string | null }
interface HistoryGap extends CostHistoryPeriod { reason_code: string; category: string; last_attempt_at: string | null; automatic_failures: number; automatic_paused: boolean }
export interface CostHistory {
  origin_status: 'unknown' | 'verified'; first_bill_period: string | null; earlier_history_unknown: boolean;
  source_window: { day_start: string; month_start: string; end_exclusive: string; basis: string };
  target_period_count: number; covered_period_count: number; earliest_success_period: string | null; last_success_at: string | null;
  continuous_coverage: { begin: string; end_exclusive: string } | null; recent: { required_count: number; covered_count: number };
  gaps: HistoryGap[]; unexplored: CostHistoryPeriod[]; pending_count: number; discovery_status: 'pending' | 'partial' | 'known_window_probed';
}
interface RangeIntent { scope: 'range' | 'all'; start_date?: string; end_date?: string; idempotency_key: string }
interface RangePreview {
  periods: CostHistoryPeriod[]; requested_scope: Record<string, unknown>; expanded: boolean; not_due: Array<string | CostHistoryPeriod>;
  outside_known_source_window: Array<string | CostHistoryPeriod>; total_count: number; preview_token: string; expansion_reasons?: string[]; accepted_count?: number;
  deferred_periods?: Array<string | CostHistoryPeriod>; history_origin_unknown?: boolean;
}
const expansionReasons:Record<string,string>={existing_complete_month:'命中已保存完整月，整月重取',outside_daily_source_window:'较早历史按来源原始月粒度重取',monthly_mode:'月模式按完整账月重取'};
const categories: Record<string,string> = { zero_unconfirmed:'零费用未确认', not_ready:'源端尚未准备', permission_denied:'权限不足', parameter_invalid:'参数不符合来源要求', upstream_failed:'源端返回异常', transient:'临时故障', confirmed_unavailable:'已核验来源不可查', outside_known_source_window:'已知来源窗口外', not_due:'尚未到期' };
const dateTime = (value?:string|null) => value ? new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(value)) : '-';
const periodName = (period:CostHistoryPeriod) => `${period.period_key}（${period.granularity==='month' ? '完整月' : '单日'}）`;
const scopeNames = (periods:Array<string|CostHistoryPeriod>) => periods.map(item=>typeof item==='string' ? item : periodName(item)).join('、');

export function TencentCostHistoryPanel({accountId,enabled,onAccepted,refreshRevision=0}: {accountId:string;enabled:boolean;onAccepted:(jobId:string)=>void;refreshRevision?:number}) {
  const base=`/admin/api/tencent/accounts/${accountId}`;
  const history=useResource<CostHistory>(`${base}/cost-history`,true);
  const [scope,setScope]=useState<'range'|'all'>('range');
  const [start,setStart]=useState(''); const [end,setEnd]=useState('');
  const [preview,setPreview]=useState<RangePreview|null>(null);
  const intent=useRef<RangeIntent|null>(null);
  const [busy,setBusy]=useState(false); const [feedback,setFeedback]=useState<{type:'error'|'info';text:string}|null>(null);
  const [search,setSearch]=useState(''); const [page,setPage]=useState(1);
  const [sort,setSort]=useState<'ascend'|'descend'|null>(null);
  const lastRefresh=useRef(refreshRevision);
  useEffect(()=>{if(lastRefresh.current!==refreshRevision){lastRefresh.current=refreshRevision;history.reload();}},[refreshRevision,history.reload]);
  function changeIntent() { setPreview(null); intent.current=null; setFeedback(null); }
  async function showPreview(next?: {start:string;end:string}) {
    const begin=next?.start ?? start; const finish=next?.end ?? end;
    const selectedScope=next ? 'range' : scope;
    if(selectedScope==='range' && (!begin || !finish || begin>finish)) {
      setFeedback({type:'error',text:'请选择有效的开始和结束日期，开始日期不得晚于结束日期'});return;
    }
    intent.current ??= {scope:selectedScope,...(selectedScope==='range'?{start_date:begin,end_date:finish}:{}),idempotency_key:crypto.randomUUID()};
    setBusy(true);setFeedback(null);
    try { const result=await request<RangePreview>(`${base}/cost-range-preview`,{method:'POST',body:intent.current});setPreview(result.data); }
    catch(error) { setFeedback({type:'error',text:error instanceof Error ? error.message : '范围预览失败，请重试'}); }
    finally {setBusy(false);}
  }
  async function accept() {
    if(!preview || !intent.current)return;
    setBusy(true);setFeedback(null);
    try {
      const result=await request<CostJob>(`${base}/cost-range-batches`,{method:'POST',body:{...intent.current,preview_token:preview.preview_token}});
      setFeedback({type:'info',text:`范围重拉批次 #${result.data.id} 已受理；各期间独立提交，请查看实际范围与延期结果。`});
      onAccepted(result.data.id);history.reload();
      setPreview(null);intent.current=null;
    } catch(error) { if(error instanceof ApiError && error.code==='TENCENT_RANGE_PREVIEW_CHANGED')setPreview(null);setFeedback({type:'error',text:error instanceof Error ? error.message : '受理结果未确认，请重试核实同一批次'}); }
    finally {setBusy(false);}
  }
  const data=history.data && Array.isArray(history.data.gaps) ? history.data : null;
  const gaps=(data?.gaps ?? []).filter(row=>!search || `${row.period_key} ${categories[row.category] ?? row.category} ${row.reason_code}`.includes(search));
  if(sort)gaps.sort((a,b)=>{
    if(!a.last_attempt_at || !b.last_attempt_at)return a.last_attempt_at ? -1 : b.last_attempt_at ? 1 : 0;
    const order=new Date(a.last_attempt_at).getTime()-new Date(b.last_attempt_at).getTime();return sort==='ascend'?order:-order;
  });
  const columns:TableColumnsType<HistoryGap>=[
    {key:'period',title:'缺失期间',dataIndex:'period_key',fixed:'left',width:150},
    {key:'granularity',title:'来源粒度',dataIndex:'granularity',width:100,render:value=>value==='month'?'完整月':'单日'},
    {key:'category',title:'原因',width:240,render:(_,row)=><Space orientation="vertical" size={4}><Tag color={row.category==='permission_denied'?'error':'warning'}>{categories[row.category] ?? '源端原因待核实'}</Tag><span style={{color:'var(--app-muted)',fontSize:12}}>{row.reason_code}</span></Space>},
    {key:'budget',title:'自动探测',width:220,render:(_,row)=>row.automatic_paused ? '自动探测已暂停，可人工重探' : `已失败 ${row.automatic_failures} 轮`},
    {key:'last',title:'最近探测（北京时间）',dataIndex:'last_attempt_at',width:190,sorter:true,sortOrder:sort,render:value=><span style={{color:'var(--app-muted)',fontSize:12,lineHeight:'20px',fontWeight:400}}>{dateTime(value)}</span>},
    {key:'action',title:'操作',width:96,fixed:'right',render:(_,row)=><Tooltip title="人工重新探测"><Button type="text" aria-label={`重新探测 ${row.period_key}`} icon={<RedoOutlined />} disabled={busy||!enabled} onClick={()=>{
      const from=row.granularity==='month'?`${row.period_key}-01`:row.period_key;
      const to=row.granularity==='month'?new Date(Number(row.period_key.slice(0,4)),Number(row.period_key.slice(5,7)),0).getDate():null;
      const until=to?`${row.period_key}-${String(to).padStart(2,'0')}`:row.period_key;
      setScope('range');setStart(from);setEnd(until);intent.current=null;setPreview(null);void showPreview({start:from,end:until});
    }} /></Tooltip>},
  ];
  const previewColumns:TableColumnsType<CostHistoryPeriod>=[
    {key:'period',title:'实际期间及粒度',fixed:'left',width:220,render:(_,row)=>periodName(row)},
    {key:'begin',title:'起点（北京时间）',dataIndex:'begin',width:220,render:value=>value ?? '-'},
    {key:'end',title:'终点（不含）',dataIndex:'end_exclusive',width:220,render:value=>value ?? '-'},
    {key:'reason',title:'范围说明',dataIndex:'expansion_reason',width:240,render:value=>value==='stored_month'?'命中已保存完整月，整月重取':value==='source_month_only'?'较早历史保留完整月原始粒度':value || '按请求期间执行'},
  ];
  return <Card title="历史回溯与范围重拉">
    <Space orientation="vertical" size={16} style={{width:'100%'}}>
      <ResourceState {...history}>{data && <>
        <Alert type="info" showIcon title={data.origin_status==='verified' ? `已核验账号费用发生起点：${data.first_bill_period}` : '账号费用发生起点未知'} description="来源可取窗口不代表账号全部费用历史。更早历史仍待评估补齐途径；空结果不等于零费用。" />
        <Descriptions column={{xs:1,md:2}} items={[
          {key:'state',label:'回溯状态',children:data.discovery_status==='known_window_probed'?'本轮已知来源目标已探测，更早历史未知':data.discovery_status==='partial'?(data.recent.covered_count>0?'近期已有可用结果，历史部分回溯':'历史部分回溯，近期尚无成功覆盖'):'等待历史发现'},
          {key:'recent',label:'近期实际覆盖',children:`${data.recent.covered_count} / ${data.recent.required_count} 个原始期间`},
          {key:'target',label:'本轮已知来源目标',children:`已覆盖 ${data.covered_period_count} / ${data.target_period_count} 个原始期间`},
          {key:'window',label:'来源能力窗口',children:`日：${data.source_window.day_start} 起；月：${data.source_window.month_start} 起；截至 ${data.source_window.end_exclusive}（不含）`},
          {key:'earliest',label:'最早成功核验期间',children:data.earliest_success_period ?? '尚无成功结果'},
          {key:'continuous',label:'连续覆盖（不跨缺口）',children:data.continuous_coverage ? `${data.continuous_coverage.begin} 至 ${data.continuous_coverage.end_exclusive}（不含）`:'尚无连续覆盖'},
          {key:'success',label:'最近成功时间（北京时间）',children:dateTime(data.last_success_at)},
          {key:'pending',label:'已受理待执行',children:`${data.pending_count} 个期间`},
        ]}/>
        <p style={{color:'var(--app-muted)',margin:0}}>来源依据：{data.source_window.basis==='cost-analysis-public-window-v1'?'腾讯云成本分析公开时间窗说明':data.source_window.basis}。月覆盖保留月粒度，不等同于日费用已覆盖。</p>
        <div style={{display:'flex',justifyContent:'space-between',gap:8,flexWrap:'wrap'}}><Button icon={<ReloadOutlined />} aria-label="刷新历史状态" onClick={history.reload}>刷新</Button><Input.Search aria-label="搜索缺失期间或原因" placeholder="搜索缺失期间或原因" value={search} onChange={event=>{setSearch(event.target.value);setPage(1);}} style={{maxWidth:320}} /></div>
        <TencentCostTableCard<HistoryGap> title="已探测缺口" rowKey={row=>`${row.granularity}:${row.period_key}`} columns={columns} dataSource={gaps} scroll={{x:1000}} locale={{emptyText:'暂无已探测失败缺口'}} pagination={{current:Math.min(page,Math.max(1,Math.ceil(gaps.length/10))),pageSize:10,onChange:setPage,showSizeChanger:false}} onChange={(_,__,sorter)=>{setSort(!Array.isArray(sorter)?sorter.order ?? null:null);setPage(1);}} />
        <p style={{margin:0}}>尚未探测 {data.unexplored.length} 个期间{data.unexplored.length ? `：${data.unexplored.slice(0,12).map(periodName).join('、')}${data.unexplored.length>12?'……':''}`:''}</p>
      </>}</ResourceState>
      <Form layout="vertical">
        <Form.Item label="重拉范围"><Select aria-label="重拉范围" value={scope} disabled={busy} style={{maxWidth:360}} options={[{value:'range',label:'指定期间'},{value:'all',label:'全部实际可取历史'}]} onChange={value=>{setScope(value);changeIntent();}} /></Form.Item>
        {scope==='range' ? <Space wrap align="start">
          <Form.Item label="开始日期"><Input aria-label="重拉开始日期" type="date" min="1970-01-01" value={start} disabled={busy} onChange={event=>{setStart(event.target.value);changeIntent();}} /></Form.Item>
          <Form.Item label="结束日期（含）"><Input aria-label="重拉结束日期" type="date" min={start || '1970-01-01'} value={end} disabled={busy} onChange={event=>{setEnd(event.target.value);changeIntent();}} /></Form.Item>
        </Space>:<Alert type="info" showIcon title="按当前已知来源窗口持续分片重拉，账号更早历史仍未知" />}
        <Button aria-label="预览实际执行范围" disabled={busy||!enabled} loading={busy} onClick={()=>void showPreview()}>预览实际执行范围</Button>
      </Form>
      {preview && <section aria-label="范围重拉预览">
        <Space orientation="vertical" size={16} style={{width:'100%'}}>
          <Alert type={preview.expanded?'warning':'info'} showIcon title={preview.expanded?'命中完整月，实际范围已扩展':`实际执行范围：${preview.total_count} 个期间`} description={`此预览不采集费用。共 ${preview.total_count} 个期间，本片可受理 ${preview.accepted_count ?? preview.total_count} 个。${(preview.expansion_reasons ?? []).map(reason=>expansionReasons[reason] ?? '来源要求整月重取').join('；')}确认后各期间独立提交，部分成功不代表全部范围成功。`} />
          <TencentCostTableCard<CostHistoryPeriod> title="实际执行期间" rowKey={row=>`${row.granularity}:${row.period_key}`} columns={previewColumns} dataSource={preview.periods} scroll={{x:900}} pagination={{pageSize:10,showSizeChanger:false}} />
          {!!preview.deferred_periods?.length && <Alert type="warning" showIcon title={`延期 ${preview.deferred_periods.length} 个期间`} description={scopeNames(preview.deferred_periods)} />}
          {!!preview.not_due.length && <Alert type="info" showIcon title="以下期间尚未到期" description={scopeNames(preview.not_due)} />}
          {!!preview.outside_known_source_window.length && <Alert type="warning" showIcon title="以下范围位于已知来源窗口外，不能据此认定没有费用" description={scopeNames(preview.outside_known_source_window)} />}
          <Button type="primary" aria-label="确认范围重拉" disabled={busy||!enabled} loading={busy} onClick={()=>void accept()}>确认范围重拉</Button>
        </Space>
      </section>}
      {feedback && <Alert type={feedback.type} showIcon title={feedback.text} />}
    </Space>
  </Card>;
}
