import { useState } from 'react';
import { App, Button, Form, Input, Space, Typography } from 'antd';
import { request } from '../services/http';
import { useResource } from '../services/useResource';
import { ResourceState } from './ResourceState';

interface TypeRow { code: string; name: string }
interface MappingSettings { employee_type_options?: Record<string, string> }

export function EmployeeTypeSettings() {
  const resource = useResource<MappingSettings>('/admin/api/settings/custom-attrs');
  const { message } = App.useApp();
  const [saving, setSaving] = useState(false);

  async function save(values: { rows: TypeRow[] }) {
    setSaving(true);
    try {
      await request('/admin/api/settings/custom-attrs', {
        method: 'PUT',
        body: { employee_type_options: Object.fromEntries(values.rows.map(row => [row.code.trim(), row.name.trim()])) },
      });
      message.success('人员类型已保存，下次同步时更新人员显示名称');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败，请重试');
    } finally {
      setSaving(false);
    }
  }

  return <ResourceState {...resource}>{resource.data && <>
    <Typography.Paragraph type="secondary">沿用已保存的人员类型配置。填写飞书返回的类型代码及对应显示名称，保存后用于后续同步；未配置的代码保留原值并标为待核实。</Typography.Paragraph>
    <Form name="employee-type-settings" layout="vertical" disabled={saving}
      initialValues={{ rows: Object.entries(resource.data.employee_type_options ?? {}).map(([code, name]) => ({ code, name })) }}
      onFinish={save}>
      <Form.List name="rows">
        {(fields, { add, remove }) => <>
          {fields.length === 0 && <Typography.Paragraph type="secondary">暂未配置人员类型，点击“新增一行”开始填写。</Typography.Paragraph>}
          {fields.map(field => <div key={field.key}><Space align="start" wrap>
            <Form.Item name={[field.name, 'code']} label="类型代码（code）" dependencies={['rows']} rules={[
              { required: true, whitespace: true, message: '请填写类型代码' },
              { max: 191, message: '类型代码最多 191 个字符' },
              ({ getFieldValue }) => ({ validator: async (_, value?: string) => {
                const rows: TypeRow[] = getFieldValue('rows') ?? [];
                if (value?.trim() && rows.filter(row => row?.code?.trim() === value.trim()).length > 1) throw new Error('类型代码不能重复');
              } }),
            ]}><Input /></Form.Item>
            <Form.Item name={[field.name, 'name']} label="显示名称" rules={[
              { required: true, whitespace: true, message: '请填写显示名称' },
              { max: 255, message: '显示名称最多 255 个字符' },
            ]}><Input /></Form.Item>
            <Button danger aria-label={`删除第 ${field.name + 1} 行`} onClick={() => remove(field.name)}>删除</Button>
          </Space></div>)}
          <Form.Item><Button type="dashed" onClick={() => add({ code: '', name: '' })}>新增一行</Button></Form.Item>
        </>}
      </Form.List>
      <Button type="primary" htmlType="submit" loading={saving}>保存人员类型</Button>
    </Form>
  </>}</ResourceState>;
}
