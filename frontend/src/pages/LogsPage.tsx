import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from '@umijs/max';
import { Avatar, Button, DatePicker, Input, Modal, Select, Space, Table, Tag, Tooltip } from 'antd';
import type { TableProps } from 'antd';
import { DownOutlined, EyeOutlined, FileTextOutlined, ReloadOutlined, UpOutlined, UserOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import { query } from '../services/http';
import { PageHeader } from '../components/PageHeader';
import { ResourceState } from '../components/ResourceState';
import { AdaptiveTableCard } from '../components/AdaptiveTableCard';
import { EmployeeIdentity } from '../components/EmployeeIdentity';
import { RawChangeDiff, type RawRecord } from '../components/RawChangeDiff';
import { CopyValue } from '../components/CopyValue';
import { TableActionButton } from '../components/TableActionButton';
import { useResource } from '../services/useResource';
import { EventConnectionStatus, formatTableTime, syncTypes } from '../components/SyncPresentation';

type ObjectType = 'employee' | 'department';
type View = 'all' | 'grouped';
interface DepartmentItem { id: string; name: string; primary: boolean }
interface PersonSummary { name: string; avatar_url?: string | null }
interface Difference {
  field: string; label?: string; before: unknown; after: unknown;
  before_person?: PersonSummary; after_person?: PersonSummary;
}
interface OrganizationChange {
  id: number;
  object_id: string;
  object_name: string;
  source?: string;
  action: string;
  actor: string;
  actor_avatar_url?: string;
  actor_is_user?: boolean;
  job_id?: string;
  event_id?: string;
  committed_at: string;
  changes: Difference[];
  department_change?: Difference | null;
  raw_records?: RawRecord[];
}
interface ChangeGroup { object_id: string; object_name: string; total: number; records: OrganizationChange[] }
interface Filters { keyword?: string; source?: string; action?: string; committed_after?: string; committed_before?: string }
const sources: Record<string, string> = { ...syncTypes, event: '飞书订阅事件' };
const actions: Record<string, string> = { create: '新增', update: '修改', deactivate: '停用', reactivate: '恢复' };
const actionColors: Record<string, string> = { create: 'success', update: 'processing', deactivate: 'error', reactivate: 'success' };
const fieldNames: Record<string, string> = {
  name: '名称', parent_id: '上级部门', leader_user_id: '负责人', status: '状态',
  primary_department_id: '主部门', departments: '部门', job_title: '职位', employee_no: '员工编号',
  email: '电子邮箱', mobile: '手机号', avatar_url: '头像', join_time: '入职时间',
  employee_type_name: '员工类型',
  permission_role_name: '权限角色', store_attribute_id: '门店属性 ID', store_attribute_name: '门店属性',
  is_frozen: '账号冻结', is_resigned: '离职状态', is_activated: '账号激活', is_exited: '退出企业',
  is_unjoin: '未加入', feishu_user_id: '飞书用户 ID', feishu_department_id: '飞书部门 ID',
  open_id: '飞书开放 ID', is_root: '组织根节点',
};
const options = (values: Record<string, string>) => Object.entries(values).map(([value, label]) => ({ value, label }));

function displayValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '-';
  if (field === 'status') return value === 'active' ? '有效' : value === 'inactive' ? '失效' : String(value);
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (Array.isArray(value)) return value.map(item => displayValue(field, item)).join('、');
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

function departmentValue(value: unknown, accent: boolean) {
  const departments = (value ?? []) as DepartmentItem[];
  if (!departments.length) return <span style={accent ? { color: 'var(--app-accent)' } : undefined}>-</span>;
  return <Space size={[8, 4]} separator={<span aria-hidden="true">/</span>} wrap>{departments.map(department => <Space key={department.id} size={4}>
    <span style={accent ? { color: 'var(--app-accent)' } : undefined}>{department.name}</span>
    {department.primary && <Tag variant="filled" style={accent ? { color: 'var(--app-primary)' } : undefined}>主部门</Tag>}
  </Space>)}</Space>;
}

function ChangeDetails({ record }: { record: OrganizationChange }) {
  const rows = [...record.changes.filter(change => !change.field.startsWith('membership:') && change.field !== 'primary_department_id'),
    ...(record.department_change ? [record.department_change] : [])];
  const hiddenFields = new Set(['permission_role_id', 'employee_type_id', 'is_virtual_root']);
  const changes = rows.filter(change => !hiddenFields.has(change.field)
    && JSON.stringify(change.before) !== JSON.stringify(change.after));
  function value(difference: Difference, side: 'before' | 'after') {
    const current = difference[side];
    if (difference.field === 'departments') return departmentValue(current, side === 'after');
    if (difference.field === 'avatar_url' && typeof current === 'string' && current.trim()) {
      return <Avatar size={24} src={current} icon={<UserOutlined />} alt={side === 'before' ? '变更前头像' : '变更后头像'} />;
    }
    const person = side === 'before' ? difference.before_person : difference.after_person;
    if (difference.field === 'leader_user_id' && person) {
      return <span style={side === 'after' ? { color: 'var(--app-accent)' } : undefined}>
        <EmployeeIdentity name={person.name} avatar={person.avatar_url} />
      </span>;
    }
    return <span style={side === 'after' ? { color: 'var(--app-accent)' } : undefined}>
      {displayValue(difference.field, current)}
    </span>;
  }
  const fieldWidth = 180;
  const valueWidth = 220;
  return <Table<Difference> className="change-detail-table" size="small" rowKey="field" pagination={false}
    dataSource={changes} tableLayout="fixed" scroll={{ x: fieldWidth + valueWidth * 2 }}
    columns={[
      { title: '变更字段', width: fieldWidth, render: (_, difference) => difference.label ?? fieldNames[difference.field] ?? difference.field },
      { title: '变更前', width: valueWidth, render: (_, difference) => value(difference, 'before') },
      { title: '变更后', width: valueWidth, render: (_, difference) => value(difference, 'after') },
    ]} />;
}

function LogsView({ objectType, objectId, initialView }: { objectType?: ObjectType; objectId?: string; initialView: View }) {
  const navigate = useNavigate();
  const [type, setType] = useState<ObjectType>(objectType ?? 'employee');
  const [view, setView] = useState<View>(initialView);
  const [filters, setFilters] = useState<Filters>({});
  const [keyword, setKeyword] = useState('');
  const [time, setTime] = useState<[Dayjs, Dayjs] | null>(null);
  const [page, setPage] = useState(1);
  const [rawSelected, setRawSelected] = useState<OrganizationChange | null>(null);
  const [expanded, setExpanded] = useState<React.Key[]>([]);
  const [groupExpanded, setGroupExpanded] = useState<React.Key[]>([]);
  const status = useResource<{ connection?: { status: string; last_event_received_at?: string | null } }>('/admin/api/status', true);
  const currentView = objectId ? 'all' : view;
  const resource = useResource<(OrganizationChange | ChangeGroup)[]>('/admin/api/organization-changes' + query({
    object_type: type, object_id: objectId, view: currentView, page, page_size: 20, ...filters,
    keyword: objectId ? undefined : filters.keyword,
    source: currentView === 'grouped' ? undefined : filters.source,
    action: currentView === 'grouped' ? undefined : filters.action,
  }), true);
  const groups = (resource.data ?? []).filter((row): row is ChangeGroup => 'records' in row);
  const records = (resource.data ?? []).filter((row): row is OrganizationChange => 'changes' in row);
  const total = Number(resource.meta.total ?? 0);
  useEffect(() => {
    const timer = window.setInterval(status.reload, 30000);
    return () => clearInterval(timer);
  }, [status.reload]);
  useEffect(() => {
    if (!resource.loading && resource.data && page > Math.max(1, Math.ceil(total / 20))) setPage(Math.max(1, Math.ceil(total / 20)));
  }, [resource.loading, resource.data, page, total]);
  function changeFilters(next: Filters) {
    setFilters(next); setPage(1); setExpanded([]); setGroupExpanded([]);
  }
  function openObject(id: string) {
    navigate('/logs' + query({ object_type: type, object_id: id, view: currentView === 'grouped' ? 'grouped' : undefined }));
  }
  function changePage(next: number) {
    setPage(next); setExpanded([]); setGroupExpanded([]);
  }
  function nameCell(name: string, id: string) {
    return <Space size={4}>
      {objectId ? <span>{name}</span> : <Button type="link" style={{ padding: 0, height: 'auto' }} onClick={() => openObject(id)}>{name}</Button>}
      <CopyValue value={id} label="对象 ID" />
    </Space>;
  }
  const recordColumns: NonNullable<TableProps<OrganizationChange>['columns']> = [
    { key: 'source', title: '变更来源', width: 200, dataIndex: 'source', render: (_, row) => row.job_id ? <Button type="link" style={{ padding: 0, height: 'auto' }} onClick={() => navigate('/sync/jobs/' + encodeURIComponent(row.job_id!))}>{sources[row.source ?? ''] ?? '历史来源待核实'}</Button>
        : <span>{sources[row.source ?? ''] ?? '历史来源待核实'}</span> },
    { key: 'action', title: '变更类型', width: 120, dataIndex: 'action', render: value => <Tag color={actionColors[value]} variant="filled">{actions[value] ?? value}</Tag> },
    { key: 'actor', title: '执行人', dataIndex: 'actor', width: 160, render: (_, row) => row.actor_is_user ? <EmployeeIdentity name={row.actor} avatar={row.actor_avatar_url} /> : row.actor || '-' },
    { key: 'time', title: '变更时间', width: 180, dataIndex: 'committed_at', render: value => <span className="sync-caption">{formatTableTime(value)}</span> },
    { key: 'raw', title: '操作', fixed: 'right', width: 96, render: (_, row) =>
      <TableActionButton tooltip="查看原始记录" size="small" aria-label="原始记录" icon={<FileTextOutlined />} onClick={() => setRawSelected(row)} /> },
  ];
  const allColumns: TableProps<OrganizationChange>['columns'] = [
    { key: 'name', title: '对象名称', width: 200, fixed: 'left', render: (_, row) => nameCell(row.object_name, row.object_id) },
    ...recordColumns,
  ];
  const expandable: TableProps<OrganizationChange>['expandable'] = {
    expandedRowRender: row => <ChangeDetails record={row} />,
    expandedRowKeys: expanded,
    onExpand: (isExpanded, row) => setExpanded(previous => isExpanded
      ? [...previous, row.id] : previous.filter(key => key !== row.id)),
    rowExpandable: row => row.changes.length > 0,
  };
  function toggleGroup(group: ChangeGroup) {
    const isExpanded = groupExpanded.includes(group.object_id);
    setGroupExpanded(previous => isExpanded
      ? previous.filter(key => key !== group.object_id) : [...previous, group.object_id]);
    if (isExpanded) {
      setExpanded(previous => previous.filter(key => !group.records.some(record => record.id === key)));
    }
  }
  const groupColumns: TableProps<ChangeGroup>['columns'] = [
    { key: 'name', title: '对象名称', width: 200, fixed: 'left', render: (_, group) => nameCell(group.object_name, group.object_id) },
    { key: 'total', title: '记录总数', dataIndex: 'total', width: 120 },
    { key: 'latest', title: '最近变更时间', width: 180,
      render: (_, group) => <span className="sync-caption">{formatTableTime(group.records[0]?.committed_at)}</span> },
    { key: 'actions', title: '操作', fixed: 'right', width: 112, render: (_, group) => {
      const isExpanded = groupExpanded.includes(group.object_id);
      return <Space size={8}>
        <TableActionButton tooltip="查看全部" aria-label={'查看全部 ' + group.total + ' 条记录'} size="small"
          icon={<EyeOutlined />} onClick={() => openObject(group.object_id)} />
        <TableActionButton tooltip={isExpanded ? '收起' : '展开最近5条'} aria-label={isExpanded ? '收起最近记录' : '展开最近5条'}
          aria-expanded={isExpanded} size="small" icon={isExpanded ? <UpOutlined /> : <DownOutlined />}
          onClick={() => toggleGroup(group)} />
      </Space>;
    } },
  ];
  const groupExpandable: TableProps<ChangeGroup>['expandable'] = {
    showExpandColumn: false,
    expandedRowKeys: groupExpanded,
    expandedRowRender: group => <Table<OrganizationChange> rowKey="id" columns={recordColumns}
      dataSource={group.records.slice(0, 5)} size="small" pagination={false} scroll={{ x: 760 }}
      expandable={{ ...expandable, expandedRowKeys: expanded.filter(key => group.records.some(record => record.id === key)) }} />,
  };
  const connection = status.data?.connection;
  const connectionStatus = <Space size={8} wrap><span>飞书事件连接状态</span>{connection ? <Tooltip title={'最近事件接收时间：' + formatTableTime(connection.last_event_received_at)} trigger={['hover', 'focus']}><span tabIndex={0}><EventConnectionStatus status={connection.status} /></span></Tooltip> : <span>{status.error ? '读取失败' : '-'}</span>}</Space>;
  const toolbar = <div className="sync-toolbar">
    <Space size={8} wrap>
      {!objectId && <Select aria-label="对象类型" value={type} style={{ width: 110 }} options={options({ employee: '人员', department: '部门' })}
        onChange={value => { setType(value); setPage(1); setExpanded([]); setGroupExpanded([]); }} />}
      {currentView === 'all' && <>
        <Select aria-label="变更来源" allowClear placeholder="全部变更来源" style={{ width: 160 }} options={options(sources)} value={filters.source}
          onChange={value => changeFilters({ ...filters, source: value })} />
        <Select aria-label="变更类型" allowClear placeholder="全部变更类型" style={{ width: 145 }} options={options(actions)} value={filters.action}
          onChange={value => changeFilters({ ...filters, action: value })} />
      </>}
      <DatePicker.RangePicker aria-label="变更时间" placeholder={['开始时间', '结束时间']} showTime value={time} onChange={value => {
        const range = value?.[0] && value?.[1] ? [value[0], value[1]] as [Dayjs, Dayjs] : null;
        setTime(range); changeFilters({ ...filters, committed_after: range?.[0].toISOString(), committed_before: range?.[1].toISOString() });
      }} />
      <Tooltip title="刷新"><Button icon={<ReloadOutlined />} aria-label="刷新记录" onClick={resource.reload} /></Tooltip>
    </Space>
    <Space size={8} wrap>
      {!objectId && <Input.Search allowClear placeholder="搜索名称或对象 ID" value={keyword}
        onChange={event => { setKeyword(event.target.value); changeFilters({ ...filters, keyword: event.target.value.trim() }); }} style={{ maxWidth: 240 }} />}
    </Space>
  </div>;
  const tabs = objectId ? undefined : [{ key: 'all', tab: '全部记录' }, { key: 'grouped', tab: '按对象查看' }];
  function changeView(key: string) {
    setView(key === 'grouped' ? 'grouped' : 'all');
    changePage(1);
  }
  const pagination = { current: page, pageSize: 20, total, showSizeChanger: false, onChange: changePage };
  const tableState = <ResourceState {...resource} empty={!resource.data?.length}><span /></ResourceState>;
  const showTable = !resource.error && Boolean(currentView === 'grouped' ? groups.length : records.length);
  const tabExtra = tabs ? { right: connectionStatus } : undefined;
  return <PageHeader className="logs-list-page" area="组织管理" title={objectId ? '对象变更记录' : '变更记录'}
    description={objectId ? '查看该对象的完整同步变更记录。' : '查看飞书组织数据已提交的变更。'}>
    {currentView === 'grouped'
      ? <AdaptiveTableCard<ChangeGroup> tabList={tabs} tabBarExtraContent={tabExtra} activeTabKey={view} onTabChange={changeView}
        rowKey="object_id" dataSource={groups} showTable={showTable} columns={groupColumns}
        pagination={pagination} scroll={{ x: 640 }} expandable={groupExpandable}>
        {toolbar}{!showTable && tableState}
      </AdaptiveTableCard>
      : <AdaptiveTableCard<OrganizationChange> title={objectId ? '对象历史' : undefined} tabList={tabs}
        tabBarExtraContent={tabExtra} activeTabKey={view} onTabChange={changeView}
        headerExtra={objectId ? <Button onClick={() => navigate('/logs' + query({ object_type: type, view: initialView === 'grouped' ? 'grouped' : undefined }))}>返回列表</Button> : undefined}
        rowKey="id" dataSource={records} showTable={showTable} columns={allColumns}
        pagination={pagination} scroll={{ x: 1040 }} expandable={expandable}>
        {toolbar}{!showTable && tableState}
      </AdaptiveTableCard>}
    <Modal title={<Space size={8}><span>原始记录 JSON</span>{rawSelected && <Tag variant="filled">{rawSelected.id}</Tag>}</Space>}
      width={1100} open={Boolean(rawSelected)} onCancel={() => setRawSelected(null)} footer={null}>
      {rawSelected && <Space className="raw-change-summary" size={[8, 4]} separator={<span aria-hidden="true">·</span>} wrap>
        <span>{rawSelected.object_name || rawSelected.object_id}</span>
        <span>{sources[rawSelected.source ?? ''] ?? '历史来源待核实'}</span>
        <span>{formatTableTime(rawSelected.committed_at)}</span>
      </Space>}
      <RawChangeDiff records={rawSelected?.raw_records ?? []} />
    </Modal>
  </PageHeader>;
}

export function LogsPage() {
  const [params] = useSearchParams();
  const objectId = params.get('object_id') ?? undefined;
  const objectType = params.get('object_type') === 'department' ? 'department' : 'employee';
  const initialView = params.get('view') === 'grouped' ? 'grouped' : 'all';
  return <LogsView key={objectType + ':' + (objectId ?? '') + ':' + initialView} objectType={objectType} objectId={objectId} initialView={initialView} />;
}
export default LogsPage;