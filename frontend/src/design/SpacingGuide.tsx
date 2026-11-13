import { useState, type CSSProperties, type ReactNode } from 'react';
import { Button, Input, Select } from 'antd';
import reference from './reference.json';
import './spacing-guide.css';

const spacing = reference.data.spacing;
const unit = parseFloat(spacing.unit);
const sizes = { xs: parseFloat(spacing.xs), sm: parseFloat(spacing.sm), md: parseFloat(spacing.md), lg: parseFloat(spacing.lg), xl: parseFloat(spacing.xl) };
export const spacingScaleCount = new Set(Object.values(sizes)).size;
const exampleMembers = [
  { name: '林晓', department: 'engineering', departmentName: '研发部' },
  { name: '陈晨', department: 'engineering', departmentName: '研发部' },
  { name: '周宁', department: 'product', departmentName: '产品部' },
];

function SpacingGap({ size, vertical = false }: { size: number; vertical?: boolean }) {
  return <span className={`spacing-gap is-${vertical ? 'vertical' : 'horizontal'}`} style={{ '--measured-space': `${size}px` } as CSSProperties} role="img" aria-label={`${vertical ? '纵向' : '横向'}间距 ${size}px`}>
    <span className="spacing-dimension" aria-hidden="true"><span>{size}px</span></span>
  </span>;
}

function SpacingStat({ label, value }: { label: string; value: string }) {
  return <div className="spacing-stat"><span>{label}</span><strong>{value}</strong></div>;
}

function SpacingInset({ size, children }: { size: number; children: ReactNode }) {
  return <div className="spacing-inset" style={{ padding: size }}>
    <span className="spacing-inset-ruler" style={{ height: size }} role="img" aria-label={`容器四周内边距 ${size}px`}><span>{size}px</span></span>
    <div className="spacing-paper">{children}</div>
  </div>;
}

function SpacingComposition() {
  const [name, setName] = useState('');
  const [department, setDepartment] = useState('all');
  const [filters, setFilters] = useState({ name: '', department: 'all' });
  const members = exampleMembers.filter(member => member.name.includes(filters.name) && (filters.department === 'all' || member.department === filters.department));
  function reset() { setName(''); setDepartment('all'); setFilters({ name: '', department: 'all' }); }
  return <div className="spacing-composition-grid">
    <div className="spacing-grid spacing-composition-stage">
      <SpacingInset size={sizes.lg}>
        <div className="spacing-inline"><h4>组织概览</h4><SpacingGap size={sizes.xs} /><span className="spacing-caption">共 3 人</span></div>
        <SpacingGap size={sizes.md} vertical />
        <div className="spacing-inline spacing-stats"><SpacingStat label="示例成员" value="3" /><SpacingGap size={sizes.md} /><SpacingStat label="所属部门" value="2" /></div>
        <SpacingGap size={sizes.xl} vertical />
        <form onSubmit={event => { event.preventDefault(); setFilters({ name: name.trim(), department }); }}>
          <h4>成员查询</h4>
          <SpacingGap size={sizes.md} vertical />
          <div className="spacing-fields">
            <label htmlFor="spacing-member-name">姓名<Input id="spacing-member-name" value={name} onChange={event => setName(event.target.value)} placeholder="输入示例姓名" /></label>
            <label htmlFor="spacing-member-department">部门<Select id="spacing-member-department" value={department} onChange={setDepartment} options={[{ value: 'all', label: '全部部门' }, { value: 'engineering', label: '研发部' }, { value: 'product', label: '产品部' }]} /></label>
          </div>
          <SpacingGap size={sizes.md} vertical />
          <div className="spacing-inline"><Button htmlType="submit" type="primary">查询</Button><SpacingGap size={sizes.sm} /><Button onClick={reset}>重置</Button></div>
        </form>
        <SpacingGap size={sizes.md} vertical />
        <div className="spacing-results" role="status" aria-live="polite"><span className="spacing-caption">显示 {members.length} 位示例成员</span>{members.length ? <ul>{members.map(member => <li key={member.name}><span>{member.name}</span><span className="spacing-caption">{member.departmentName}</span></li>)}</ul> : <p>暂无匹配的示例成员</p>}</div>
      </SpacingInset>
    </div>
    <div className="spacing-combination-rules"><h4>组合时这样选</h4><ul>
      <li><strong>4px</strong>：标题与人数等紧密附属信息。</li>
      <li><strong>8px</strong>：同一组查询、重置按钮。</li>
      <li><strong>16px</strong>：并列统计卡、字段组、内容组与操作区之间。</li>
      <li><strong>24px</strong>：常规内容容器的四周内边距。</li>
      <li><strong>32px</strong>：概览与查询两个独立区域之间。</li>
    </ul><p>关系紧密的内容靠近，同一组内容保持一致的节奏；独立区域使用更大的留白。</p><p className="spacing-caption">此处为本地示例数据，可输入「林晓」或按部门查询，体验实际控件之间的间距。</p></div>
  </div>;
}

export default function SpacingGuide() {
  const applications = [
    { size: sizes.xs, token: 'unit / xs', name: '文字与紧密附属信息', usage: '标题与人数、名称与补充信息等紧密关联的内容。小间距让它们被读作同一组。', caption: '部门名称与人数之间留 4px。',
      sample: <div className="spacing-inline"><strong>研发部</strong><SpacingGap size={sizes.xs} /><span className="spacing-caption">共 20 人</span></div> },
    { size: sizes.sm, token: 'sm', name: '同行控件与轻量分组', usage: '同一操作组中的相邻按钮，例如查询与重置、保存与取消。组内保持紧凑，表达它们属于同一次操作。', caption: '同一组按钮之间留 8px。',
      sample: <div className="spacing-inline"><Button type="primary">查询</Button><SpacingGap size={sizes.sm} /><Button>重置</Button></div> },
    { size: sizes.md, token: 'md', name: '卡片栅格 / 内容间隔 / 小卡片内边距', usage: '并列的小型统计卡或摘要卡、同一模块中的内容组和字段组，以及紧凑小卡片内部。内容需要分组，同时仍属于同一阅读区域时使用。', caption: '统计卡之间、紧凑卡片四周内边距与内容组间隔均为 16px。',
      sample: <div className="spacing-samples"><div className="spacing-inline spacing-stats"><SpacingStat label="成员总数" value="20" /><SpacingGap size={sizes.md} /><SpacingStat label="部门数量" value="4" /></div><SpacingInset size={sizes.md}><h5>成员资料</h5><SpacingGap size={sizes.md} vertical /><p>林晓 · 研发部</p></SpacingInset></div> },
    { size: sizes.lg, token: 'lg', name: '章节与桌面页面内边距', usage: '相关章节之间、桌面内容区四周，以及常规卡片的内部留白。紧凑小卡可用 16px，常规卡片采用 24px。', caption: '常规卡片四周内边距与两个章节之间均为 24px。',
      sample: <SpacingInset size={sizes.lg}><h5>部门信息</h5><p className="spacing-caption">研发部 · 成员与组织资料</p><SpacingGap size={sizes.lg} vertical /><h5>负责人信息</h5><p className="spacing-caption">林晓</p></SpacingInset> },
    { size: sizes.xl, token: 'xl / control-height', name: '独立区域间距 / 标准控件高度', usage: '组织概览与成员管理等相对独立的内容区域之间，用 32px 留白建立区域层级。标准按钮、输入框与选择器的默认高度也为 32px；间距表示元素之间的空白，控件高度表示元素本身的尺寸。', caption: '两个独立内容区域之间留 32px；下方按钮自身高度为 32px。',
      sample: <div className="spacing-samples"><div className="spacing-regions"><div className="spacing-region"><h5>组织概览</h5></div><SpacingGap size={sizes.xl} vertical /><div className="spacing-region"><h5>成员管理</h5></div></div><div className="spacing-height-example"><span className="spacing-caption">标准控件高度 · control-height</span><div className="spacing-height-control"><Button style={{ height: spacing['control-height'] }}>默认按钮</Button><span className="spacing-height-ruler" role="img" aria-label={`按钮高度 ${spacing['control-height']}`}><span>{spacing['control-height']}</span></span></div></div></div> },
  ];
  const style = { '--spacing-unit': spacing.unit, '--spacing-sm': spacing.sm, '--spacing-md': spacing.md, '--spacing-lg': spacing.lg, '--spacing-control-height': spacing['control-height'] } as CSSProperties;
  return <div className="panel spacing-guide" style={style}>
    <div className="spacing-intro"><h3>按内容关系选择间距</h3><p>以 4px 为基础单位，紧密信息、同组内容、独立区域逐级增加留白。下方同时展示尺寸、使用场景与实际案例；浅色区域表示正在测量的空白，每一小格为 4px。</p><p>整体密度由主题的 sizeUnit、sizeStep 与控件尺寸共同协调。需要紧凑界面时，可评估 compactAlgorithm，也可与浅色或深色算法组合；本页仍按既定刻度展示，调整时需同步核对留白、控件高度与 4px 网格。</p></div>
    <div>{applications.map(item => <article className="spacing-application" key={item.size}>
      <div className="spacing-standard"><strong>{item.size}px</strong><code>{item.token}</code><div className="space-track" aria-hidden="true"><div className="space-bar" style={{ width: item.size }} /></div><span>{item.size / unit} 格 × 4px</span></div>
      <div className="spacing-usage"><h4>{item.name}</h4><p>{item.usage}</p></div>
      <div className="spacing-example"><div className="spacing-grid spacing-example-stage">{item.sample}</div><p className="spacing-caption">{item.caption}</p></div>
    </article>)}</div>
    <div className="spacing-composition"><h3>在组织概览与成员查询中组合使用</h3><p>把间距放回完整界面，观察附属信息、操作组、内容组与容器之间的关系。</p><SpacingComposition /></div>

  </div>;
}
