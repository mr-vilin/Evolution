import { useRef, useState } from 'react';
import { Alert, App, Button, Collapse, Descriptions, Form, Select, Space, Tag } from 'antd';
import dayjs from 'dayjs';
import { request } from '../services/http';

export interface CostAttempt {
  id: string; attempt_no: number; status: string; error_code?: string | null; return_state?: string;
  input_capture_status?: string; output_capture_status?: string;
  request_id?: string | null; failure_evidence?: Record<string, unknown> | null;
  started_at?: string | null; finished_at?: string | null;
  execution_input: Record<string, unknown>; execution_output: Record<string, unknown> | null;
}
export interface CostScopePeriod {granularity:string;period_key:string;month?:string;begin?:string;end_exclusive?:string;expansion_reason?:string|null}
export interface CostJob {
  requested_scope?: {scope:string;start_date?:string;end_date?:string}; requested_periods?: CostScopePeriod[]; scope_status?:string; earlier_history_unknown?:boolean; expanded?:boolean; expansion_reasons?:string[]; not_due?:Array<string|CostScopePeriod>; outside_known_source_window?:Array<string|CostScopePeriod>;
  id: string; month: string | null; granularity?: 'day' | 'month'; period_key?: string; periods?: CostScopePeriod[]; deferred_periods?: Array<string|CostScopePeriod>; blocked_periods?: Array<{period_key:string;reason_code:string}>; kind?: 'batch' | 'period'; parent_job_id?: string | null; children?: CostJob[]; deferred_months?: string[]; blocked_months?: Array<{month:string;reason_code:string}>; months?: string[]; scheduled_at?: string | null; status: string; error_code?: string | null; source_job_id?: string | null;
  next_attempt_at?: string | null; deadline_at?: string | null; queue_deadline_at?: string | null; attempts?: CostAttempt[];
}
export const costStatuses: Record<string, string> = { pending:'等待执行',running:'正在采集',retry_wait:'等待自动重试',succeeded:'已成功提交',failed:'执行失败',unknown:'结果未知',partial_failed:'部分失败，仍有缺口',no_work:'无待同步期间' };
export function costStatusTag(status: string) {
  return <Tag color={status === 'succeeded' ? 'success' : status === 'failed' ? 'error' : status === 'partial_failed' ? 'warning' : status === 'running' ? 'processing' : status === 'retry_wait' || status === 'unknown' ? 'warning' : 'default'}>{costStatuses[status] ?? '未知状态'}</Tag>;
}
const labels: Record<string, string> = {
  granularity:'原始粒度',period_key:'实际期间',requested_period_key:'请求期间',month:'账月',begin:'期间起点',end_exclusive:'期间终点（不含）',policy:'冻结执行策略',max_attempts:'最大总尝试次数',
  deadline_seconds:'单次预算（秒）',run_deadline_seconds:'执行轮次预算（秒）',retry_base_seconds:'退避基数（秒）',retry_max_seconds:'最大退避（秒）',
  retry_jitter_seconds:'抖动上限（秒）',lease_seconds:'租约（秒）',heartbeat_seconds:'心跳（秒）',queue_limit:'配置队列上限',queue_deadline_seconds:'首次领取等待预算（秒）',max_rows:'单次产品行数上限',
  handler:'处理契约',contract:'返回契约',business:'业务',account_id:'账号标识',uin:'账号 UIN',credential_ref:'受控凭据引用',credential_revision:'凭据修订',
  config_id:'配置标识',config_revision:'配置修订',control_revision:'启停修订',frequency:'采集频率',currency:'币种',dataset_epoch:'初始化世代',actor_id:'发起管理员',
  execution_identity:'执行身份核验方式',attempt_no:'尝试序号',generation:'隔离代次',trigger_request_id:'受理关联标识',attempt_request_id:'本次请求关联标识',
  upstream_params:'实际上游参数',BeginTime:'起始时间',EndTime:'截至时间',PeriodType:'期间类型',BillType:'账单类型',FeeType:'费用类型',Dimensions:'聚合维度',NeedConditionValue:'产品映射证据开关',
  status:'返回状态',period_id:'费用期间标识',job_id:'逻辑任务标识',attempt_id:'尝试标识',row_count:'产品条数',total:'精确总费用',request_ids:'实际上游请求标识',coverage:'覆盖证据',committed_at:'原提交时间',
  reason_code:'原因编码',upstream_request_id:'上游请求标识',upstream_response_state:'上游响应观察状态',observed_at:'失联观察时间',isolation_generation:'接管隔离代次',
  archive_repaired:'归档已修复',archive_repaired_at:'归档修复时间',source:'恢复依据',source_job_id:'原任务标识',rerun_reason:'重跑原因',
  request_namespace:'受理命名空间',timezone:'业务时区',bill_type:'账单类型',fee_type:'费用口径',dimensions:'聚合维度',currency_source:'币种声明依据',zero_evidence:'零费用证据',
};
const scopePeriodName=(period:CostScopePeriod)=>period.period_key+'（'+(period.granularity==='month'?'完整月':'单日')+'）';
const scopeList=(periods:Array<string|CostScopePeriod>)=>periods.map(period=>typeof period==='string'?period:scopePeriodName(period)).join('、');
function EvidenceValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span>-</span>;
  if (Array.isArray(value)) return value.length ? <ol style={{margin:0,paddingInlineStart:24}}>{value.map((item,index) => <li key={index}><EvidenceValue value={item} /></li>)}</ol> : <span>空列表</span>;
  if (typeof value === 'object') return <Descriptions size="small" column={1} items={Object.entries(value).map(([key,item]) => ({key,label:labels[key] ?? key,children:<EvidenceValue value={item} />}))} />;
  if (typeof value === 'boolean') return <span>{value ? '是' : '否'}</span>;
  return <span style={{overflowWrap:'anywhere'}}>{String(value) || '-'}</span>;
}
const time = (value?: string | null) => value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';
const returns: Record<string,string> = { VALUE:'已捕获真实返回',NOT_RETURNED:'因异常未正常返回',UNKNOWN:'返回结果未知，尚无可核实返回',NULL:'明确返回空值',VOID:'按契约无返回值' };

export function TencentCostJobDetail({ job, canRerun, onRerun }: { job: CostJob; canRerun: boolean; onRerun: (jobId: string) => void }) {
  const { message } = App.useApp();
  const [reason,setReason] = useState<'after_fix' | 'refresh_result'>('after_fix');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState<string | null>(null);
  const keys = useRef(new Map<string,string>());
  async function rerun() {
    const intent = `${job.id}:${reason}`;
    const key = keys.current.get(intent) ?? crypto.randomUUID(); keys.current.set(intent,key);
    setBusy(true);setError(null);
    try {
      const result = await request<CostJob>(`/admin/api/tencent/cost-jobs/${job.id}/rerun`,{method:'POST',body:{idempotency_key:key,reason}});
      message.success(`重跑任务 #${result.data.id} 已受理`);onRerun(result.data.id);
    } catch (failure) { setError(failure instanceof Error ? failure.message : '受理结果未确认，请用同一原因重试核实'); }
    finally { setBusy(false); }
  }
  return <Space orientation="vertical" size={16} style={{width:'100%'}}>
    <Descriptions column={{xs:1,md:2}} items={[
      {key:'job',label:'逻辑任务',children:`#${job.id} / ${job.kind === 'batch' ? '费用父批次' : `${job.period_key ?? job.month}${job.granularity==='day' ? '（单日）' : ''}`}`},
      {key:'status',label:'逻辑任务状态',children:costStatusTag(job.status)},
      {key:'source',label:'原任务',children:job.source_job_id ? `#${job.source_job_id}` : '-'},
      {key:'reason',label:'最近原因',children:job.error_code ?? '-'},
      {key:'next',label:'下次重试时间',children:time(job.next_attempt_at)},
      {key:'deadline',label:'执行轮次截止',children:time(job.deadline_at)},
      {key:'queue',label:'首次领取等待截止',children:time(job.queue_deadline_at)},
    ]} />
    {job.status === 'retry_wait' && <Alert type="warning" showIcon title="当前尝试失败，任务将按冻结策略自动重试" description="等待重试期间保留本配置串行资格，其他配置可继续执行。" />}
    {job.status === 'failed' && <Alert type="error" showIcon title="任务已结束，将不再自动重试" description="查看逐次原因，修复问题后可人工重跑；重跑会创建关联的新任务。" />}
    {job.granularity==='day' && job.error_code==='TENCENT_COST_ZERO_UNCONFIRMED' && <Alert type="warning" showIcon title="日零费用尚未确认，原费用已保留" description="腾讯云公开接口没有独立日级就绪证明；请核查后人工重跑，不以整月就绪证明单日为零。" />}
    {job.kind === 'batch' && <>
      {(job.scope_status && job.scope_status!=='complete') && job.status==='succeeded' && <Alert type="warning" showIcon title="本片已完成，申请范围仍未全部覆盖" description="请继续查看延期、尚未到期和来源窗口外的期间；本片成功不代表全范围费用均已取得。" />}
      {job.requested_scope && <Descriptions column={1} items={[
        {key:'requested',label:'申请范围',children:job.requested_scope.scope==='all'?'全部实际可取历史（当前已知来源目标）':`${job.requested_scope.start_date} 至 ${job.requested_scope.end_date}（含结束日）`},
        {key:'actual',label:'本片实际期间及粒度',children:(job.periods ?? []).map(scopePeriodName).join('、') || '本片无已受理期间'},
      ]}/>}
      {(job.requested_scope && job.earlier_history_unknown) && <Alert type="info" showIcon title="账号费用发生起点仍未知，更早历史待评估" />}
      {!!job.not_due?.length && <Alert type="info" showIcon title="以下期间尚未到期" description={scopeList(job.not_due)} />}
      {!!job.outside_known_source_window?.length && <Alert type="warning" showIcon title="以下期间位于已知来源窗口外，历史发生情况未知" description={scopeList(job.outside_known_source_window)} />}
      {job.blocked_periods?.map(item=><Alert key={item.period_key} type="warning" showIcon title={`${item.period_key}：已达到自动补漏上限，请核查后人工重跑。`} />)}
      {!!job.deferred_periods?.length && <Alert type="warning" showIcon title="仍有旧期间缺口等待补漏" description={scopeList(job.deferred_periods)} />}
      <Alert type="info" showIcon title={job.periods ? "父批次仅汇总期间结果，不产生执行尝试" : "父批次仅汇总账月结果，不产生执行尝试"} description="各期间独立提交；本片子任务成功不代表延期或未知范围已完成，失败期间可分别查看和重跑。" />
      {!!job.blocked_months?.length && <Alert type="warning" showIcon title="部分旧账月已达到自动补漏上限" description={`${job.blocked_months.map(item => item.month).join('、')}：请核查权限或历史可查范围，修复后手动重跑对应账月。`} />}
      {(job.deferred_months?.length ?? 0)>0 && <Alert type="warning" showIcon title={`仍有 ${job.deferred_months!.length} 个旧账月缺口等待后续补漏`} description={job.deferred_months!.join('、')} />}
      <Space orientation="vertical" size={8}>{job.children?.map(child => <Space key={child.id} wrap>
        <span>{child.period_key ?? child.month}{child.granularity==='day' ? '（单日）' : ''}</span>{costStatusTag(child.status)}<span>{child.error_code ?? ''}</span>
        <Button aria-label={child.period_key ? `查看期间 ${child.period_key}` : `查看账月 ${child.month}`}  onClick={() => onRerun(child.id)}>{child.granularity==='day' ? '查看期间':'查看账月'}</Button>
      </Space>)}</Space>
    </>}
    {job.kind !== 'batch' && (!job.attempts?.length ? <p>任务尚未实际执行，没有尝试输入或返回记录。</p> : <Collapse key={job.id} defaultActiveKey={[job.attempts.at(-1)!.id]} items={job.attempts.map(attempt => ({
      key:attempt.id,label:`第 ${attempt.attempt_no} 次尝试 · ${costStatuses[attempt.status] ?? attempt.status}`,
      children:<Space orientation="vertical" size={16} style={{width:'100%'}}>
        <Descriptions column={{xs:1,md:2}} items={[
          {key:'status',label:'当次状态',children:costStatusTag(attempt.status)},
          {key:'return',label:'返回事实',children:returns[attempt.return_state ?? (attempt.execution_output ? 'VALUE' : 'UNKNOWN')] ?? '未知返回形态'},
          {key:'capture',label:'返回保存状态',children:attempt.output_capture_status === 'CAPTURED' ? '完整已保存' : attempt.output_capture_status === 'FAILED' ? '归档缺口，等待核实修复' : attempt.output_capture_status === 'NO_CONTENT' ? '确认无正常返回内容' : attempt.execution_output ? '完整已保存' : '无可用内容'},
          {key:'start',label:'实际开始时间',children:time(attempt.started_at)},
          {key:'finish',label:'已核实结束时间',children:time(attempt.finished_at)},
          {key:'error',label:'当次原因',children:attempt.error_code ?? '-'},
          {key:'request',label:'当次请求关联标识',children:attempt.request_id ?? '历史未采集'},
        ]} />
        <section aria-label={`第 ${attempt.attempt_no} 次实际脱敏输入`}><h3 className="section-title">实际脱敏输入</h3><EvidenceValue value={attempt.execution_input} /></section>
        <section aria-label={`第 ${attempt.attempt_no} 次真实返回`}><h3 className="section-title">真实返回</h3>{attempt.execution_output === null ? <p>{attempt.return_state === 'VALUE' ? '已观察到返回，当前归档存在缺口，等待原事务回执修复' : returns[attempt.return_state ?? 'UNKNOWN']}</p> : <EvidenceValue value={attempt.execution_output} />}</section>
        {attempt.failure_evidence && <section aria-label="安全失败或恢复证据"><h3 className="section-title">安全失败或恢复证据</h3><EvidenceValue value={attempt.failure_evidence} /></section>}
      </Space>,
    }))} />)}
    {job.kind !== 'batch' && ['succeeded','failed'].includes(job.status) && <Form layout="vertical">
      <Form.Item label="重跑原因"><Select aria-label="重跑原因" value={reason} disabled={busy || !canRerun} onChange={setReason} style={{maxWidth:320}} options={[{value:'after_fix',label:'已修复失败原因'},{value:'refresh_result',label:'重新获取该期间最新结果'}]} /></Form.Item>
      <Button aria-label="人工重跑" loading={busy} disabled={!canRerun} onClick={() => void rerun()}>人工重跑</Button>
    </Form>}
    {error && <Alert type="error" showIcon title={error} />}
  </Space>;
}
