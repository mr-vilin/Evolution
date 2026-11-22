import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Dropdown, Form, Input, Progress, Result, Space, Spin, Steps, Table, Tag } from 'antd';
import { CheckOutlined, LogoutOutlined } from '@ant-design/icons';
import { themeLogoUrl } from '../branding/logo';
import { buildInfo } from '../buildInfo';
import { useAdminSession } from '../components/AdminSessionContext';
import { EmployeeIdentity } from '../components/EmployeeIdentity';
import { request } from '../services/http';
import { useThemeColors } from '../theme/ThemeProvider';
import { ConfigurationChecks, type InitializationConfiguration, type Mappings } from './InitializationConfiguration';
import './InitializationPage.css';

interface CheckItem { key: string; title: string; status: string; message: string; field?: string; object_id?: string; object_type?: string; readability?: string }
interface FieldRequirement { key: string; object_type: string; field: string; title: string; requirement: string; rule: string }
interface Check { step: number; title: string; status: string; items: CheckItem[] }
interface ProgressData { departments_processed?: number; employees_processed?: number; departments_total?: number | null; employees_total?: number | null }
export interface InitializationStatus {
  flow_id: string | null; phase: string; complete: boolean; checks: Check[]; checking_step?: number;
  configuration?: InitializationConfiguration;
  settings: Mappings; counts?: { departments: number; employees: number };
  field_sample?: { mode: 'manual' | 'automatic'; user_ids: string[] };
  required_fields?: FieldRequirement[];
  last_error?: { code: string; message: string; issues?: { object_id: string; field?: string; message: string }[] };
  job?: { job_id: string; status: string; phase: string; started_at?: string; updated_at?: string; finished_at?: string; progress: ProgressData } | null;
}
const titles = ['检查配置', '测试飞书连接', '试读部门与人员', '核验所需字段', '执行全量同步'];
const phases: Record<string, string> = { queued: '等待后台任务', scopes: '确认企业范围', departments: '采集部门', employees: '采集人员', collected: '完成采集', validating: '校验全量数据', publishing: '提交初始化数据', published: '初始化完成', collection_failed: '初始化失败', interrupted: '后台任务中断' };

function FieldCheckResults({ items, requirements }: { items: CheckItem[]; requirements: FieldRequirement[] }) {
  const rules = new Map(requirements.map(rule => [rule.key, rule]));
  const groups = new Map<string, { key: string; title: string; field?: string; requirement?: string; rule?: string; items: CheckItem[] }>();
  if (items.length === 0) {
    for (const rule of requirements) groups.set(rule.key, { ...rule, title: `${rule.object_type === 'department' ? '部门 · ' : rule.object_type === 'user' ? '人员 · ' : ''}${rule.title}`, items: [] });
  }
  for (const item of items) {
    const key = item.object_id ? `${item.object_type ?? 'user'}:${item.field ?? item.key}` : item.key;
    const rule = rules.get(item.object_id ? `${item.object_type ?? 'user'}:${item.field}` : item.key);
    const group = groups.get(key) ?? { requirement: rule?.requirement, rule: rule?.rule, key, title: `${item.object_type === 'department' ? '部门 · ' : item.object_id ? '人员 · ' : ''}${item.title}`, field: item.field, items: [] };
    group.items.push(item);
    groups.set(key, group);
  }
  const rows = [...groups.values()];
  return <Table rowKey="key" size="small" pagination={false} dataSource={rows} scroll={{ x: 900 }} columns={[
    { title: '所需字段', key: 'field', width: 200, render: (_, row) => <><strong>{row.title}</strong>{row.field && <div className="initialization-muted">{row.field}</div>}</> },
    { title: '填写要求', key: 'requirement', width: 220, render: (_, row) => <><strong>{row.requirement ?? '-'}</strong>{row.rule && <div className="initialization-muted">{row.rule}</div>}</> },
    { title: '校验结果', key: 'status', width: 164, render: (_, row) => {
      const passed = row.items.filter(item => item.status === 'passed').length;
      const failed = row.items.some(item => item.status === 'failed');
      if (row.items.some(item => item.readability && item.readability !== 'readable')) return <Tag variant="filled" color="warning">含未知信息（可缺省）</Tag>;
      if (row.items.length === 0) return <Tag variant="filled">待校验</Tag>;
      const allPassed = passed === row.items.length;
      return <>
        <Tag variant="filled" color={failed ? 'error' : allPassed ? 'success' : undefined}>
          {failed ? '未通过' : allPassed ? '已通过' : '未校验'}
        </Tag>
        {row.items.length > 1 && <div className="initialization-muted">通过 {passed} / {row.items.length}</div>}
      </>;
    } },
    { title: '样本与原因', key: 'details', render: (_, row) => row.items.length === 0 ? '-' : <ul className="initialization-field-details">{row.items.map(item => <li key={item.key}>{item.object_id && <strong>{item.object_id}：</strong>}{item.readability ? item.message : item.status === 'passed' ? '校验通过' : item.message}</li>)}</ul> },
  ]} />;
}


const mappingForm = 'initialization-settings';
const sampleForm = 'initialization-sample';

const checkDescriptions: Record<string, string> = {
  connection: '请求飞书通讯录接口，读取应用的授权范围。',
  whole_enterprise: '请求根部门的人员列表，验证应用可以从根部门开始读取。',
  departments: '从根部门最多抽取 3 个子部门，读取部门详情。',
  employees: '从授权范围及根部门、抽样部门中最多选取 3 位人员，读取人员详情。',
};
const checklists: Record<number, { key: string; title: string }[]> = {
  2: [
    { key: 'connection', title: '应用凭据与通讯录连通性' },
    { key: 'whole_enterprise', title: '根部门人员列表读取权限' },
  ],
  3: [
    { key: 'departments', title: '部门结构试读' },
    { key: 'employees', title: '人员详情试读' },
  ],
};

function availableStep(data: InitializationStatus | null) {
  if (!data || data.phase === 'cleanup_required') return 1;
  if (data.complete || ['ready', 'running', 'failed'].includes(data.phase)) return 5;
  return [1, 2, 3, 4].find(step => !data.checks.some(check => check.step === step && check.status === 'passed')) ?? 5;
}

function checkStatus(status?: string) {
  if (status === 'passed') return { text: '已通过', color: 'success' };
  if (status === 'failed') return { text: '未通过', color: 'error' };
  return { text: '待检查' };
}

function CheckList({ step, items }: { step: number; items: CheckItem[] }) {
  const definitions = checklists[step];
  return <>
    <ul className="initialization-check-items">
      {definitions.map(({ key, title }) => {
        const item = items.find(result => result.key === key);
        const status = checkStatus(item?.status);
        return <li key={key}>
          <div className="initialization-check-label"><strong>{title}</strong><Tag color={status.color}>{status.text}</Tag></div>
          <p className="initialization-muted">{checkDescriptions[key]}</p>
          {item?.message && <p>{item.message}</p>}
        </li>;
      })}
    </ul>
    {items.filter(item => !definitions.some(definition => definition.key === item.key)).map(item =>
      <Alert key={item.key} type="error" showIcon title={item.message || item.title} />
    )}
  </>;
}

function SyncDetails({ data }: { data: InitializationStatus }) {
  if (data.complete) return <Card><Result status="success" title="初始化完成"
    subTitle={`已同步 ${data.counts?.departments ?? 0} 个部门、${data.counts?.employees ?? 0} 位人员，全部校验通过。`} /></Card>;

  const job = data.job;
  const progress = job?.progress ?? {};
  const { departments_total, employees_total } = progress;
  const processed = (progress.departments_processed ?? 0) + (progress.employees_processed ?? 0);
  const total = typeof departments_total === 'number' && typeof employees_total === 'number' ? departments_total + employees_total : 0;
  const elapsed = job?.started_at
    ? Math.max(0, Math.floor(((job.finished_at ? Date.parse(job.finished_at) : Date.now()) - Date.parse(job.started_at)) / 1000))
    : 0;

  return <>
    {data.phase === 'failed' && <RestartNotice data={data} />}
    {data.last_error?.issues?.length ? <Card title="需要修正的数据">
      <ul className="initialization-issues">{data.last_error.issues.map((issue, index) =>
        <li key={index}><strong>{issue.object_id}</strong> {issue.field}：{issue.message}</li>)}</ul>
    </Card> : null}
    {data.phase === 'ready' && <Card title="所有前置检查已通过">
      <p>开始后将读取全企业数据，逐条核验并提交。后台任务中断后需要重新开始。</p>
    </Card>}
    {job && <Card title={phases[job.phase] ?? '初始化同步进度'}>
      <Space wrap size={16}>
        <span>已采集部门：{progress.departments_processed ?? 0}{typeof departments_total === 'number' ? ` / ${departments_total}` : ''}</span>
        <span>已采集人员：{progress.employees_processed ?? 0}{typeof employees_total === 'number' ? ` / ${employees_total}` : ''}</span>
        <span>耗时 {elapsed} 秒</span>
      </Space>
      {total > 0 ? <div className="initialization-progress">
        <p>采集进度</p>
        <Progress percent={Math.round(processed / total * 100)} status={data.phase === 'failed' ? 'exception' : 'active'} />
      </div> : data.phase === 'running' && <div className="initialization-progress"><Space><Spin size="small" />正在发现和读取数据</Space></div>}
      {job.updated_at && <p className="initialization-muted initialization-progress">最近更新：{new Date(job.updated_at).toLocaleString()}</p>}
    </Card>}
  </>;
}

function RestartNotice({ data }: { data: InitializationStatus }) {
  const failed = data.phase === 'failed';
  return <Alert type={failed ? 'error' : 'warning'} showIcon
    title={failed ? '本轮初始化未成功' : '需要按新流程重新初始化'}
    description={<>
      <p>{data.last_error?.message ?? '现有实例需要重新完成初始化。'}</p>
      <p>重新开始会清除部门、人员、关系、门店资料（含编码、备注）及临时采集结果，保留飞书配置、管理员资格、登录能力和失败审计。</p>
    </>} />;
}

export default function InitializationPage({ onComplete }: { onComplete?: () => void }) {
  const { message } = App.useApp();
  const { colors } = useThemeColors();
  const session = useAdminSession();
  const [selectedStep, setSelectedStep] = useState<number | null>(null);
  const [data, setData] = useState<InitializationStatus | null>(null);
  const [networkError, setNetworkError] = useState('');
  const [working, setWorking] = useState(false);
  const [localCheck, setLocalCheck] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const busy = useRef(false);
  const alive = useRef(true);
  const sequence = useRef(0);
  const panel = useRef<HTMLElement>(null);

  const load = useCallback(async () => {
    const current = ++sequence.current;
    try {
      const result = await request<InitializationStatus>('/admin/api/initialization');
      if (alive.current && current === sequence.current) {
        setData(result.data);
        setNetworkError('');
      }
    } catch (error) {
      if (alive.current && current === sequence.current) {
        setNetworkError(error instanceof Error ? error.message : '连接暂时中断');
      }
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void load();
    const timer = window.setInterval(() => { if (!busy.current) void load(); }, 2000);
    return () => { alive.current = false; window.clearInterval(timer); };
  }, [load]);

  const max = availableStep(data);
  const step = Math.min(selectedStep ?? max, max);
  const check = data?.checks.find(item => item.step === step);
  const checking = data?.phase === 'checking';
  const running = data?.phase === 'running';
  const cleanupRequired = data?.phase === 'cleanup_required';
  const mayEdit = !!data && !data.complete && !cleanupRequired && data.phase !== 'failed' && !running;
  const disabled = working || checking || Boolean(networkError);
  const locked = disabled || editing;
  const name = session?.profile?.name || '当前管理员';
  const enter = onComplete ?? (() => window.location.assign('/organization'));

  useEffect(() => { if (panel.current) panel.current.scrollTop = 0; }, [step]);

  useEffect(() => {
    if (selectedStep !== null && selectedStep > max) {
      setSelectedStep(max);
      setEditing(false);
    }
  }, [selectedStep, max]);

  function goTo(next: number) {
    setEditing(false);
    setSelectedStep(next);
  }

  async function action(path: string, method = 'POST', body?: unknown) {
    if (busy.current) return false;
    busy.current = true;
    setWorking(true);
    // Drop any poll started before this action. The action reloads authoritative state.
    sequence.current += 1;
    try {
      await request('/admin/api/initialization' + path, { method, body });
      await load();
      return true;
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败，请重试');
      await load();
      return false;
    } finally {
      busy.current = false;
      if (alive.current) setWorking(false);
    }
  }

  async function logout() {
    try {
      await request('/admin/auth/logout', { method: 'POST' });
      window.location.reload();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '退出失败，请重试');
    }
  }

  async function checkStep(userId?: string) {
    setSelectedStep(step);
    setLocalCheck(step);
    try {
      if (await action(`/checks/${step}`, 'POST', userId ? { user_id: userId } : undefined)) setEditing(false);
    } finally {
      setLocalCheck(null);
    }
  }

  function footerActions() {
    if (!data) return null;
    if (cleanupRequired || (step === 5 && data.phase === 'failed')) {
      return <Button danger type="primary" disabled={disabled} loading={working} onClick={async () => {
        if (await action('/restart')) goTo(1);
      }}>{cleanupRequired ? '重新初始化' : '重新开始'}</Button>;
    }
    if (step === 5) {
      if (data.complete) return <Button type="primary" onClick={enter}>进入系统</Button>;
      if (running) return <Button type="primary" disabled>同步中</Button>;
      return <Button type="primary" loading={working} disabled={locked || data.phase !== 'ready'} onClick={() => void action('/start')}>立即同步</Button>;
    }
    if (editing) return <>
      <Button disabled={working} onClick={() => setEditing(false)}>取消</Button>
      {step === 4 && <Button disabled={disabled} onClick={() => void checkStep()}>使用自动样本重新检测</Button>}
      <Button autoInsertSpace={false} type="primary" htmlType="submit" form={step === 1 ? mappingForm : sampleForm} loading={working} disabled={disabled}>
        {step === 1 ? '保存' : '保存并检测'}
      </Button>
    </>;
    const passed = data.complete || check?.status === 'passed';
    return <>
      {mayEdit && !passed && <Button type="primary" loading={localCheck === step || (checking && data.checking_step === step)}
        disabled={locked} onClick={() => void checkStep()}>
        {check?.status === 'failed' ? '重新检测' : '开始检测'}
      </Button>}
      <Button type={passed ? "primary" : "default"} disabled={locked || !passed} onClick={() => goTo(step + 1)}>下一步</Button>
    </>;
  }

  return <main className="initialization-page">
    <header className="initialization-header">
      <div className="initialization-topbar">
        <div className="initialization-brand">
          <img src={themeLogoUrl(colors.primary)} alt="Evolution Logo" width={32} height={32} />
          <span>Evolution</span>
          <span className="initialization-version">V {buildInfo.version}</span>
        </div>
        <Dropdown trigger={['click']} menu={{ items: [
          { key: 'logout', label: '退出登录', icon: <LogoutOutlined />, onClick: () => void logout() },
        ] }}>
          <Button type="text" className="initialization-account" aria-label={`${name}，管理员菜单`} aria-haspopup="menu">
            <EmployeeIdentity name={name} avatar={session?.profile?.avatar_url} />
          </Button>
        </Dropdown>
      </div>
      <div className="initialization-step-header">
        <div className="initialization-container initialization-heading">
          <h1>企业组织数据初始化</h1>
          <p>完成前置检查后，同步企业的全部部门与人员。</p>
          <div aria-label="初始化步骤">
            <Steps className="initialization-steps"
              classNames={{ item: 'initialization-step', itemRail: 'initialization-step-rail' }}
              size="small" titlePlacement="vertical" responsive={false} current={step - 1}
              items={titles.map((title, index) => {
                const item = data?.checks.find(result => result.step === index + 1);
                const syncStep = index === 4;
                const active = localCheck === index + 1 || (checking && (data.checking_step ?? 1) === index + 1) || (syncStep && running);
                const passed = !active && (!!data?.complete || item?.status === 'passed');
                const failed = !active && (item?.status === 'failed' || (syncStep && data?.phase === 'failed'));
                return {
                  title,
                  content: passed ? '已通过' : failed ? '未通过' : active ? (syncStep ? '同步中' : '检测中') : syncStep ? '待同步' : '待检查',
                  status: passed ? 'finish' : failed ? 'error' : active || index + 1 === step ? 'process' : 'wait',
                  icon: passed ? <CheckOutlined className="initialization-passed" /> : undefined,
                };
              })} />
          </div>
        </div>
      </div>
    </header>
    <section className="initialization-scroll" ref={panel} aria-label={titles[step - 1]} tabIndex={0}>
      <div className="initialization-container initialization-panel-stack">
        {networkError && <Alert type="warning" showIcon
          title={data ? '连接暂时中断，正在重新连接' : '暂时无法读取初始化状态'}
          description={networkError} action={<Button onClick={() => void load()}>重新连接</Button>} />}
        {!data && !networkError && <Card><Space><Spin size="small" />正在读取初始化状态</Space></Card>}
        {data && cleanupRequired && <RestartNotice data={data} />}
        {data && !cleanupRequired && step === 1 && <ConfigurationChecks
          configuration={data.configuration} items={check?.items ?? []} settings={data.settings}
          editing={editing} mayEdit={mayEdit} disabled={disabled} formName={mappingForm}
          onEdit={() => { setSelectedStep(1); setEditing(true); }}
          onSave={async values => {
            if (await action('/settings', 'PUT', values)) {
              setEditing(false);
              message.success('已保存，请重新检测配置');
            }
          }} />}
        {data && (step === 2 || step === 3) && <Card title={titles[step - 1]}><CheckList step={step} items={check?.items ?? []} /></Card>}
        {data && step === 4 && <>
          <Card title="抽样设置" extra={mayEdit && !editing && <Button autoInsertSpace={false} disabled={disabled}
            onClick={() => { setSelectedStep(4); setEditing(true); }}>编辑</Button>}>
            {editing ? <Form<{ user_id: string }> name={sampleForm} id={sampleForm} layout="vertical" disabled={disabled}
              className="initialization-user-check" initialValues={{ user_id: data.field_sample?.mode === 'manual' ? data.field_sample.user_ids[0] : '' }}
              onFinish={values => void checkStep(values.user_id.trim())}>
              <Form.Item name="user_id" label="校验人员 user_id" extra="指定人员需要在应用通讯录可见范围内。"
                rules={[
                  { required: true, whitespace: true, message: '请填写校验人员的 user_id' },
                  { max: 191, message: 'user_id 最多 191 字符' },
                ]}>
                <Input placeholder="请输入飞书 user_id" maxLength={191} />
              </Form.Item>
            </Form> : <p>校验方式：{data.field_sample?.mode === 'manual' ? '手动指定人员' : '自动抽样'}
              {data.field_sample && `；人员 user_id：${data.field_sample.user_ids.join('、') || '无'}`}
            </p>}
          </Card>
          <Card title={titles[3]}>
            {mayEdit && !editing && <Button type="link" className="initialization-mapping-link" disabled={disabled} onClick={() => goTo(1)}>检查字段映射</Button>}
            <p className="initialization-muted">非必填字段允许留空。标注“接口仍须返回”的字段需要飞书返回合法空值，直属上级和部门负责人可由接口省略。全量同步时仍会逐条核验。</p>
            <FieldCheckResults items={check?.items ?? []} requirements={data.required_fields ?? []} />
          </Card>
        </>}
        {data && step === 5 && <SyncDetails data={data} />}
      </div>
    </section>
    <footer className="initialization-footer">
      <div className="initialization-container initialization-footer-inner">
        <span className="initialization-muted">第 {step} 步，共 {titles.length} 步</span>
        <Space wrap size={8}>
          {step > 1 && <Button disabled={locked} onClick={() => goTo(step - 1)}>上一步</Button>}
          {footerActions()}
        </Space>
      </div>
    </footer>
  </main>;
}
