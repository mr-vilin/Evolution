import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import { Alert, App, Badge, Button, Card, Drawer, Grid, Input, Select, Space, Statistic, Switch, Tag, Tooltip, Tree, Typography, theme } from 'antd';
import { CaretDownFilled, EditOutlined, EyeOutlined, LeftOutlined, MenuOutlined, RightOutlined, SyncOutlined } from '@ant-design/icons';
import { useNavigate } from '@umijs/max';
import type { DataNode } from 'antd/es/tree';
import type { TreeProps } from 'antd';
import type { Department, Employee } from '../domain';
import { ApiError, type Meta, query, request } from '../services/http';
import { useResource } from '../services/useResource';
import { datasetQuery, sameDataset, useOrganizationPeople, useOrganizationTree } from '../services/useOrganization';
import { rangeLabel, useOrganizationSelection } from '../services/useOrganizationSelection';
import { PageHeader } from '../components/PageHeader';
import { ResourceTable } from '../components/ResourceTable';
import { OrganizationStoreEditor } from '../components/OrganizationStoreEditor';
import { StoreEditor } from '../components/StoreEditor';
import { EmployeeDepartments } from '../components/EmployeeDepartments';
import { EmployeeDetailDrawer } from '../components/EmployeeDetailDrawer';
import { DepartmentDetailDrawer } from '../components/DepartmentDetailDrawer';
import { CopyUserId, EmployeeAccountStatus, EmployeeIdentity } from '../components/EmployeeIdentity';
import { contactLabel } from '../components/employeePresentation';
import { EmployeeValue } from '../components/EmployeeValue';

const ROOT: Department = { id: '0', parent_id: null, name: '本组织', path: ['本组织'], status: 'active', is_virtual_root: true, is_store: false, store_code: null, notes: null, has_children: true };
interface OrganizationSummary {
  department_id: string; department_count: number; employee_count: number; unactivated_count: number; unjoin_count: number; resigned_count: number; member_count: number; members_limited: boolean;
}
const summaryItems = [
  ['department_count', '总部门数'], ['employee_count', '总人数'], ['unactivated_count', '未激活'],
  ['unjoin_count', '未加入'], ['resigned_count', '已离职'],
] as const;
type StatusView = 'none' | 'unactivated' | 'unjoin' | 'resigned';
const statusViews: Record<string, { value: StatusView; label: string }> = {
  unactivated_count: { value: 'unactivated', label: '未激活' },
  unjoin_count: { value: 'unjoin', label: '未加入' },
  resigned_count: { value: 'resigned', label: '已离职' },
};
const accountOptions = [
  { label: '全部账号状态', value: 'all' }, { label: '已激活', value: 'activated' }, { label: '未激活', value: 'unactivated' },
  { label: '已暂停', value: 'frozen' }, { label: '未加入', value: 'unjoin' }, { label: '状态未知', value: 'unknown' },
];
export function OrganizationPage() {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const accountBadgeColors: Record<string, string> = {
    activated: token.colorSuccess, unactivated: token.colorWarning, frozen: token.colorError,
    unjoin: token.colorBgLayout, unknown: token.colorBgLayout,
  };
  const compactColumns = Grid.useBreakpoint().xs === true;
  const navigate = useNavigate();
  const [employeeId, setEmployeeId] = useState<string>();
  const [departmentId, setDepartmentId] = useState<string>();
  const [includeInactive, setIncludeInactive] = useState(false);
  const tree = useOrganizationTree(includeInactive);
  const [selected, setSelected] = useState<string>('0');
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<string[]>(['0']);
  const [memberScopeOpen, setMemberScopeOpen] = useState(false);
  const [memberChoice, setMemberChoice] = useState<{ departmentId: string; descendants: boolean }>();
  const [keyword, setKeyword] = useState('');
  const [accountStatus, setAccountStatus] = useState('all');
  const [statusView, setStatusView] = useState<StatusView>('none');
  const [treeOpen, setTreeOpen] = useState(false);
  const [treeCollapsed, setTreeCollapsed] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [editor, setEditor] = useState<{ departments: Department[]; meta: Meta } | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [singleOpen, setSingleOpen] = useState(false);
  const [openingEditor, setOpeningEditor] = useState(false);
  const [notice, setNotice] = useState('');
  const grid = useRef<HTMLDivElement>(null);
  const retries = useRef(0);
  const recover = useCallback(() => { setNotice('数据已变化，已保留原选择和编辑草稿，请核对实际目标。'); tree.reload(); }, [tree.reload]);
  const selection = useOrganizationSelection(tree.meta, recover);
  useLayoutEffect(() => {
    const element = grid.current;
    if (!element) return;
    const resize = () => element.style.setProperty('--org-panel-height', `${Math.max(0, window.innerHeight - element.getBoundingClientRect().top - window.scrollY - 16)}px`);
    resize();
    const observer = new ResizeObserver(resize);
    if (element.parentElement) observer.observe(element.parentElement);
    window.addEventListener('resize', resize);
    return () => { observer.disconnect(); window.removeEventListener('resize', resize); };
  }, [notice, selection.error]);
  const searchResource = useResource<Department[]>(search.trim() && tree.ready
    ? '/admin/api/organization/search' + query({ keyword: search.trim(), include_inactive: includeInactive, ...datasetQuery(tree.meta) }) : null);
  const companySummary = useResource<OrganizationSummary>(tree.ready
    ? '/admin/api/organization/summary' + query({ department_id: '0', ...datasetQuery(tree.meta) }) : null);
  const departmentSummary = useResource<OrganizationSummary>(tree.ready && selected !== '0'
    ? '/admin/api/organization/summary' + query({ department_id: selected, ...datasetQuery(tree.meta) }) : null);
  const summary = selected === '0' ? companySummary : departmentSummary;
  const companyStats = companySummary.data?.department_id === '0' && sameDataset(companySummary.meta, tree.meta) ? companySummary.data : null;
  const activeSummary = summary.data?.department_id === selected && sameDataset(summary.meta, tree.meta) ? summary.data : null;
  const membersLimited = activeSummary?.members_limited === true;
  const descendants = !membersLimited && (memberChoice?.departmentId === selected ? memberChoice.descendants : true);
  const people = useOrganizationPeople(activeSummary && !summary.error ? selected : undefined, descendants, keyword, accountStatus, tree.meta, statusView);
  function toggleStatusView(value: StatusView) {
    setStatusView(current => current === value ? 'none' : value);
    setSelected('0'); setAccountStatus('all'); setMemberChoice(undefined); setKeyword(''); setMemberScopeOpen(false);
  }
  const scroll = useRef<HTMLDivElement>(null);
  const [tableBodyHeight, setTableBodyHeight] = useState(240);
  useLayoutEffect(() => {
    const element = scroll.current;
    const header = element?.querySelector<HTMLElement>('.ant-table-header');
    if (!element || !header) return;
    const resize = () => setTableBodyHeight(Math.max(0, element.clientHeight - header.offsetHeight));
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const body = scroll.current?.querySelector('.ant-table-body');
    if (body) body.scrollTop = 0;
  }, [people.path]);
  const versionError = people.error?.code === 'DATASET_CHANGED' || summary.error?.code === 'DATASET_CHANGED' || companySummary.error?.code === 'DATASET_CHANGED' || searchResource.error?.code === 'DATASET_CHANGED'
    || Object.values(tree.branches).some(branch => branch.error?.code === 'DATASET_CHANGED');
  useEffect(() => { if (versionError && retries.current < 2) { retries.current += 1; recover(); } }, [versionError, recover]);
  useEffect(() => { if (people.data.length) retries.current = 0; }, [people.data]);
  const visible = search.trim() ? searchResource.data ?? [] : tree.nodes;
  useEffect(() => {
    if (search.trim() || !tree.ready) return;
    for (const row of tree.nodes) {
      if (expanded.includes(row.id) && row.has_children && !tree.branches[row.id]?.loaded
        && !tree.branches[row.id]?.loading && !tree.branches[row.id]?.error) void tree.load(row.id);
    }
  }, [tree.nodes, tree.branches, tree.ready, tree.load, search, expanded]);
  const current = selected === '0' ? ROOT : [...tree.nodes, ...(searchResource.data ?? []), ...(editor?.departments ?? [])].find(row => row.id === selected);
  const hits = new Set((searchResource.meta.matched_ids as string[] | undefined) ?? []);
  function retry() { retries.current = 0; tree.reload(); }
  const byId = new Map(visible.map(row => [row.id, row]));
  const nodes = new Map<string, DataNode>();
  const checkedKeys: string[] = [];
  const halfCheckedKeys: string[] = [];
  for (const department of [ROOT, ...visible.filter(row => row.id !== '0')]) {
    const state = selection.states[department.id];
    const checked = department.id === '0' ? state?.descendants === 'all' : Boolean(state?.self_selected);
    const halfChecked = department.id === '0' ? state?.descendants === 'partial' : !state?.self_selected && !!state && state.descendants !== 'none';
    if (checked) checkedKeys.push(department.id);
    else if (halfChecked) halfCheckedKeys.push(department.id);
    const selectedCount = state?.selected_count ?? 0;
    const countDiameter = Math.max(22, String(selectedCount).length * 8 + 6);
    const rangeColor = state?.self_selected
      ? (state.descendants === 'all' || !department.has_children ? 'all' : 'self') : 'descendants';
    const rangeDescription = `${department.name}：${rangeLabel(state)}，已选 ${selectedCount} 个部门`;
    nodes.set(department.id, { key: department.id, isLeaf: department.id !== '0' && !department.has_children,
      disableCheckbox: department.status !== 'active' || !selection.ready || openingEditor,
      children: [], title: <span className="org-tree-title">
      <span className={hits.has(department.id) ? 'tree-hit' : ''}>{department.name}</span>
      {department.id === '0' && <label className="org-inactive-toggle" onClick={event => event.stopPropagation()} onDoubleClick={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()}>
        <Switch size="small" aria-label="显示失效部门" checked={includeInactive} onChange={setIncludeInactive} />
        <span>显示失效部门</span>
      </label>}
      {department.status !== 'active' && <Tag>失效</Tag>}{department.is_store && <Tag color="blue">门店</Tag>}
      {department.id !== '0' && selectedCount > 0 && <Tooltip title={rangeDescription}>
        <span className={`org-range-count org-range-${rangeColor}`} style={{ width: countDiameter, height: countDiameter }}
          role="img" aria-label={rangeDescription}>{selectedCount}</span>
      </Tooltip>}
    </span> });
  }
  for (const department of visible) if (department.id !== '0') (nodes.get(department.parent_id ?? '0') ?? nodes.get('0'))!.children!.push(nodes.get(department.id)!);
  for (const [id, node] of nodes) {
    node.children?.sort((a, b) => (byId.get(String(a.key))?.sort_order ?? 0) - (byId.get(String(b.key))?.sort_order ?? 0) || String(a.key).localeCompare(String(b.key)));
    const branch = tree.branches[id];
    if (!search.trim() && (branch?.loading || branch?.cursor || branch?.error)) node.children?.push({ key: `page:${id}`, selectable: false, checkable: false, isLeaf: true,
      title: <Button type="link" loading={branch.loading} onClick={event => { event.stopPropagation(); void tree.load(id, Boolean(branch.cursor)); }}>
        {branch.error ? `重试加载${id === '0' ? '本组织' : byId.get(id)?.name ?? '部门'}` : branch.loading ? '正在加载' : '加载更多部门'}</Button> });
  }
  const onDrop: TreeProps['onDrop'] = async info => {
    if (!info.dropToGap || search.trim() || !tree.ready) return;
    const department = byId.get(String(info.dragNode.key)); const anchor = byId.get(String(info.node.key));
    if (!department || !anchor || department.parent_id !== anchor.parent_id) return;
    const relative = info.dropPosition - Number(info.node.pos.split('-').at(-1));
    try {
      await request('/admin/api/organization/order', { method: 'POST', body: { ...datasetQuery(tree.meta), department_id: department.id,
        parent_id: department.parent_id ?? '0', anchor_id: anchor.id, position: relative < 0 ? 'before' : 'after' } });
      message.success('部门顺序已保存'); tree.reload();
    } catch (reason) { message.error(reason instanceof Error ? reason.message : '排序失败'); if (reason instanceof ApiError && reason.status === 409) recover(); }
  };
  async function openBatch() {
    if (!selection.ready || !selection.count || openingEditor) return;
    setOpeningEditor(true);
    try { setEditor(await selection.details()); setEditorOpen(true); }
    catch (reason) { message.error(reason instanceof Error ? reason.message : '读取目标失败'); if (reason instanceof ApiError && reason.status === 409) recover(); }
    finally { setOpeningEditor(false); }
  }
  async function subtreeSync() {
    if (!selected || selected === '0') return;
    setSyncing(true);
    try { const result = await request<{ job_id: string; reused?: boolean }>('/admin/api/sync/jobs', { method: 'POST', body: { type: 'subtree', root_department_id: selected } }); message.success(result.data.reused ? '已打开相同范围的活动任务' : '局部同步任务已创建'); navigate(`/sync/jobs/${encodeURIComponent(result.data.job_id)}`); }
    catch (reason) { message.error(reason instanceof Error ? reason.message : '创建任务失败'); }
    finally { setSyncing(false); }
  }
  const treePanel = <Card className="org-tree-card" title={
    <Input.Search aria-label="搜索部门名称" allowClear placeholder="搜索部门名称" value={search} onChange={event => setSearch(event.target.value)} />
  }><div className="org-tree-controls">
    {searchResource.loading && <Typography.Text>正在搜索</Typography.Text>}
    {searchResource.error && <Alert type="error" title={searchResource.error.message} action={<Button onClick={retry}>重试</Button>} />}
    {tree.branches['0']?.error && <Alert type="error" title={tree.branches['0'].error.message} action={<Button onClick={retry}>重试</Button>} />}
    </div><div className="org-tree-scroll" role="region" aria-label="部门树列表" tabIndex={0}>
    <Tree className="org-tree" blockNode checkable checkStrictly checkedKeys={{ checked: checkedKeys, halfChecked: halfCheckedKeys }}
      onCheck={(_, info) => void selection.toggle(String(info.node.key))} showLine={{ showLeafIcon: false }}
      switcherIcon={node => <CaretDownFilled style={{ transform: `rotate(${node.expanded ? 0 : -90}deg)` }}
        aria-label={`${node.expanded ? '收起' : '展开'}${node.eventKey === '0' ? '本组织' : byId.get(String(node.eventKey))?.name ?? '部门'}`} />}
      treeData={[nodes.get('0')!]} expandedKeys={search.trim() ? ['0', ...visible.map(row => row.id)] : expanded}
      onExpand={(keys, info) => { if (search.trim()) return; setExpanded(keys.map(String)); if (info.expanded && !tree.branches[String(info.node.key)]?.loaded) void tree.load(String(info.node.key)); }}
      selectedKeys={selected ? [selected] : []} onSelect={keys => { setStatusView('none'); setSelected(keys[0] ? String(keys[0]) : '0'); setTreeOpen(false); }}
      draggable={search.trim() ? false : { nodeDraggable: node => node.key !== '0' && !String(node.key).startsWith('page:') }}
      allowDrop={({ dragNode, dropNode, dropPosition }) => dropPosition !== 0 && dragNode.key !== dropNode.key && byId.has(String(dragNode.key)) && byId.has(String(dropNode.key)) && byId.get(String(dragNode.key))?.parent_id === byId.get(String(dropNode.key))?.parent_id}
      onDrop={onDrop} />
    {search.trim() && !searchResource.loading && !searchResource.error && !visible.length && <Typography.Text>未找到匹配部门</Typography.Text>}
  </div></Card>;
  return <PageHeader title="组织架构" description="浏览部门与当前成员，选择准确范围并维护门店属性。" extra={<Space wrap>
    <Button className="tree-trigger" icon={<MenuOutlined />} onClick={() => setTreeOpen(true)}>选择部门</Button>
    <Typography.Text aria-live="polite">{selection.error ? '选中部门数待核对' : selection.calculating || !tree.ready ? '正在计算选中部门数' : `已选 ${selection.count} 个部门`}</Typography.Text>
    <Button type="primary" loading={openingEditor} disabled={!selection.ready || !selection.count} onClick={() => void openBatch()}>批量设置</Button>
  </Space>}>
    {notice && <Alert type="warning" showIcon title={notice} />}
    {selection.error && <Alert type="error" title={selection.error} action={<Button onClick={retry}>重新计算</Button>} />}
    <div className={`org-grid${treeCollapsed ? ' org-grid-tree-collapsed' : ''}`} ref={grid}>
      <div className="tree-panel">
        <div id="organization-tree-panel" className="org-tree-panel-content" hidden={treeCollapsed}>{treePanel}</div>
        <Button className="org-tree-collapse" style={{ borderColor: token.colorBorderSecondary }} aria-label={treeCollapsed ? '展开部门面板' : '折叠部门面板'}
          title={treeCollapsed ? '展开部门面板' : '折叠部门面板'} aria-expanded={!treeCollapsed} aria-controls="organization-tree-panel"
          icon={treeCollapsed ? <RightOutlined /> : <LeftOutlined />} onClick={() => setTreeCollapsed(value => !value)} />
      </div>
      <div className="org-detail-panel" style={{ '--org-border': token.colorBorderSecondary, '--org-text': token.colorText, '--org-primary': token.colorPrimary } as CSSProperties}>
        <Card className="org-summary-card" styles={{ body: { padding: 0 } }}>
          <section aria-label="部门统计" aria-busy={!companyStats || companySummary.loading}>
            <div className="org-company-summary">{summaryItems.map(([key, title]) => {
              const view = statusViews[key];
              const chosen = Boolean(view && statusView === view.value);
              return <div className={`org-stat-cell${chosen ? ' org-stat-selected' : ''}`} key={key}
                style={chosen ? { background: token.colorSuccessBg, boxShadow: `inset 0 0 0 1px ${token.colorSuccessBorder}` } : undefined}>
                <Statistic title={<span className="org-stat-title">{title}{view && <Tooltip title={chosen ? '恢复本组织默认列表' : `查看全组织${title}人员`}>
                  <Button type="text" size="small" aria-label={`查看${title}人员`} aria-pressed={chosen} disabled={!companyStats || !!companySummary.error}
                    style={{ color: chosen ? token.colorSuccessText : token.colorTextTertiary }} icon={<EyeOutlined />} onClick={() => toggleStatusView(view.value)} />
                </Tooltip>}</span>} value={companyStats?.[key] ?? '—'} loading={companySummary.loading}
                  styles={{ content: { fontSize: token.fontSizeHeading3, color: chosen ? token.colorSuccessText : undefined } }} />
              </div>;
            })}</div>
          </section>
          {companySummary.error && selected !== '0' && <Alert type="error" title={companySummary.error.message} action={<Button onClick={companySummary.error.code === 'DATASET_CHANGED' ? retry : companySummary.reload}>重试</Button>} />}
        </Card>
        <Card className="org-people-card" styles={{ header: { borderBottom: 0 } }} title={<div className="org-members-header">
          <div className="org-department-heading">
            <Typography.Title level={4} className="org-department-name" style={{ margin: 0 }}>{statusView === 'none' ? current?.name ?? '当前部门' : statusViews[`${statusView}_count`].label}</Typography.Title>
            <Typography.Text className="org-member-count" type="secondary" aria-live="polite">共{people.total}人</Typography.Text>
            {statusView === 'none' && current && current.id !== '0' && <Space className="org-department-actions" size={4}>
              <Tooltip title="更新此部门及后代" trigger={['hover', 'focus']}>
                <Button type="text" size="small" aria-label="更新此部门及后代" icon={<SyncOutlined />} loading={syncing} onClick={() => void subtreeSync()} />
              </Tooltip>
              <Tooltip title="编辑门店资料" trigger={['hover', 'focus']}>
                <Button type="text" size="small" aria-label="编辑门店资料" icon={<EditOutlined />} disabled={current.status !== 'active'} onClick={() => setSingleOpen(true)} />
              </Tooltip>
              <Tooltip title="查看部门详情" trigger={['hover', 'focus']}>
                <Button type="text" size="small" aria-label="查看部门详情" icon={<EyeOutlined />} onClick={() => setDepartmentId(current.id)} />
              </Tooltip>
            </Space>}
          </div>
          <Select aria-label="账号状态" value={accountStatus} disabled={statusView !== 'none'} onChange={setAccountStatus} options={accountOptions}
            optionRender={option => <span className="org-account-option"><span>{option.label}</span>{option.value !== 'all' &&
              <Badge count={people.accountCounts[String(option.value)] ?? 0} showZero overflowCount={Number.MAX_SAFE_INTEGER}
                color={accountBadgeColors[String(option.value)]}
                styles={{ indicator: { color: ['unjoin', 'unknown'].includes(String(option.value)) ? token.colorText : undefined } }} />}</span>} />
          <Tooltip title="当前部门人数较多，列表中将只展示部门直属成员，不再展示子部门成员"
            placement="top" destroyOnHidden open={statusView === 'none' && memberScopeOpen && membersLimited && !keyword.trim()} styles={{ root: { maxWidth: 320 } }}>
          <span className="org-member-scope">
          <Select aria-label="展示成员" onOpenChange={setMemberScopeOpen} value={descendants ? 'all' : 'direct'} disabled={!activeSummary || statusView !== 'none'}
            onChange={value => setMemberChoice({ departmentId: selected, descendants: value === 'all' })} options={[
              { label: '部门直属成员', value: 'direct' }, { label: '部门全部成员', value: 'all', disabled: membersLimited }]} />
          </span></Tooltip>
          <Input.Search className="org-member-search" aria-label="搜索人员" allowClear placeholder="搜索姓名、完整手机号或user_id" value={keyword} onChange={event => setKeyword(event.target.value)} />
        </div>}>
          {summary.error && <Alert type="error" title={summary.error.message} action={<Button onClick={summary.error.code === 'DATASET_CHANGED' ? retry : summary.reload}>重试</Button>} />}
          {(people.loading || people.error || people.cursor) && <div className="org-people-feedback">
            {people.loading && <Typography.Text role="status">正在加载人员</Typography.Text>}
            {people.error && <Alert type="error" title={people.error.message} action={<Button onClick={people.error.code === 'DATASET_CHANGED' ? retry : () => void people.more()}>重试</Button>} />}
            {!people.loading && !people.error && people.cursor && <Button size="small" onClick={() => void people.more()}>加载更多人员</Button>}
          </div>}
          <div ref={scroll} className="org-people-scroll" role="region" aria-label="部门人员列表" tabIndex={0}
            style={{ '--org-table-body-height': `${tableBodyHeight}px` } as CSSProperties}>
            <ResourceTable<Employee> rowKey="id" dataSource={people.data} pagination={false} rowHoverable={false} scroll={{ x: compactColumns ? 1592 : 1664, y: tableBodyHeight }} onScroll={event => {
            const element = event.currentTarget; if (element.scrollHeight - element.scrollTop - element.clientHeight < 100 && people.cursor && !people.loading && !people.error) void people.more();
          }} columns={[
              { title: '姓名', dataIndex: 'name', width: compactColumns ? 152 : 208, fixed: 'left', render: (_, row) => <div className="employee-name-cell">
                <EmployeeIdentity name={row.name} avatar={row.avatar_url} onClick={() => setEmployeeId(row.id)} /><CopyUserId employee={row} /></div> },
              { title: '账号状态', width: 160, render: (_, row) => <EmployeeAccountStatus employee={row} /> },
              { title: '手机号码', width: 180, render: (_, row) => <EmployeeValue value={contactLabel(row, 'mobile')} /> },
              { title: '直属上级', width: 180, render: (_, row) => <EmployeeIdentity name={row.leader_name ?? row.leader_user_id} avatar={row.leader_avatar_url} /> },
              { title: '部门', width: 216, render: (_, row) => <EmployeeDepartments employee={row} /> },
              { title: '人员类型', width: 140, render: (_, row) => <EmployeeValue value={row.employee_type_name || row.employee_type_id} /> },
              { title: '职务', width: 140, render: (_, row) => <EmployeeValue value={row.job_title} /> },
              { title: '门店属性', width: 160, render: (_, row) => <EmployeeValue value={row.store_attribute_name || row.store_attribute_id} /> },
              { title: '权限角色', width: 160, render: (_, row) => <EmployeeValue value={row.permission_role_name || row.permission_role_id} /> },
              { title: '操作', width: compactColumns ? 104 : 120, fixed: 'right', render: (_, row) => <Button type="link" onClick={() => setEmployeeId(row.id)}>查看详情</Button> },
            ]} />
          </div>
        </Card>
      </div></div>
    <EmployeeDetailDrawer employeeId={employeeId} onClose={() => setEmployeeId(undefined)} />
    <DepartmentDetailDrawer departmentId={departmentId} onClose={() => setDepartmentId(undefined)} />
    <Drawer className="tree-drawer" title="选择部门" placement="left" size={360} open={treeOpen} onClose={() => setTreeOpen(false)}>{treePanel}</Drawer>
    <OrganizationStoreEditor initial={editor} open={editorOpen} ready={tree.ready} onClose={() => setEditorOpen(false)} onConflict={recover}
      onRecheck={selection.details} onSaved={() => { tree.reload(); people.reload(); }} />
    <StoreEditor departments={current ? [current] : []} dataVersion={tree.meta.data_version} open={singleOpen}
      onClose={() => setSingleOpen(false)} onConflict={recover} onSaved={() => tree.reload()} />
  </PageHeader>;
}
export default OrganizationPage;
