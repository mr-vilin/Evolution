import { useMemo, useState } from 'react';
import { Alert, App, Button, Form, Input, Modal, Select, Space, Tag, Tooltip } from 'antd';
import type { TableColumnsType } from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined, WalletOutlined } from '@ant-design/icons';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { TencentCostTableCard } from '../components/TencentCostTableCard';
import { useTencentSort, timeValue, TencentTime } from '../components/tencentPresentation';
import { ApiError, request } from '../services/http';
import { useResource } from '../services/useResource';
import { TencentAccountMaintenance } from './TencentAccountMaintenance';

export interface TencentAccount {
  id: string; uin: string; alias: string; credential_ref: string; revision: number; credential_revision: number;
  is_enabled: boolean; verification_status: string; verified_at: string; create_time: string; update_time: string;
}
interface CredentialOption { value: string; label: string }
interface AccountForm { uin: string; alias: string; credential_ref: string }

export function TencentAccountsPage() {
  const accounts = useResource<TencentAccount[]>('/admin/api/tencent/accounts');
  const credentials = useResource<CredentialOption[]>('/admin/api/tencent/credential-options');
  const { message } = App.useApp();
  const [form] = Form.useForm<AccountForm>();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<TencentAccount | null>(null);
  const [maintenanceNotice, setMaintenanceNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const labels = useMemo(() => new Map(credentials.data?.map(item => [item.value,item.label])), [credentials.data]);
  const sorting=useTencentSort<TencentAccount>({verified:row=>timeValue(row.verified_at),created:row=>timeValue(row.create_time)},()=>setPage(1));
  const filtered = useMemo(() => (accounts.data ?? []).filter(row => !search || `${row.alias} ${row.uin}`.includes(search)), [accounts.data,search]);
  const rows=sorting.rows(filtered);
  async function submit(register: boolean) {
    let values: AccountForm;
    try { values = await form.validateFields(register ? undefined : ['uin', 'credential_ref']); } catch { return; }
    setBusy(true); setFeedback(null);
    try {
      const body = register ? values : { uin: values.uin, credential_ref: values.credential_ref };
      await request(register ? '/admin/api/tencent/accounts' : '/admin/api/tencent/accounts/validate', { method:'POST', body });
      if (register) {
        message.success('账号已验证并登记'); setOpen(false); form.resetFields(); accounts.reload(); setPage(1);
      } else setFeedback({type:'success',text:'凭据归属验证通过，可登记账号'});
    } catch (error) {
      const text = error instanceof Error ? error.message : '操作失败，请重试';
      setFeedback({type:'error',text});
      if (error instanceof ApiError && error.code === 'TENCENT_ACCOUNT_MISMATCH') form.setFields([{name:'uin',errors:[text]}]);
      if (error instanceof ApiError && error.code === 'TENCENT_CREDENTIAL_REF_INVALID') form.setFields([{name:'credential_ref',errors:[text]}]);
    } finally { setBusy(false); }
  }
  const columns: TableColumnsType<TencentAccount> = [
    { key:'alias',title:'账号名称',dataIndex:'alias',fixed:'left',width:160,ellipsis:true },
    { key:'uin',title:'账号 UIN',dataIndex:'uin',width:160 },
    { key:'credential',title:'只读凭据',render:(_,row) => labels.get(row.credential_ref) ?? '凭据待维护',width:200,ellipsis:true },
    { key:'status',title:'状态',render:(_,row) => <Tag color={row.is_enabled && row.verification_status === 'verified' ? 'success' : 'default'}>{row.is_enabled ? row.verification_status === 'verified' ? '已验证 / 启用' : '待验证' : '已停用'}</Tag>,width:150 },
    { key:'verified',...sorting.column('verified'),title:'验证时间（北京时间）',dataIndex:'verified_at',render:value => <TencentTime value={value} />,width:190 },
    { key:'created',...sorting.column('created'),title:'登记时间（北京时间）',dataIndex:'create_time',render:value => <TencentTime value={value} />,width:190 },
    { key:'actions',title:'操作',fixed:'right',width:96,render:(_,row) => <Space size={8}><Tooltip title="实时余额"><Button type="text" aria-label="实时余额" icon={<WalletOutlined />} href={`/tencent/accounts/${encodeURIComponent(row.id)}/balance`} disabled={!row.is_enabled || row.verification_status !== 'verified'} /></Tooltip><Tooltip title="维护账号"><Button type="text" aria-label="维护账号" icon={<EditOutlined />} onClick={() => setEditing(row)} /></Tooltip></Space> },
  ];
  return <PageHeader area="业务管理" title="腾讯云账号" description="登记各自独立的腾讯云账号，分别查看费用和实时余额。">
    {maintenanceNotice && <Alert type="warning" showIcon title={maintenanceNotice} style={{marginBottom:16}} />}
    <TencentCostTableCard<TencentAccount> title="腾讯云账号列表" showTable={!accounts.loading && !accounts.error && !!accounts.data?.length} rowKey="id" columns={columns} dataSource={rows} onChange={sorting.onChange} scroll={{x:1186}} pagination={{current:Math.min(page,Math.max(1,Math.ceil(rows.length/20))),pageSize:20,onChange:setPage,showSizeChanger:false}}>
      <div style={{display:'flex',justifyContent:'space-between',gap:8,flexWrap:'wrap',marginBottom:16,minWidth:0}}>
        <Space><Button type="primary" aria-label="登记账号" icon={<PlusOutlined />} onClick={() => {setFeedback(null);setOpen(true);}}>登记账号</Button><Button aria-label="刷新" icon={<ReloadOutlined />} onClick={() => {accounts.reload();credentials.reload();}}>刷新</Button></Space>
        <Input.Search aria-label="搜索账号" placeholder="搜索账号名称或 UIN" allowClear value={search} onChange={event => {setSearch(event.target.value);setPage(1);}} style={{width:260,maxWidth:'100%',minWidth:0,flex:'0 1 260px'}} />
      </div>
      <ResourceState {...accounts} empty={!accounts.data?.length}>
        <span />
      </ResourceState>
    </TencentCostTableCard>
    <Modal title="登记腾讯云账号" centered open={open} onCancel={() => {if(!busy) setOpen(false);}} mask={{closable:!busy}} closable={!busy} footer={<Space><Button disabled={busy} onClick={() => setOpen(false)}>取消</Button><Button loading={busy} disabled={!credentials.data?.length} onClick={() => void submit(false)}>验证归属</Button><Button type="primary" loading={busy} disabled={!credentials.data?.length} onClick={() => void submit(true)}>验证并登记</Button></Space>}>
      <Alert type="info" showIcon title="每个独立账号使用自身只读凭据" description="请从已登记的凭据中选择。登记时将核验实际账号归属。" style={{marginBottom:16}} />
      <ResourceState {...credentials}>
        {credentials.data?.length === 0 && <Alert type="warning" showIcon title="暂无可用只读凭据" description="请联系部署维护人员登记只读凭据后刷新。" />}
        <Form form={form} layout="vertical" onValuesChange={() => setFeedback(null)}>
          <Form.Item name="uin" label="账号 UIN" rules={[{required:true,message:'请输入账号 UIN'},{pattern:/^[1-9][0-9]{0,31}$/,message:'请输入腾讯云主账号的数字 UIN'}]}><Input maxLength={32} placeholder="腾讯云主账号 UIN" autoComplete="off" /></Form.Item>
          <Form.Item name="alias" label="中文别名" rules={[{required:true,whitespace:true,message:'请输入中文别名'},{max:128,message:'中文别名不能超过128字'}]}><Input maxLength={128} placeholder="例如：生产业务账号" /></Form.Item>
          <Form.Item name="credential_ref" label="只读凭据" rules={[{required:true,message:'请选择受控只读凭据'}]}><Select options={credentials.data ?? []} placeholder="请选择只读凭据" /></Form.Item>
        </Form>
      </ResourceState>
      {feedback && <Alert showIcon type={feedback.type} title={feedback.text} />}
    </Modal>
    {editing && <TencentAccountMaintenance account={editing} onReload={() => {setEditing(null);accounts.reload();credentials.reload();}} credentialOptions={credentials.data ?? []} onCancel={() => setEditing(null)} onSaved={warning => {setMaintenanceNotice(warning ?? '');setEditing(null);accounts.reload();}} />}
  </PageHeader>;
}

export default TencentAccountsPage;
