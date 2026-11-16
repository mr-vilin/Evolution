import { useEffect, useId, useMemo, useRef, useState, type Key } from 'react';
import { App, Avatar, Button, Dropdown, Form, Input, InputNumber, Modal, Progress, Select, Table, Tag, Tooltip } from 'antd';
import type { TableColumnsType, TableProps } from 'antd';
import type { FilterValue, SortOrder } from 'antd/es/table/interface';
import { CopyOutlined, DeleteOutlined, EditOutlined, EyeOutlined, MoreOutlined, PlusOutlined, ReloadOutlined, SendOutlined } from '@ant-design/icons';
import { compareNumbers, compareTimes, demoRecords, displayValue, filterFields, personInitial, statusColors, type DemoRecord, type FilterField } from './tableStandardsModel';

type Filters = Partial<Record<FilterField, FilterValue | null>>;
type SortState = { key: string | null; order: SortOrder };
type EditValues = { name: string; quantity: number | null };

function useBodyHeight(ref: React.RefObject<HTMLDivElement | null>, maxHeight: number) {
  const [height, setHeight] = useState(240);
  useEffect(() => {
    const shell = ref.current;
    if (!shell) return;
    let frame = 0;
    const measure = () => {
      const top = shell.querySelector<HTMLElement>('.table-demo-top');
      const header = shell.querySelector<HTMLElement>('.ant-table-header');
      const pagination = shell.querySelector<HTMLElement>('.ant-pagination');
      const body = shell.querySelector<HTMLElement>('.ant-table-body');
      const paginationStyle = pagination ? getComputedStyle(pagination) : null;
      const paginationHeight = pagination ? pagination.offsetHeight + parseFloat(paginationStyle!.marginTop) + parseFloat(paginationStyle!.marginBottom) : 0;
      const scrollbar = body ? Math.max(0, body.offsetHeight - body.clientHeight) : 0;
      setHeight(Math.max(1, Math.floor(maxHeight - (top?.offsetHeight ?? 0) - (header?.offsetHeight ?? 40) - paginationHeight - scrollbar - 2)));
    };
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    const observer = new ResizeObserver(schedule);
    observer.observe(shell);
    for (const element of shell.querySelectorAll('.table-demo-top, .ant-table-header, .ant-pagination')) observer.observe(element);
    window.addEventListener('resize', schedule);
    measure();
    return () => { observer.disconnect(); cancelAnimationFrame(frame); window.removeEventListener('resize', schedule); };
  }, [maxHeight, ref]);
  return height;
}

export default function TableDemo({ showCreate = true, maxHeight = 520, recordLimit, compact = false }: {
  showCreate?: boolean; maxHeight?: number; recordLimit?: number; compact?: boolean;
}) {
  const { message, modal } = App.useApp();
  const instanceId = useId();
  const shellRef = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(compact);
  const nextId = useRef(1);
  const [records, setRecords] = useState(demoRecords);
  const [filters, setFilters] = useState<Filters>({});
  const [sort, setSort] = useState<SortState>({ key: null, order: null });
  const [keyword, setKeyword] = useState('');
  const [draftKeyword, setDraftKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [editing, setEditing] = useState<DemoRecord | 'new' | null>(null);
  const [form] = Form.useForm<EditValues>();
  const bodyHeight = useBodyHeight(shellRef, maxHeight);
  useEffect(() => {
    const shell = shellRef.current!;
    const measure = () => setNarrow(compact || shell.clientWidth < 640);
    const observer = new ResizeObserver(measure);
    observer.observe(shell); measure();
    return () => observer.disconnect();
  }, [compact]);
  const base = useMemo(() => recordLimit == null ? records : records.slice(0, recordLimit), [records, recordLimit]);
  const matchesKeyword = (row: DemoRecord) => [row.name, row.owner].some(value => value.toLocaleLowerCase().includes(keyword.toLocaleLowerCase()));
  const matchesFilters = (row: DemoRecord) => filterFields.every(([key]) => !filters[key]?.length || filters[key]!.includes(row[key]));
  const dataSource = base.filter(matchesKeyword);
  const resultCount = dataSource.filter(matchesFilters).length;
  const current = Math.min(page, Math.max(1, Math.ceil(resultCount / pageSize)));

  function updateFilter(key: FilterField, values: string[]) {
    setFilters(previous => ({ ...previous, [key]: values.length ? values : null }));
    setPage(1);
  }
  function search(value: string) { setKeyword(value.trim()); setPage(1); }
  async function copyId(row: DemoRecord) {
    try {
      await navigator.clipboard.writeText(row.id);
      message.success('已复制 ID');
    } catch {
      modal.info({ title: '复制失败，请手动复制 ID', content: <p className="table-manual-id">{row.id}</p>, okText: '关闭' });
    }
  }
  function edit(row: DemoRecord | 'new') {
    form.resetFields();
    form.setFieldsValue(row === 'new' ? { name: '', quantity: 0 } : { name: row.name, quantity: row.quantity });
    setEditing(row);
  }
  function save(values: EditValues) {
    if (editing === 'new') {
      const row: DemoRecord = {
        ...demoRecords[0], id: `demo-local-${nextId.current++}`, name: values.name.trim(), quantity: values.quantity ?? null,
        status: '未开始', progress: 0, source: '手动录入', createdAt: null, updatedAt: null,
      };
      setRecords(previous => [row, ...previous]);
      setPage(1);
      message.success(matchesKeyword(row) && matchesFilters(row)
        ? '已新增本地示例记录；当前查询条件仍然保留'
        : '已新增本地示例记录；记录不符合当前查询条件，暂不显示');
    } else if (editing) {
      setRecords(previous => previous.map(row => row.id === editing.id ? { ...row, name: values.name.trim(), quantity: values.quantity ?? null } : row));
      message.success('已更新本地示例记录');
    }
    setEditing(null);
  }
  function remove(row: DemoRecord) {
    modal.confirm({ title: `删除“${row.name}”？`, content: '仅删除当前演示中的本地记录。', okText: '删除', cancelText: '取消', okButtonProps: { danger: true },
      onOk: () => { setRecords(previous => previous.filter(item => item.id !== row.id)); message.success('已删除本地示例记录'); },
    });
  }
  const filterColumn = (key: FilterField) => ({
    filteredValue: filters[key]?.length ? filters[key]! : null,
    onFilter: (value: Key | boolean, row: DemoRecord) => row[key] === value,
    // 主要四项只在工具栏出现，其余条件使用对应表头。
    ...(key === 'department' || key === 'priority' ? {
      filters: [...new Set(demoRecords.map(row => row[key]))].map(value => ({ text: value, value })), filterOnClose: false,
    } : {}),
  });
  const sortableColumn = (key: 'quantity' | 'progress' | 'createdAt' | 'updatedAt') => ({
    sortOrder: sort.key === key ? sort.order : null,
    sorter: (a: DemoRecord, b: DemoRecord, order?: SortOrder) => {
      const comparison = key === 'quantity' || key === 'progress'
        ? compareNumbers(a[key], b[key], order)
        : compareTimes(a[key], b[key], order);
      // 同值在升降序均按完整数据源中的基准顺序排列。
      return comparison || (base.indexOf(a) - base.indexOf(b)) * (order === 'descend' ? -1 : 1);
    },
  });
  const columns: TableColumnsType<DemoRecord> = [
    { key: 'name', title: '名称', dataIndex: 'name', width: narrow ? 104 : 208, fixed: 'left',
      render: (_value, row) => <div className="table-record-name"><Tooltip title={row.name} trigger={['hover', 'focus']}><span tabIndex={0} className="table-name-text">{row.name}</span></Tooltip><Tooltip title="复制 ID" trigger={['hover', 'focus']}><Button type="text" size="small" aria-label={`复制 ID：${row.name}`} icon={<CopyOutlined />} onClick={() => void copyId(row)} /></Tooltip></div> },
    { key: 'status', title: '状态', dataIndex: 'status', width: 112, ...filterColumn('status'), render: (value: keyof typeof statusColors) => <Tag color={statusColors[value]}>{value}</Tag> },
    ...filterFields.filter(([key]) => key !== 'status').map(([key, title]) => ({ key, title, dataIndex: key, width: key === 'owner' ? 144 : 112, ...filterColumn(key), render: key === 'owner' ? (name: string, row: DemoRecord) => <span className="table-person"><Avatar size={24} src={row.ownerAvatar}>{personInitial(name)}</Avatar><span>{name}</span></span> : displayValue })),
    { key: 'quantity', title: '数量', dataIndex: 'quantity', width: 100, ...sortableColumn('quantity'), render: displayValue },
    { key: 'progress', title: '进度', dataIndex: 'progress', width: 156, ...sortableColumn('progress'), render: (value: number | null) => value == null ? '-' : <Progress percent={value} size="small" /> },
    { key: 'createdAt', className: 'table-time', title: '创建时间', dataIndex: 'createdAt', width: 184, ...sortableColumn('createdAt'), render: displayValue },
    { key: 'updatedAt', className: 'table-time', title: '更新时间', dataIndex: 'updatedAt', width: 184, ...sortableColumn('updatedAt'), render: displayValue },
    { key: 'actions', title: '操作', width: narrow ? 96 : 120, fixed: 'right', render: (_value, row) => <div className="table-row-actions">
      <Tooltip title="查看" trigger={['hover', 'focus']}><Button type="text" size="small" aria-label={`查看：${row.name}`} icon={<EyeOutlined />} onClick={() => modal.info({ title: row.name, content: <p>负责人：{row.owner}；状态：{row.status}；数量：{displayValue(row.quantity)}。本地演示记录，时间按北京时间展示。</p>, okText: '关闭' })} /></Tooltip>
      <Tooltip title="编辑" trigger={['hover', 'focus']}><Button type="text" size="small" aria-label={`编辑：${row.name}`} icon={<EditOutlined />} onClick={() => edit(row)} /></Tooltip>
      <Dropdown trigger={['click']} menu={{ items: [
        { key: 'resend', label: '重发', icon: <SendOutlined /> }, { key: 'delete', label: '删除', icon: <DeleteOutlined />, danger: true },
      ], onClick: ({ key }) => key === 'delete' ? remove(row) : message.success(`已模拟重发“${row.name}”`) }}><Tooltip title="更多操作" trigger={['hover', 'focus']}><Button type="text" size="small" aria-label={`更多操作：${row.name}`} icon={<MoreOutlined />} /></Tooltip></Dropdown>
    </div> },
  ];
  const onChange: TableProps<DemoRecord>['onChange'] = (pagination, nextFilters, sorter, extra) => {
    if (extra.action === 'filter') {
      // antd 回传无 filters 菜单列时会给出空数组；工具栏字段仍以同源状态为准。
      setFilters(previous => ({ ...previous, ...Object.fromEntries(filterFields
        .filter(([key]) => key === 'department' || key === 'priority')
        .map(([key]) => [key, nextFilters[key]?.length ? nextFilters[key] : null])) })); setPage(1);
    } else if (extra.action === 'sort') {
      const single = Array.isArray(sorter) ? sorter[0] : sorter;
      setSort({ key: single.order ? String(single.columnKey) : null, order: single.order ?? null }); setPage(1);
    } else { setPage(pagination.current ?? 1); setPageSize(pagination.pageSize ?? 10); }
  };
  const searchControl = <Input.Search className="table-search" aria-label="搜索名称或负责人" placeholder="搜索名称或负责人" value={draftKeyword} allowClear onChange={event => { setDraftKeyword(event.target.value); if (!event.target.value) search(''); }} onSearch={search} />;
  const refresh = <Tooltip title="刷新本地示例" trigger={['hover', 'focus']}><Button aria-label="刷新" icon={<ReloadOutlined />} onClick={() => { setPage(current); message.success('已刷新本地示例，保留当前查询状态'); }} /></Tooltip>;
  return <div className="table-demo">
    <div ref={shellRef} className={`table-demo-shell${narrow ? ' is-narrow' : ''}`} data-testid="table-demo-shell">
      <div className="table-demo-top"><h3>本地任务列表</h3><div className="table-demo-toolbar">
        <div className="table-toolbar-left">
          <div className="table-toolbar-filters">{filterFields.slice(0, 4).map(([key, label]) => <Select className="table-main-filter" key={key} id={`${instanceId}-${key}`} aria-label={label} mode="multiple" maxTagCount="responsive" placeholder={`全部${label}`} value={(filters[key] ?? []) as string[]} allowClear options={[...new Set(demoRecords.map(row => row[key]))].map(value => ({ value, label: value }))} onChange={values => updateFilter(key, values)} />)}</div>
          <div className="table-toolbar-actions">{showCreate && <Button type="primary" icon={<PlusOutlined />} onClick={() => edit('new')}>新增</Button>}{refresh}</div>
        </div>
        <div className="table-toolbar-right">{searchControl}</div>
      </div></div>
      <Table<DemoRecord> rowKey="id" size="small" columns={columns} dataSource={dataSource} onChange={onChange} scroll={{ x: narrow ? 1480 : 1624, y: bodyHeight }} pagination={{ current, pageSize, showSizeChanger: true, pageSizeOptions: [5, 10, 20], showTotal: total => `共 ${total} 条`, size: 'small' }} />
    </div>
    <Modal className="table-demo-modal" title={editing === 'new' ? '新增本地示例记录' : '编辑本地示例记录'} open={editing !== null} onCancel={() => setEditing(null)} onOk={() => form.submit()} okText="保存" cancelText="取消">
      <Form form={form} layout="vertical" onFinish={save}><Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true, message: '请输入名称' }, { max: 100, message: '名称最多 100 个字符' }]}><Input maxLength={100} /></Form.Item><Form.Item name="quantity" label="数量" rules={[{ type: 'number', min: 0, message: '数量应为非负数' }]}><InputNumber min={0} precision={0} /></Form.Item><p className="table-form-help">仅操作本地示例，不写入业务系统。未产生的业务时间显示 -。</p></Form>
    </Modal>
  </div>;
}
