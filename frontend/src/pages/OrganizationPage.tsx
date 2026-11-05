import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Checkbox, Drawer, Input, Radio, Select, Space, Tag, Tree, Typography } from 'antd';
import { DownOutlined, EditOutlined, MenuOutlined, RightOutlined, SyncOutlined, UserOutlined } from '@ant-design/icons';
import { useNavigate } from '@umijs/max';
import type { DataNode } from 'antd/es/tree';
import type { TreeProps } from 'antd';
import type { Department, Employee } from '../domain';
import { primaryStoreLabel } from '../domain';
import { ApiError, type Meta, query, request } from '../services/http';
import { useResource } from '../services/useResource';
import { datasetQuery, useOrganizationPeople, useOrganizationTree } from '../services/useOrganization';
import { rangeLabel, useOrganizationSelection } from '../services/useOrganizationSelection';
import { PageHeader } from '../components/PageHeader';
import { ResourceTable } from '../components/ResourceTable';
import { OrganizationStoreEditor } from '../components/OrganizationStoreEditor';
import { StoreEditor } from '../components/StoreEditor';

const ROOT: Department = { id: '0', parent_id: null, name: '组织', path: ['组织'], status: 'active', is_virtual_root: true, is_store: false, store_code: null, notes: null, has_children: true };
function accountLabel(row: Employee) {
  const flags = row.account_status ?? {};
  const labels = [flags.is_activated === true ? '已激活' : flags.is_activated === false ? '未激活' : '',
    flags.is_frozen === true ? '已暂停' : '', flags.is_unjoin === true ? '未加入' : '',
    flags.is_resigned === true ? '已离职' : '', flags.is_exited === true ? '已退出' : ''].filter(Boolean);
  if (['is_activated', 'is_frozen', 'is_unjoin', 'is_resigned', 'is_exited'].some(key => flags[key as keyof typeof flags] == null)) labels.push('状态未知');
  return labels.join('、') || '状态未知';
}
function mobileLabel(row: Employee) {
  const readability = row.field_readability?.mobile;
  return readability === 'readable' ? row.mobile || '未填写' : readability === 'unreadable' ? '未知（不可读）' : '未知（未采集）';
}
export function OrganizationPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [includeInactive, setIncludeInactive] = useState(false);
  const tree = useOrganizationTree(includeInactive);
  const [selected, setSelected] = useState<string>();
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<string[]>(['0']);
  const [descendants, setDescendants] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [accountStatus, setAccountStatus] = useState('all');
  const [treeOpen, setTreeOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [editor, setEditor] = useState<{ departments: Department[]; meta: Meta } | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [singleOpen, setSingleOpen] = useState(false);
  const [openingEditor, setOpeningEditor] = useState(false);
  const [notice, setNotice] = useState('');
  const retries = useRef(0);
  const recover = useCallback(() => { setNotice('数据已变化，已保留原选择和编辑草稿，请核对实际目标。'); tree.reload(); }, [tree.reload]);
  const selection = useOrganizationSelection(tree.meta, recover);
  const searchResource = useResource<Department[]>(search.trim() && tree.ready
    ? '/admin/api/organization/search' + query({ keyword: search.trim(), include_inactive: includeInactive, ...datasetQuery(tree.meta) }) : null);
  const people = useOrganizationPeople(selected, descendants, keyword, accountStatus, tree.meta);
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = 0; }, [people.path]);
  const versionError = people.error?.code === 'DATASET_CHANGED' || searchResource.error?.code === 'DATASET_CHANGED'
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
  const current = [...tree.nodes, ...(searchResource.data ?? []), ...(editor?.departments ?? [])].find(row => row.id === selected);
  const hits = new Set((searchResource.meta.matched_ids as string[] | undefined) ?? []);
  function retry() { retries.current = 0; tree.reload(); }
  function expand(id: string) {
    setExpanded(value => value.includes(id) ? value.filter(key => key !== id) : [...value, id]);
    if (!tree.branches[id]?.loaded && !tree.branches[id]?.loading) void tree.load(id);
  }
  const byId = new Map(visible.map(row => [row.id, row]));
  const nodes = new Map<string, DataNode>();
  for (const department of [ROOT, ...visible.filter(row => row.id !== '0')]) {
    const state = selection.states[department.id];
    nodes.set(department.id, { key: department.id, isLeaf: department.id !== '0' && !department.has_children, children: [], title: <Space size={4} wrap>
      <span onClick={event => event.stopPropagation()}><Checkbox aria-label={`选择${department.name}`}
        disabled={department.status !== 'active' || !selection.ready || openingEditor}
        checked={department.id === '0' ? state?.descendants === 'all' : Boolean(state?.self_selected)}
        indeterminate={department.id === '0' ? state?.descendants === 'partial' : !state?.self_selected && !!state && state.descendants !== 'none'}
        onChange={() => void selection.toggle(department.id)} /></span>
      <span className={hits.has(department.id) ? 'tree-hit' : ''}>{department.name}</span>
      {department.status !== 'active' && <Tag>失效</Tag>}{department.is_store && <Tag color="blue">门店</Tag>}
      {department.id !== '0' && <Typography.Text type="secondary">{rangeLabel(state)}</Typography.Text>}
      {department.id !== '0' && department.has_children && !search.trim() && <Button type="text" size="small"
        aria-label={`${expanded.includes(department.id) ? '收起' : '展开'}${department.name}`}
        icon={expanded.includes(department.id) ? <DownOutlined /> : <RightOutlined />}
        onClick={event => { event.stopPropagation(); expand(department.id); }} />}
    </Space> });
  }
  for (const department of visible) if (department.id !== '0') (nodes.get(department.parent_id ?? '0') ?? nodes.get('0'))!.children!.push(nodes.get(department.id)!);
  for (const [id, node] of nodes) {
    node.children?.sort((a, b) => (byId.get(String(a.key))?.sort_order ?? 0) - (byId.get(String(b.key))?.sort_order ?? 0) || String(a.key).localeCompare(String(b.key)));
    const branch = tree.branches[id];
    if (!search.trim() && (branch?.loading || branch?.cursor || branch?.error)) node.children?.push({ key: `page:${id}`, selectable: false, isLeaf: true,
      title: <Button type="link" loading={branch.loading} onClick={event => { event.stopPropagation(); void tree.load(id, Boolean(branch.cursor)); }}>
        {branch.error ? `重试加载${id === '0' ? '组织' : byId.get(id)?.name ?? '部门'}` : branch.loading ? '正在加载' : '加载更多部门'}</Button> });
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
    try { const result = await request<{ job_id: string; reused?: boolean }>('/admin/api/sync/jobs', { method: 'POST', body: { type: 'subtree', root_department_id: selected } }); message.success(result.data.reused ? `复用任务 #${result.data.job_id}` : `已创建任务 #${result.data.job_id}`); navigate(`/sync?job=${encodeURIComponent(result.data.job_id)}`); }
    catch (reason) { message.error(reason instanceof Error ? reason.message : '创建任务失败'); }
    finally { setSyncing(false); }
  }
  const treePanel = <Card title="部门树"><Space orientation="vertical" style={{ width: '100%' }}>
    <Input.Search allowClear placeholder="搜索部门名称" value={search} onChange={event => setSearch(event.target.value)} />
    <Checkbox checked={includeInactive} onChange={event => setIncludeInactive(event.target.checked)}>显示失效部门</Checkbox>
    {searchResource.loading && <Typography.Text>正在搜索</Typography.Text>}
    {searchResource.error && <Alert type="error" title={searchResource.error.message} action={<Button onClick={retry}>重试</Button>} />}
    {tree.branches['0']?.error && <Alert type="error" title={tree.branches['0'].error.message} action={<Button onClick={retry}>重试</Button>} />}
    <Tree className="org-tree" blockNode showLine treeData={[nodes.get('0')!]} expandedKeys={search.trim() ? ['0', ...visible.map(row => row.id)] : expanded}
      onExpand={(keys, info) => { if (search.trim()) return; setExpanded(keys.map(String)); if (info.expanded && !tree.branches[String(info.node.key)]?.loaded) void tree.load(String(info.node.key)); }}
      selectedKeys={selected ? [selected] : []} onSelect={keys => { setSelected(keys[0] ? String(keys[0]) : undefined); setTreeOpen(false); }}
      draggable={search.trim() ? false : { nodeDraggable: node => node.key !== '0' && !String(node.key).startsWith('page:') }}
      allowDrop={({ dragNode, dropNode, dropPosition }) => dropPosition !== 0 && dragNode.key !== dropNode.key && byId.has(String(dragNode.key)) && byId.has(String(dropNode.key)) && byId.get(String(dragNode.key))?.parent_id === byId.get(String(dropNode.key))?.parent_id}
      onDrop={onDrop} />
    {search.trim() && !searchResource.loading && !searchResource.error && !visible.length && <Typography.Text>未找到匹配部门</Typography.Text>}
  </Space></Card>;
  return <PageHeader title="组织架构" description="浏览部门与当前成员，选择准确范围并维护门店属性。" extra={<Space wrap>
    <Button className="tree-trigger" icon={<MenuOutlined />} onClick={() => setTreeOpen(true)}>选择部门</Button>
    <Typography.Text aria-live="polite">{selection.error ? '选中部门数待核对' : selection.calculating || !tree.ready ? '正在计算选中部门数' : `已选 ${selection.count} 个部门`}</Typography.Text>
    <Button type="primary" loading={openingEditor} disabled={!selection.ready || !selection.count} onClick={() => void openBatch()}>批量设置</Button>
  </Space>}>
    {notice && <Alert type="warning" showIcon title={notice} />}
    {selection.error && <Alert type="error" title={selection.error} action={<Button onClick={retry}>重新计算</Button>} />}
    <div className="org-grid"><div className="tree-panel">{treePanel}</div>
      <Card title={selected && selected !== '0' ? current?.name ?? '当前部门' : '请选择部门'} extra={current && current.id !== '0' && <Space>
        <Button icon={<SyncOutlined />} loading={syncing} onClick={() => void subtreeSync()}>更新此部门及后代</Button>
        <Button icon={<EditOutlined />} disabled={current.status !== 'active'} onClick={() => setSingleOpen(true)}>编辑门店资料</Button></Space>}>
        {!selected || selected === '0' ? <Typography.Text type="secondary">选择部门以查看人员。</Typography.Text> : <>
          <Space className="toolbar" wrap><Radio.Group value={descendants} onChange={event => setDescendants(event.target.value)} options={[{ label: '部门直属成员', value: false }, { label: '部门全部成员', value: true }]} />
            <Input.Search allowClear placeholder="搜索姓名、完整手机号或 USER_ID" value={keyword} onChange={event => setKeyword(event.target.value)} />
            <Select aria-label="账号状态" value={accountStatus} onChange={setAccountStatus} style={{ minWidth: 140 }} options={[
              { label: '全部账号状态', value: 'all' }, { label: '已激活', value: 'activated' }, { label: '未激活', value: 'unactivated' },
              { label: '已暂停', value: 'frozen' }, { label: '未加入', value: 'unjoin' }, { label: '状态未知', value: 'unknown' }]} />
          </Space><Typography.Paragraph aria-live="polite">共 {people.total} 人，已加载 {people.data.length} 人</Typography.Paragraph>
          <div ref={scroll} role="region" aria-label="部门人员列表" style={{ maxHeight: '65vh', overflow: 'auto' }} onScroll={event => {
            const element = event.currentTarget; if (element.scrollHeight - element.scrollTop - element.clientHeight < 100 && people.cursor && !people.loading && !people.error) void people.more();
          }}><ResourceTable<Employee> rowKey="id" dataSource={people.data} pagination={false} scroll={{ x: 720 }} columns={[
              { title: '姓名', dataIndex: 'name', render: (name, row) => <Button type="link" icon={<UserOutlined />} onClick={() => navigate(`/employees/${encodeURIComponent(row.id)}`)}>{name}</Button> },
              { title: 'USER_ID', render: (_, row) => row.user_id ?? row.id }, { title: '手机号', render: (_, row) => mobileLabel(row) },
              { title: '账号状态', render: (_, row) => accountLabel(row) }, { title: '主门店状态', dataIndex: 'primary_store_status', render: primaryStoreLabel },
            ]} />
            {people.loading && <Typography.Paragraph role="status">正在加载人员</Typography.Paragraph>}
            {people.error && <Alert type="error" title={people.error.message} action={<Button onClick={people.error.code === 'DATASET_CHANGED' ? retry : () => void people.more()}>重试</Button>} />}
            {!people.loading && !people.error && (people.cursor ? <Button onClick={() => void people.more()}>加载更多人员</Button> : <Typography.Paragraph type="secondary">没有更多人员</Typography.Paragraph>)}
          </div></>}
      </Card></div>
    <Drawer className="tree-drawer" title="选择部门" placement="left" size={360} open={treeOpen} onClose={() => setTreeOpen(false)}>{treePanel}</Drawer>
    <OrganizationStoreEditor initial={editor} open={editorOpen} ready={tree.ready} onClose={() => setEditorOpen(false)} onConflict={recover}
      onRecheck={selection.details} onSaved={() => { tree.reload(); people.reload(); }} />
    <StoreEditor departments={current ? [current] : []} dataVersion={tree.meta.data_version} open={singleOpen}
      onClose={() => setSingleOpen(false)} onConflict={recover} onSaved={() => tree.reload()} />
  </PageHeader>;
}
export default OrganizationPage;
