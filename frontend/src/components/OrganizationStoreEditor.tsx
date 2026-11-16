import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Drawer, Form, Input, Space, Switch, Typography } from 'antd';
import type { Department, StoreChange } from '../domain';
import { ApiError, type Meta, request } from '../services/http';
import { datasetQuery } from '../services/useOrganization';

interface Baseline { departments: Department[]; meta: Meta }
export function OrganizationStoreEditor({ initial, open, ready, onClose, onConflict, onRecheck, onSaved }: {
  initial: Baseline | null; open: boolean; ready: boolean; onClose: () => void;
  onConflict: () => void; onRecheck: (ids: string[]) => Promise<Baseline>; onSaved: () => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<{ changes: StoreChange[] }>();
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    if (open && initial) {
      setBaseline(initial); setConflict(false); setError(''); setNotice('');
      form.setFieldsValue({ changes: initial.departments.map(row => ({ department_id: row.id, is_store: row.is_store, store_code: row.store_code, notes: row.notes })) });
    }
  }, [open, initial, form]);
  async function save() {
    if (pending.current || conflict || !baseline?.departments.length) return;
    pending.current = true;
    let changes: StoreChange[];
    try { changes = (await form.validateFields()).changes; } catch { pending.current = false; return; }
    setBusy(true); setError('');
    try {
      const result = await request<{ saved_count: number }>('/admin/api/organization/stores', {
        method: 'POST', body: { ...datasetQuery(baseline.meta), changes },
      });
      message.success(`已保存 ${result.data.saved_count} 个部门的门店设置`);
      onSaved(); onClose();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) { setConflict(true); onConflict(); }
      else {
        setError(reason instanceof Error ? reason.message : '保存失败，请重试');
        if (reason instanceof ApiError) {
          const fields = reason.fields.flatMap(item => {
            const index = baseline.departments.findIndex(row => row.id === item.department_id);
            const name: ['changes', number, 'store_code' | 'is_store'] = ['changes', index, item.code?.includes('STORE_CODE') ? 'store_code' : 'is_store'];
            return index < 0 ? [] : [{ name, errors: [item.message ?? '此部门设置无效'] }];
          });
          form.setFields(fields);
        }
      }
    } finally { pending.current = false; setBusy(false); }
  }
  async function recheck() {
    if (pending.current || !baseline || !ready) return;
    pending.current = true; setBusy(true); setError('');
    try {
      const drafts = new Map((form.getFieldValue('changes') as StoreChange[]).map(row => [row.department_id, row]));
      const next = await onRecheck(baseline.departments.map(row => row.id));
      form.setFieldsValue({ changes: next.departments.map(row => drafts.get(row.id)!) });
      setNotice(`已重新核对：${next.departments.length} 个有效部门（原 ${baseline.departments.length} 个）。请核对后再次保存。`);
      setBaseline(next); setConflict(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '核对失败，请重试'); }
    finally { pending.current = false; setBusy(false); }
  }
  return <Drawer title={`设置门店属性（${baseline?.departments.length ?? 0} 个部门）`} open={open}
    onClose={() => { if (!busy) onClose(); }} destroyOnHidden size={560}
    footer={<Space><Button disabled={busy} onClick={onClose}>取消</Button><Button type="primary" aria-label="保存" loading={busy}
      disabled={conflict || !baseline?.departments.length} onClick={() => void save()}>保存</Button></Space>}>
    {conflict && <Alert type="warning" showIcon title="数据已变化，请重新核对目标与数量"
      description="草稿已保留。新部门不会自动加入，核对后须再次保存。"
      action={<Button disabled={!ready || busy} onClick={() => void recheck()}>重新核对目标</Button>} />}
    {notice && <Alert type="info" showIcon title={notice} />}
    {error && <Alert type="error" showIcon title={error} />}
    <Typography.Paragraph type="secondary">已选 {baseline?.departments.length ?? 0} 个部门。仅修改本次目标，不自动继承给下级。</Typography.Paragraph>
    <Form form={form} layout="vertical" disabled={busy}>
      <Form.List name="changes">{fields => fields.map((field, index) => <section className="store-change" key={field.key}>
        <strong>{baseline?.departments[index]?.path.join(' / ') || baseline?.departments[index]?.name}</strong>
        <Form.Item name={[field.name, 'department_id']} hidden><Input /></Form.Item>
        <Form.Item name={[field.name, 'is_store']} label="标记为门店" valuePropName="checked"><Switch /></Form.Item>
        <Form.Item name={[field.name, 'store_code']} label="门店编码" rules={[{ max: 128, message: '门店编码最多 128 字符' }]}><Input allowClear maxLength={128} /></Form.Item>
        <Form.Item name={[field.name, 'notes']} label="备注"><Input.TextArea allowClear rows={2} /></Form.Item>
      </section>)}</Form.List>
    </Form>
  </Drawer>;
}
