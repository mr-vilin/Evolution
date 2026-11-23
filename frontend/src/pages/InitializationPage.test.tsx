import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import InitializationPage, { type InitializationStatus } from './InitializationPage';
import { AuthGate } from '../components/AuthGate';

afterEach(() => vi.unstubAllGlobals());
const base = (): InitializationStatus => ({ flow_id: 'flow', phase: 'pending', complete: false, checks: [], settings: {} });
const check = (step: number) => ({ step, title: `步骤${step}`, status: 'passed', items: [{ key: 'check', title: `已核验${step}`, status: 'passed', message: '' }] });

const fieldState = (): InitializationStatus => ({
  ...base(), phase: 'precheck_failed', field_sample: { mode: 'automatic', user_ids: ['u', 'v'] },
  checks: [1, 2, 3].map(check).concat({ ...check(4), status: 'failed', items: [
    { key: 'u:name', field: 'name', object_id: 'u', object_type: 'user', title: '姓名', status: 'passed', message: '' },
    { key: 'v:name', field: 'name', object_id: 'v', object_type: 'user', title: '姓名', status: 'passed', message: '' },
    { key: 'u:role', field: 'permission_role', object_id: 'u', object_type: 'user', title: '权限角色', status: 'failed', message: '自定义字段值未返回或格式错误' },
    { key: 'v:role', field: 'permission_role', object_id: 'v', object_type: 'user', title: '权限角色', status: 'passed', message: '' },
    { key: 'u:store', field: 'store_attribute', object_id: 'u', object_type: 'user', title: '门店属性', status: 'pending', message: '字段定义校验未通过，尚未校验人员字段值' },
  ] } as InitializationStatus['checks'][number]),
});

it('逐字段显示通过、失败和未校验，标明样本及失败原因', async () => {
  vi.stubGlobal('fetch', async () => Response.json({ data: fieldState(), meta: {} }));
  render(<App><InitializationPage /></App>);
  const table = await screen.findByRole('table');
  const rows = within(table).getAllByRole('row');
  expect(rows).toHaveLength(4);
  expect(within(rows[1]).getByText('已通过')).not.toBeNull();
  expect(within(rows[2]).getByText('未通过')).not.toBeNull();
  expect(within(rows[2]).getByText('通过 1 / 2')).not.toBeNull();
  expect(within(rows[2]).getByText('自定义字段值未返回或格式错误', { exact: false })).not.toBeNull();
  expect(within(rows[3]).getByText('未校验')).not.toBeNull();
  expect(screen.getByText('校验方式：自动抽样；人员 user_id：u、v')).not.toBeNull();
});

it('检查前即列出填写要求，区分非必填和条件必填', async () => {
  const state: InitializationStatus = { ...base(), checks: [1, 2, 3].map(check), required_fields: [
    { key: 'user:leader_user_id', object_type: 'user', field: 'leader_user_id', title: '直属上级', requirement: '非必填', rule: '允许未配置、空值或接口省略。' },
    { key: 'department:leader_user_id', object_type: 'department', field: 'leader_user_id', title: '部门负责人', requirement: '非必填', rule: '允许未配置、空值或接口省略。' },
    { key: 'user:orders', object_type: 'user', field: 'orders', title: '部门顺序与唯一主部门', requirement: '条件必填', rule: '有部门时须指定唯一主部门。' },
  ] };
  vi.stubGlobal('fetch', async () => Response.json({ data: state, meta: {} }));
  render(<App><InitializationPage /></App>);
  const table = await screen.findByRole('table');
  expect(within(table).getByRole('columnheader', { name: '填写要求' })).not.toBeNull();
  expect(within(table).getAllByText('非必填')).toHaveLength(2);
  expect(within(table).getAllByText('允许未配置、空值或接口省略。')).toHaveLength(2);
  expect(within(table).getByText('条件必填')).not.toBeNull();
  expect(within(table).getAllByText('待校验')).toHaveLength(3);
});

it('保存并检测指定人员后回到文本态，等待管理员前进和开始同步', async () => {
  let state = fieldState();
  const mutations = vi.fn();
  vi.stubGlobal('fetch', async (url: string, options: RequestInit) => {
    if (options.method === 'POST') {
      mutations(url, options.body ? JSON.parse(options.body as string) : undefined);
      state = { ...state, phase: 'ready', checks: [1, 2, 3, 4].map(check), field_sample: { mode: 'manual', user_ids: ['manual'] } };
    }
    return Response.json({ data: state, meta: {} });
  });
  render(<App><InitializationPage /></App>);
  fireEvent.click(await screen.findByRole('button', { name: '编辑' }));
  fireEvent.change(await screen.findByLabelText('校验人员 user_id'), { target: { value: ' manual ' } });
  fireEvent.click(screen.getByRole('button', { name: '保存并检测' }));
  await screen.findByText('校验方式：手动指定人员；人员 user_id：manual');
  expect(mutations).toHaveBeenCalledExactlyOnceWith('/admin/api/initialization/checks/4', { user_id: 'manual' });
  expect(screen.queryByLabelText('校验人员 user_id')).toBeNull();
  expect(screen.queryByRole('button', { name: '立即同步' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
  await screen.findByRole('button', { name: '立即同步' });
});

it('空白 user_id 在字段旁提示且不请求；自动重检不携带手动 ID', async () => {
  const mutations = vi.fn();
  vi.stubGlobal('fetch', async (_url: string, options: RequestInit) => {
    if (options.method === 'POST') mutations(options.body);
    return Response.json({ data: fieldState(), meta: {} });
  });
  render(<App><InitializationPage /></App>);
  fireEvent.click(await screen.findByRole('button', { name: '编辑' }));
  fireEvent.change(await screen.findByLabelText('校验人员 user_id'), { target: { value: '  ' } });
  fireEvent.click(screen.getByRole('button', { name: '保存并检测' }));
  await screen.findByText('请填写校验人员的 user_id');
  expect(mutations).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '使用自动样本重新检测' }));
  await waitFor(() => expect(mutations).toHaveBeenCalledExactlyOnceWith(undefined));
});

it('未初始化管理员只看到全屏向导，工作台内容不挂载', async () => {
  const state = { ...base(), phase: 'cleanup_required' };
  vi.stubGlobal('fetch', async (url: string) => Response.json({ data: url === '/admin/auth/session' ? { open_id: 'ou', csrf_token: 'csrf', initialization_complete: false, profile: { name: '林晓', avatar_url: 'https://example.test/avatar.png' } } : state, meta: {} }));
  render(<App><AuthGate><div>工作台业务资料</div></AuthGate></App>);
  await screen.findByText('需要按新流程重新初始化');
  expect(screen.getByAltText('Evolution Logo')).not.toBeNull();
  expect(screen.getByText('林晓')).not.toBeNull();
  expect(screen.getByAltText('林晓的头像').getAttribute('src')).toBe('https://example.test/avatar.png');
  expect(screen.queryByRole('menuitem', { name: /退出登录/ })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /林晓.*管理员菜单/ }));
  await screen.findByRole('menuitem', { name: /退出登录/ });
  expect(screen.getByRole('region', { name: '检查配置' })).not.toBeNull();
  expect(screen.queryByText('工作台业务资料')).toBeNull();
  expect(screen.getByRole('button', { name: '重新初始化' })).not.toBeNull();
  expect(screen.queryByRole('button', { name: '立即同步' })).toBeNull();
});

it('逐步检测通过才能前进，所有预检通过后仍要手动同步', async () => {
  let state = base();
  const calls: string[] = [];
  vi.stubGlobal('fetch', async (url: string, options: RequestInit) => {
    if (options.method === 'POST') {
      calls.push(url);
      if (url.includes('/checks/')) {
        const step = Number(url.split('/').at(-1));
        state = { ...state, checks: [...state.checks, check(step)], phase: step === 4 ? 'ready' : 'pending' };
      } else if (url.endsWith('/start')) {
        state = { ...state, phase: 'running', job: { job_id: 'job', status: 'running', phase: 'employees', progress: { employees_processed: 8 } } };
        return Response.json({ data: { job_id: 'job' }, meta: {} });
      }
    }
    return Response.json({ data: state, meta: {} });
  });
  render(<App><InitializationPage /></App>);
  expect(screen.queryByRole('button', { name: '立即同步' })).toBeNull();
  const checks = ['检查配置', '测试飞书连接', '试读部门与人员', '核验所需字段'];
  for (const [index, title] of checks.entries()) {
    expect(await screen.findByRole('region', { name: title })).not.toBeNull();
    expect(Boolean(screen.queryByRole('button', { name: '上一步' }))).toBe(index > 0);
    const next = screen.getByRole<HTMLButtonElement>('button', { name: '下一步' });
    expect(next.disabled).toBe(true);
    fireEvent.click(await screen.findByRole('button', { name: '开始检测' }));
    await waitFor(() => expect(next.disabled).toBe(false));
    fireEvent.click(next);
  }
  const start = await screen.findByRole('button', { name: '立即同步' });
  expect(calls).toEqual([1, 2, 3, 4].map(step => `/admin/api/initialization/checks/${step}`));
  expect(screen.queryByText('全企业及无部门人员覆盖验收')).toBeNull();
  expect(screen.queryByRole('button', { name: '保存依据并确认覆盖验收' })).toBeNull();
  fireEvent.click(start);
  await screen.findByText('已采集人员：8');
  expect(calls.filter(url => url.endsWith('/start'))).toHaveLength(1);
  expect(screen.queryByText('初始化完成')).toBeNull();
});

it('失败后必须清理重来，不显示立即同步；历史通过项不会直接放行', async () => {
  let state: InitializationStatus = { ...base(), phase: 'failed', checks: [1, 2, 3, 4].map(check), last_error: { code: 'INTERRUPTED', message: '后台任务已中断' } };
  const mutations: string[] = [];
  vi.stubGlobal('fetch', async (url: string, options: RequestInit) => {
    if (options.method === 'POST') {
      mutations.push(url);
      if (url.endsWith('/restart')) state = { ...base(), flow_id: 'fresh' };
      if (url.includes('/checks/')) state = { ...state, phase: 'precheck_failed', checks: [{ ...check(1), status: 'failed', items: [] }] };
    }
    return Response.json({ data: state, meta: {} });
  });
  render(<App><InitializationPage /></App>);
  const restart = await screen.findByRole('button', { name: '重新开始' });
  expect(screen.queryByRole('button', { name: '立即同步' })).toBeNull();
  fireEvent.click(restart);
  await waitFor(() => expect(mutations).toEqual(['/admin/api/initialization/restart']));
  await screen.findByText('存储与任务单例');
  const detect = screen.getByRole<HTMLButtonElement>('button', { name: /开始检测/ });
  await waitFor(() => expect(detect.disabled).toBe(false));
  fireEvent.click(detect);
  await waitFor(() => expect(mutations).toEqual(['/admin/api/initialization/restart', '/admin/api/initialization/checks/1']));
  expect(screen.queryByRole('button', { name: '立即同步' })).toBeNull();
});

it('后端确认完成后展示人数并由管理员进入系统', async () => {
  const enter = vi.fn();
  vi.stubGlobal('fetch', async () => Response.json({ data: { ...base(), phase: 'complete', complete: true, counts: { departments: 3, employees: 24 } }, meta: {} }));
  render(<App><InitializationPage onComplete={enter} /></App>);
  fireEvent.click(await screen.findByRole('button', { name: '进入系统' }));
  expect(enter).toHaveBeenCalledOnce();
  expect(screen.getByText('已同步 3 个部门、24 位人员，全部校验通过。')).not.toBeNull();
});

const mappingState = (): InitializationStatus => ({
  ...base(), phase: 'precheck_failed',
  settings: { permission_role: 'role', store_attribute: 'store', employee_type_options: { '01': '正式员工', '2': '临时员工' } },
});

it('员工类型按行回显，编辑、增加和删除后保存映射并可重新读取', async () => {
  let state: InitializationStatus = { ...mappingState(), checks: [1].map(check) };
  const save = vi.fn();
  vi.stubGlobal('fetch', async (url: string, options: RequestInit) => {
    if (options.method === 'POST' && url.endsWith('/checks/1')) state = { ...state, checks: [check(1)] };
    if (options.method === 'PUT') {
      const settings = JSON.parse(options.body as string);
      save(settings);
      state = { ...state, checks: [], phase: 'pending', settings };
    }
    return Response.json({ data: state, meta: {} });
  });
  render(<App><InitializationPage /></App>);
  fireEvent.click(await screen.findByRole('button', { name: '上一步' }));
  expect(screen.getByText('正式员工')).not.toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '编辑' }));
  fireEvent.change(screen.getByDisplayValue('正式员工'), { target: { value: ' 全职员工 ' } });
  fireEvent.click(screen.getByRole('button', { name: '新增一行' }));
  fireEvent.change(screen.getAllByLabelText('选项 ID')[2], { target: { value: ' 03 ' } });
  fireEvent.change(screen.getAllByLabelText('选项名称')[2], { target: { value: '实习员工' } });
  // 数字键由接口对象枚举在前；删除对应的临时员工行后，其余行的值应保持。
  fireEvent.click(screen.getByRole('button', { name: '删除第 1 行' }));
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  await waitFor(() => expect(save).toHaveBeenCalledExactlyOnceWith({
    permission_role: 'role', store_attribute: 'store', employee_type_options: { '01': '全职员工', '03': '实习员工' },
  }));
  await screen.findByText('全职员工');
  expect(screen.getByText('选项 ID 03')).not.toBeNull();
  expect(screen.queryByText('临时员工')).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.getByRole<HTMLButtonElement>('button', { name: '下一步' }).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '开始检测' }));
  await waitFor(() => expect(screen.getByRole<HTMLButtonElement>('button', { name: '下一步' }).disabled).toBe(false));
});

it('空白字段及去除首尾空格后的重复 ID 阻止保存，修正后可提交', async () => {
  const save = vi.fn();
  vi.stubGlobal('fetch', async (_url: string, options: RequestInit) => {
    if (options.method === 'PUT') save(JSON.parse(options.body as string));
    return Response.json({ data: mappingState(), meta: {} });
  });
  render(<App><InitializationPage /></App>);
  fireEvent.click(await screen.findByRole('button', { name: '编辑' }));
  fireEvent.click(screen.getByRole('button', { name: '新增一行' }));
  fireEvent.change(screen.getAllByLabelText('选项 ID')[2], { target: { value: '   ' } });
  fireEvent.change(screen.getAllByLabelText('选项名称')[2], { target: { value: '   ' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  await screen.findByText('请填写选项 ID');
  await screen.findByText('请填写选项名称');
  expect(save).not.toHaveBeenCalled();
  fireEvent.change(screen.getAllByLabelText('选项 ID')[2], { target: { value: ' 01 ' } });
  fireEvent.change(screen.getAllByLabelText('选项名称')[2], { target: { value: '实习员工' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  await screen.findAllByText('选项 ID 不能重复');
  expect(save).not.toHaveBeenCalled();
  fireEvent.change(screen.getAllByLabelText('选项 ID')[2], { target: { value: '3' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  await waitFor(() => expect(save).toHaveBeenCalledOnce());
});

it('保存失败及状态重新读取后保留编辑内容，删除全部行可保存原契约允许的空映射', async () => {
  const save = vi.fn();
  vi.stubGlobal('fetch', async (_url: string, options: RequestInit) => {
    if (options.method === 'PUT') {
      save(JSON.parse(options.body as string));
      return Response.json({ error: { code: 'UNAVAILABLE', message: '设置暂时无法保存' } }, { status: 503 });
    }
    return Response.json({ data: mappingState(), meta: {} });
  });
  render(<App><InitializationPage /></App>);
  fireEvent.click(await screen.findByRole('button', { name: '编辑' }));
  fireEvent.change(await screen.findByDisplayValue('正式员工'), { target: { value: '待保存名称' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  await screen.findByText('设置暂时无法保存');
  await waitFor(() => expect((screen.getByRole('button', { name: '新增一行' }) as HTMLButtonElement).disabled).toBe(false));
  expect(screen.getByDisplayValue('待保存名称')).not.toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '删除第 1 行' }));
  fireEvent.click(screen.getByRole('button', { name: '删除第 1 行' }));
  expect(screen.getByText('暂未配置员工类型选项')).not.toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  await waitFor(() => expect(save).toHaveBeenLastCalledWith({ permission_role: 'role', store_attribute: 'store', employee_type_options: {} }));
});

it('检查期间保持配置只读且禁用编辑和下一步', async () => {
  vi.stubGlobal('fetch', async () => Response.json({ data: { ...mappingState(), phase: 'checking', checking_step: 1 }, meta: {} }));
  render(<App><InitializationPage /></App>);
  expect(await screen.findByText('正式员工')).not.toBeNull();
  expect(screen.getByRole<HTMLButtonElement>('button', { name: '编辑' }).disabled).toBe(true);
  expect(screen.getByRole<HTMLButtonElement>('button', { name: '下一步' }).disabled).toBe(true);
  expect(screen.queryByRole('textbox')).toBeNull();
});
