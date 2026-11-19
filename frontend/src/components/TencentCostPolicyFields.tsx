import { Collapse, Form, InputNumber } from 'antd';

export const defaultCostPolicy = {
  max_attempts:3,deadline_seconds:90,run_deadline_seconds:900,retry_base_seconds:30,retry_max_seconds:300,retry_jitter_seconds:5,
  lease_seconds:120,heartbeat_seconds:20,queue_limit:200,queue_deadline_seconds:86400,max_rows:10000,
};
export type CostPolicy = typeof defaultCostPolicy;
const fields: Array<{name:keyof CostPolicy;label:string;min:number;max:number}> = [
  {name:'max_attempts',label:'最大总尝试次数',min:1,max:5},
  {name:'deadline_seconds',label:'单次执行预算（秒）',min:30,max:300},
  {name:'run_deadline_seconds',label:'执行轮次预算（秒）',min:60,max:86400},
  {name:'retry_base_seconds',label:'退避基数（秒）',min:5,max:300},
  {name:'retry_max_seconds',label:'最大退避（秒）',min:5,max:900},
  {name:'retry_jitter_seconds',label:'随机抖动上限（秒）',min:0,max:30},
  {name:'lease_seconds',label:'执行租约（秒）',min:30,max:600},
  {name:'heartbeat_seconds',label:'心跳间隔（秒）',min:5,max:60},
  {name:'queue_limit',label:'配置待处理任务上限',min:1,max:500},
  {name:'queue_deadline_seconds',label:'首次领取等待预算（秒）',min:60,max:604800},
  {name:'max_rows',label:'单次产品行数上限',min:1,max:10000},
];
export function costPolicyErrors(policy: CostPolicy) {
  const errors: Partial<Record<keyof CostPolicy,string>> = {};
  fields.forEach(field => {
    const value=policy[field.name];
    if (!Number.isInteger(value) || value<field.min || value>field.max) errors[field.name]=`请输入 ${field.min} 至 ${field.max} 的整数`;
  });
  if (policy.heartbeat_seconds*3>policy.lease_seconds) errors.heartbeat_seconds='心跳间隔不能超过租约的三分之一';
  if (policy.run_deadline_seconds<policy.deadline_seconds) errors.run_deadline_seconds='轮次预算不得小于单次执行预算';
  if (policy.retry_max_seconds<policy.retry_base_seconds) errors.retry_max_seconds='最大退避不得小于退避基数';
  return errors;
}
export function TencentCostPolicyFields({policy,onChange,disabled}:{policy:CostPolicy;onChange:(value:CostPolicy)=>void;disabled:boolean}) {
  const errors=costPolicyErrors(policy);
  return <Collapse style={{marginBottom:16}} items={[{key:'policy',label:'重试与执行限制',children:<>
    <p>最大总尝试次数包含首次执行。策略编辑用于新任务；已有任务继续使用冻结策略，启停操作即时复核。</p>
    <p>首次领取前使用等待预算；领取后的执行、退避和重试共同消耗执行轮次预算。</p>
    <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(min(100%,240px),1fr))',gap:16}}>
      {fields.map(field => <Form.Item key={field.name} label={field.label} validateStatus={errors[field.name] ? 'error' : undefined} help={errors[field.name]}>
        <InputNumber aria-label={field.label} min={field.min} max={field.max} precision={0} value={Number.isNaN(policy[field.name]) ? null : policy[field.name]}
          disabled={disabled} onChange={value => onChange({...policy,[field.name]:value ?? Number.NaN})} style={{width:'100%'}} />
      </Form.Item>)}
    </div>
  </>}]} />;
}
