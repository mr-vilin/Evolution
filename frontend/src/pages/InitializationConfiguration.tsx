import { Alert, Button, Card, Form, Input, Tag } from 'antd';

export interface InitializationConfiguration {
  storage: { queue_lock_ready: boolean; worker_lease_ready: boolean };
  feishu: {
    app_id_masked: string | null;
    tenant_key_masked: string | null;
    app_secret_configured: boolean;
    redirect_uri_configured: boolean;
    session_secret_configured: boolean;
    binding_matches: boolean;
  };
}

export interface Mappings {
  permission_role?: string;
  store_attribute?: string;
  employee_type_options?: Record<string, string>;
}

interface EmployeeTypeRow { id: string; name: string }
interface MappingFormValues {
  permission_role: string;
  store_attribute: string;
  employee_type_options: EmployeeTypeRow[];
}
interface CheckResult { key: string; status: string; message: string }

function Details({ entries }: { entries: Array<[string, string]> }) {
  return <dl className="initialization-details">
    {entries.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
  </dl>;
}

function CheckTag({ status }: { status?: string }) {
  if (status === 'passed') return <Tag color="success">已通过</Tag>;
  if (status === 'failed') return <Tag color="error">未通过</Tag>;
  return <Tag>待检查</Tag>;
}

const configuredText = (value?: boolean) => value === undefined ? '—' : value ? '已配置' : '未配置';
const existsText = (value?: boolean) => value === undefined ? '—' : value ? '已建立' : '缺失';

function MappingEditor({ settings, disabled, formName, onSave }: {
  settings: Mappings;
  disabled: boolean;
  formName: string;
  onSave: (values: Mappings) => Promise<void>;
}) {
  const options = Object.entries(settings.employee_type_options ?? {}).map(([id, name]) => ({ id, name }));
  return <Form<MappingFormValues>
    id={formName}
    name={formName}
    layout="vertical"
    disabled={disabled}
    initialValues={{ ...settings, employee_type_options: options }}
    onFinish={values => onSave({
      permission_role: values.permission_role.trim(),
      store_attribute: values.store_attribute.trim(),
      employee_type_options: Object.fromEntries(values.employee_type_options.map(row => [row.id.trim(), row.name.trim()])),
    })}
  >
    <div className="initialization-form-grid">
      <Form.Item name="permission_role" label="权限角色字段 ID" rules={[
        { required: true, whitespace: true, message: '请填写权限角色字段 ID' },
        { max: 191, message: '字段 ID 最多 191 字符' },
      ]}><Input maxLength={191} /></Form.Item>
      <Form.Item name="store_attribute" label="门店属性字段 ID" rules={[
        { required: true, whitespace: true, message: '请填写门店属性字段 ID' },
        { max: 191, message: '字段 ID 最多 191 字符' },
      ]}><Input maxLength={191} /></Form.Item>
    </div>
    <section className="initialization-options" aria-labelledby="employee-type-options-title">
      <h3 id="employee-type-options-title">员工类型选项</h3>
      <p className="initialization-muted">每行填写一个飞书选项的 ID 和名称。</p>
      <Form.List name="employee_type_options">
        {(fields, { add, remove }) => <>
          {fields.length === 0 && <p className="initialization-muted">暂未配置员工类型选项</p>}
          {fields.map(field => <div className="initialization-option-row" key={field.key}>
            <Form.Item name={[field.name, 'id']} label="选项 ID" rules={[
              { required: true, whitespace: true, message: '请填写选项 ID' },
              ({ getFieldValue }) => ({ validator: async (_, value?: string) => {
                const rows: EmployeeTypeRow[] = getFieldValue('employee_type_options') ?? [];
                if (value?.trim() && rows.filter(row => row?.id?.trim() === value.trim()).length > 1) {
                  throw new Error('选项 ID 不能重复');
                }
              } }),
            ]}><Input /></Form.Item>
            <Form.Item name={[field.name, 'name']} label="选项名称"
              rules={[{ required: true, whitespace: true, message: '请填写选项名称' }]}><Input /></Form.Item>
            <Button danger className="initialization-option-remove" aria-label={`删除第 ${field.name + 1} 行`}
              onClick={() => remove(field.name)}>删除</Button>
          </div>)}
          <Button type="dashed" onClick={() => add({ id: '', name: '' })}>新增一行</Button>
        </>}
      </Form.List>
    </section>
  </Form>;
}

export function ConfigurationChecks({ configuration, items, settings, editing, mayEdit, disabled, formName, onEdit, onSave }: {
  configuration?: InitializationConfiguration;
  items: CheckResult[];
  settings: Mappings;
  editing: boolean;
  mayEdit: boolean;
  disabled: boolean;
  formName: string;
  onEdit: () => void;
  onSave: (values: Mappings) => Promise<void>;
}) {
  const storage = configuration?.storage;
  const feishu = configuration?.feishu;
  const storageResult = items.find(item => item.key === 'storage');
  const identityResult = items.find(item => item.key === 'identity');
  const mappingResult = items.find(item => item.key === 'mappings');
  const options = Object.entries(settings.employee_type_options ?? {});

  return <>
    {items.filter(item => !['storage', 'identity', 'mappings'].includes(item.key)).map(item =>
      <Alert key={item.key} type="error" showIcon title={item.message || '配置检测失败'} />
    )}
    <Card title="存储与任务单例" extra={<CheckTag status={storageResult?.status} />}>
      <p className="initialization-muted">检查数据库是否建立了任务队列锁和同步 Worker 租约记录。队列锁防止重复创建任务，租约用于协调 Worker 领取和更新任务。</p>
      <Details entries={[
        ['任务队列锁记录', existsText(storage?.queue_lock_ready)],
        ['同步 Worker 租约记录', existsText(storage?.worker_lease_ready)],
      ]} />
      {storageResult?.message && <p className="initialization-check-message">{storageResult.message}</p>}
    </Card>
    <Card title="飞书应用、租户及登录配置" extra={<CheckTag status={identityResult?.status} />}>
      <p className="initialization-muted">检查部署参数是否齐全，以及当前飞书应用和租户是否与数据库绑定一致。</p>
      <Details entries={[
        ['应用 ID（App ID）', feishu?.app_id_masked ?? (feishu ? '未配置' : '—')],
        ['应用密钥（App Secret）', feishu?.app_secret_configured ? '********' : configuredText(feishu?.app_secret_configured)],
        ['企业标识（Tenant Key）', feishu?.tenant_key_masked ?? (feishu ? '未配置' : '—')],
        ['登录回调地址', configuredText(feishu?.redirect_uri_configured)],
        ['会话签名密钥', feishu?.session_secret_configured ? '********' : configuredText(feishu?.session_secret_configured)],
        ['应用及租户绑定', feishu ? (feishu.binding_matches ? '一致' : '缺失或不一致') : '—'],
      ]} />
      {identityResult?.message && <p className="initialization-check-message">{identityResult.message}</p>}
    </Card>
    <Card title="自定义字段与员工类型映射" extra={<div className="initialization-card-actions">
      <CheckTag status={mappingResult?.status} />
      {mayEdit && !editing && <Button autoInsertSpace={false} disabled={disabled} onClick={onEdit}>编辑</Button>}
    </div>}>
      {mappingResult?.message && <p className="initialization-muted">{mappingResult.message}</p>}
      {editing ? <MappingEditor settings={settings} disabled={disabled} formName={formName} onSave={onSave} /> : <>
        <Details entries={[
          ['权限角色字段 ID', settings.permission_role || '未配置'],
          ['门店属性字段 ID', settings.store_attribute || '未配置'],
        ]} />
        <section className="initialization-options" aria-labelledby="employee-type-options-title">
          <h3 id="employee-type-options-title">员工类型选项</h3>
          {options.length > 0 ? <Details entries={options.map(([id, label]) => [`选项 ID ${id}`, label])} />
            : <p className="initialization-muted">暂未配置员工类型选项</p>}
        </section>
      </>}
    </Card>
  </>;
}
