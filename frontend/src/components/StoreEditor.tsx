import { useEffect, useMemo, useState } from 'react';
import { Alert, App, Button, Drawer, Form, Input, Modal, Space, Switch, Table, Tag, Typography } from 'antd';
import type { Department, StoreChange } from '../domain';
import { stableFingerprint } from '../domain';
import { ApiError, request } from '../services/http';
import { EmployeeValue } from './EmployeeValue';
import { departmentPath } from './employeePresentation';

interface Preview { changes: StoreChange[]; affectedEmployeeCount: number; version: number; fingerprint: string }
export function StoreEditor({ departments, dataVersion, open, onClose, onConflict, onSaved }: { departments: Department[]; dataVersion?: number; open: boolean; onClose: () => void; onConflict: () => void; onSaved: () => void }) {
  const { message } = App.useApp();
  const [form] = Form.useForm<{ changes: StoreChange[] }>();
  const values = Form.useWatch([], form);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  useEffect(() => { if (open) { form.setFieldsValue({ changes: departments.map(item => ({ department_id: item.id, is_store: item.is_store, store_code: item.store_code, notes: item.notes })) }); setPreview(null); setConflict(false); } }, [form, open]);
  const fingerprint = useMemo(() => stableFingerprint(values?.changes ?? []), [values]);
  const previewValid = Boolean(preview && preview.version === dataVersion && preview.fingerprint === fingerprint);
  async function buildPreview() { if (dataVersion === undefined) return; const { changes } = await form.validateFields(); setBusy(true); setConflict(false); try { const result = await request<{ changes: StoreChange[]; affected_employee_count: number }>('/admin/api/stores/batch/preview', { method: 'POST', body: { data_version: dataVersion, changes } }); form.setFieldsValue({ changes: result.data.changes }); setPreview({ changes: result.data.changes, affectedEmployeeCount: result.data.affected_employee_count, version: dataVersion, fingerprint: stableFingerprint(result.data.changes) }); setPreviewOpen(true); } catch (error) { if (error instanceof ApiError && error.status === 409) { setConflict(true); setPreview(null); onConflict(); } else message.error(error instanceof Error ? error.message : '预览失败'); } finally { setBusy(false); } }
  async function applyPreview() { if (!previewValid || !preview) return; setBusy(true); try { await request('/admin/api/stores/batch/apply', { method: 'POST', body: { data_version: preview.version, changes: preview.changes } }); message.success(`已保存 ${preview.changes.length} 个部门的门店设置`); setPreviewOpen(false); onSaved(); onClose(); } catch (error) { if (error instanceof ApiError && error.status === 409) { setConflict(true); setPreview(null); setPreviewOpen(false); onConflict(); } else message.error(error instanceof Error ? error.message : '保存失败'); } finally { setBusy(false); } }
  return <><Drawer title={`设置门店属性（${departments.length} 个部门）`} open={open} onClose={onClose} destroyOnHidden size={560} footer={<Space><Button onClick={onClose}>取消</Button><Button type="primary" loading={busy} onClick={buildPreview}>预览影响</Button></Space>}>
    {conflict && <Alert type="warning" showIcon title="数据已更新，请重新预览" description="已刷新基准版本，并保留当前表单内容。" />}
    <Form form={form} layout="vertical"><Form.List name="changes">{fields => fields.map((field, index) => { const department = departments[index]; return <section className="store-change" key={field.key}><Typography.Text strong>{department && departmentPath(department)}</Typography.Text><Form.Item name={[field.name, 'department_id']} hidden><Input /></Form.Item><Form.Item name={[field.name, 'is_store']} label="标记为门店" valuePropName="checked"><Switch disabled={department?.is_root} /></Form.Item><Form.Item name={[field.name, 'store_code']} label="门店编码"><Input allowClear /></Form.Item><Form.Item name={[field.name, 'notes']} label="备注"><Input.TextArea allowClear rows={2} /></Form.Item></section>; })}</Form.List></Form>
  </Drawer>
    <Modal centered title="确认门店变更" open={previewOpen} onCancel={() => setPreviewOpen(false)} onOk={applyPreview}
      confirmLoading={busy} okButtonProps={{ disabled: !previewValid }} okText="确认提交" cancelText="返回编辑" width={760}>
      <Alert type="info" showIcon title={`预计影响 ${preview?.affectedEmployeeCount ?? 0} 位员工`} />
      <Table size="small" pagination={false} rowKey="department_id" dataSource={preview?.changes ?? []}
        columns={[
          { key: 'department', title: '部门', dataIndex: 'department_id', render: (id: string) => {
            const department = departments.find(item => item.id === id);
            return <EmployeeValue value={department && departmentPath(department)} />;
          } },
          { title: '门店状态', dataIndex: 'is_store', render: (value: boolean) => <Tag color={value ? 'blue' : 'default'}>{value ? '门店' : '普通部门'}</Tag> },
          { title: '编码', dataIndex: 'store_code', render: value => <EmployeeValue value={value} /> },
          { title: '备注', dataIndex: 'notes', render: value => <EmployeeValue value={value} /> },
        ]} />
    </Modal>
  </>;
}
