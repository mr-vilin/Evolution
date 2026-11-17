import { useState } from 'react';
import { Alert, App, Button, Form, Input, Modal, Select, Switch } from 'antd';
import { ApiError, request } from '../services/http';
import type { TencentAccount } from './TencentAccountsPage';

interface MaintenanceForm { alias: string; is_enabled: boolean; credential_ref?: string }

export function TencentAccountMaintenance({ account, credentialOptions = [], onCancel, onSaved, onReload }: {
  account: TencentAccount; credentialOptions?: Array<{value:string;label:string}>; onCancel: () => void; onSaved: (warning?:string) => void; onReload?: () => void;
}) {
  const [form] = Form.useForm<MaintenanceForm>();
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [stale, setStale] = useState(false);
  async function save() {
    if (busy || stale) return;
    let values: MaintenanceForm;
    try { values = await form.validateFields(); } catch { return; }
    const body: { revision: number; alias?: string; is_enabled?: boolean; credential_ref?:string } = {revision:account.revision};
    if (values.alias.trim() !== account.alias) body.alias = values.alias.trim();
    if (values.is_enabled !== account.is_enabled) body.is_enabled = values.is_enabled;
    if (values.credential_ref) body.credential_ref = values.credential_ref;
    if (Object.keys(body).length === 1) {setError('请先修改需要维护的内容'); return;}
    setBusy(true); setError('');
    try {
      const result = await request<TencentAccount>(`/admin/api/tencent/accounts/${encodeURIComponent(account.id)}`, {
        method: 'PATCH', body,
      });
      const verification = result.meta.verification as {auxiliary_readiness?:string} | undefined;
      if (verification?.auxiliary_readiness === 'not_ready') {
        onSaved('凭据轮换成功；辅助账单仍在准备中，后续成本采集会单独核验就绪状态。');
      } else {message.success('账号维护已保存'); onSaved();}
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '维护失败，请重试');
      if (reason instanceof ApiError) {
        if (['TENCENT_ACCOUNT_CONFLICT','TENCENT_CAPABILITY_CHANGED','NETWORK_ERROR','INVALID_RESPONSE'].includes(reason.code)) setStale(true);
        if (reason.code === 'TENCENT_CREDENTIAL_REF_INVALID' || reason.code === 'TENCENT_ACCOUNT_MISMATCH' || reason.code === 'TENCENT_PERMISSION_DENIED') {
          form.setFields([{name:'credential_ref',errors:[reason.message]}]);
        }
      }
    } finally { setBusy(false); }
  }
  return <Modal title="维护腾讯云账号" centered open onCancel={() => {if (!busy) onCancel();}} onOk={() => void save()}
    okText="保存维护" cancelText="取消" confirmLoading={busy} okButtonProps={{disabled:stale}} cancelButtonProps={{disabled:busy}} mask={{closable:!busy}} closable={!busy}>
    <Alert type="info" showIcon title="停用将阻止新的余额查询和成本执行" description="停用前的在途结果将被隔离，重新启用也不会恢复旧执行资格。已保存的费用和尝试历史保留。" style={{marginBottom:16}} />
    <Form form={form} name="tencent-maintenance" layout="vertical" initialValues={{alias:account.alias,is_enabled:account.is_enabled}} disabled={busy}>
      <Form.Item label="账号 UIN"><Input aria-label="账号 UIN" value={account.uin} readOnly /></Form.Item>
      <Form.Item name="alias" label="中文别名" rules={[{required:true,whitespace:true,message:'请输入中文别名'},{max:128,message:'中文别名不能超过128字'}]}><Input maxLength={128} /></Form.Item>
      <Form.Item name="credential_ref" label="轮换只读凭据" extra="留空保留当前凭据；选择后核验同一 UIN 及已启用成本所需权限。">
        <Select allowClear options={credentialOptions} placeholder="保留当前凭据" disabled={busy || !credentialOptions.length} />
      </Form.Item>
      <Form.Item name="is_enabled" label="账号总开关" valuePropName="checked"><Switch checkedChildren="启用" unCheckedChildren="停用" /></Form.Item>
    </Form>
    {error && <Alert type="error" showIcon title={error} action={stale ? <Button onClick={onReload ?? onCancel}>刷新账号后重新维护</Button> : undefined} />}
  </Modal>;
}
