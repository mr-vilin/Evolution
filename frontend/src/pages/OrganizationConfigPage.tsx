import { useEffect, useState } from 'react';
import { useSearchParams } from '@umijs/max';
import { App, Button, Card, Descriptions, Form, InputNumber, Space, Switch, Tabs, TimePicker } from 'antd';
import dayjs from 'dayjs';
import { EmployeeTypeSettings } from '../components/EmployeeTypeSettings';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { EventConnectionStatus, formatTableTime } from '../components/SyncPresentation';
import { request } from '../services/http';
import { useResource } from '../services/useResource';

interface Schedule { enabled: boolean; local_time: string; timezone: string; updated_at: string | null }
interface MonitorConfig { normal_minutes: number; disconnect_minutes: number }

function ReconcileSettings() {
  const { message } = App.useApp();
  const schedule = useResource<Schedule>('/admin/api/settings/reconcile-schedule');
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (schedule.data) form.setFieldsValue({ enabled: schedule.data.enabled, local_time: dayjs(schedule.data.local_time, 'HH:mm') });
  }, [schedule.data, form]);
  async function save(values: { enabled: boolean; local_time: dayjs.Dayjs }) {
    setSaving(true);
    try {
      await request('/admin/api/settings/reconcile-schedule', { method: 'PUT', body: { enabled: values.enabled, local_time: values.local_time.format('HH:mm'), timezone: 'Asia/Shanghai' } });
      message.success('计划已保存'); schedule.reload();
    } catch (error) { message.error(error instanceof Error ? error.message : '保存失败'); }
    finally { setSaving(false); }
  }
  return <ResourceState {...schedule}>{schedule.data && <Form form={form} layout="vertical" onFinish={save} style={{ maxWidth: 420 }}>
    <Form.Item name="enabled" label="启用每日核对" valuePropName="checked"><Switch /></Form.Item>
    <Form.Item name="local_time" label="执行时间（北京时间）" rules={[{ required: true }]}><TimePicker format="HH:mm" minuteStep={5} /></Form.Item>
    <Descriptions column={1} items={[{ key: 'zone', label: '时区', children: schedule.data.timezone }, { key: 'updated', label: '更新时间', children: formatTableTime(schedule.data.updated_at) }]} />
    <Button type="primary" htmlType="submit" loading={saving}>保存计划</Button>
  </Form>}</ResourceState>;
}

function EventMonitorSettings() {
  const { message } = App.useApp();
  const config = useResource<MonitorConfig>('/admin/api/settings/event-monitor');
  const status = useResource<{ connection: { status: string; last_event_received_at?: string | null; elapsed_minutes?: number | null } }>('/admin/api/status', true);
  const [form] = Form.useForm<MonitorConfig>();
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (config.data) form.setFieldsValue(config.data); }, [config.data, form]);
  useEffect(() => { const timer = window.setInterval(status.reload, 30000); return () => clearInterval(timer); }, [status.reload]);
  async function save(values: MonitorConfig) {
    setSaving(true);
    try {
      await request('/admin/api/settings/event-monitor', { method: 'PUT', body: values });
      message.success('连接时限已保存'); config.reload(); status.reload();
    } catch (error) { message.error(error instanceof Error ? error.message : '保存失败'); }
    finally { setSaving(false); }
  }
  return <Space orientation="vertical" size={24} style={{ width: '100%' }}>
    <ResourceState {...status} loading={status.loading && !status.data}>{status.data && <Descriptions column={1} items={[
      { key: 'status', label: '当前状态', children: <EventConnectionStatus status={status.data.connection.status} /> },
      { key: 'last', label: '最近事件接收时间', children: formatTableTime(status.data.connection.last_event_received_at) },
      { key: 'elapsed', label: '距今时长', children: status.data.connection.elapsed_minutes == null ? '-' : status.data.connection.elapsed_minutes + ' 分钟' },
    ]} />}</ResourceState>
    <ResourceState {...config}>{config.data && <Form form={form} layout="vertical" onFinish={save} style={{ maxWidth: 420 }}>
      <Form.Item name="normal_minutes" label="正常时限（分钟）" rules={[{ required: true, type: 'integer', min: 1 }]}><InputNumber min={1} precision={0} style={{ width: '100%' }} /></Form.Item>
      <Form.Item name="disconnect_minutes" label="断开时限（分钟）" dependencies={['normal_minutes']} rules={[
        { required: true, type: 'integer', min: 1 },
        ({ getFieldValue }) => ({ validator: (_, value) => value > getFieldValue('normal_minutes') ? Promise.resolve() : Promise.reject(new Error('断开时限必须大于正常时限')) }),
      ]}><InputNumber min={1} precision={0} style={{ width: '100%' }} /></Form.Item>
      <Button type="primary" htmlType="submit" loading={saving}>保存配置</Button>
    </Form>}</ResourceState>
  </Space>;
}

export default function OrganizationConfigPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') || 'employee-types';
  return <PageHeader area="组织管理" title="配置中心" description="管理组织人员类型、每日核对和飞书事件连接。"><Card><Tabs activeKey={tab} onChange={value => setParams({ tab: value })} items={[
    { key: 'employee-types', label: '人员类型', children: <EmployeeTypeSettings /> },
    { key: 'schedule', label: '每日核对', children: <ReconcileSettings /> },
    { key: 'event-monitor', label: '飞书事件连接', children: <EventMonitorSettings /> },
  ]} /></Card></PageHeader>;
}
