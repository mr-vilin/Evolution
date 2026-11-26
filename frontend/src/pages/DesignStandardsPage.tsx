import { useState, type CSSProperties, type ReactNode } from 'react';
import { App, Avatar, Badge, Button, Checkbox, ColorPicker, ConfigProvider, Input, Popover, Select, Space, Tag, Tooltip, theme } from 'antd';
import { CheckOutlined, CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined, LineChartOutlined, SmileOutlined, SunOutlined, SyncOutlined, UndoOutlined } from '@ant-design/icons';
import reference from '../design/reference.json';
import SpacingGuide, { spacingScaleCount } from '../design/SpacingGuide';
import ComponentGuide, { componentStyleCount } from '../design/ComponentGuide';
import ShadowGuide, { shadowStyleCount } from '../design/ShadowGuide';
import MotionGuide, { motionStyleCount } from '../design/MotionGuide';
import DesignSectionNav from '../design/DesignSectionNav';
import DesignMember from '../design/DesignMember';
import { useThemeColors } from '../theme/ThemeProvider';
import { type ColorRole } from '../theme/colors';
import '../design/standards.css';

const { data, colors: colorReference, chapters } = reference;
const valueIcons = [<SunOutlined />, <CheckOutlined />, <SmileOutlined />, <LineChartOutlined />];
const sections = [['colors', '色彩体系'], ['typography', '字体层级'], ['layout', '布局'], ['geometry', '圆角与形状'], ['spacing', '间距应用'], ['components', '组件样式'], ['shadows', '阴影'], ['motion', '动画'], ['notes', 'Do Or Not Do']];
const statusTypes = ['success', 'warning', 'error', 'processing', 'default'] as const;
const statusIcons = [<CheckCircleOutlined />, <ExclamationCircleOutlined />, <CloseCircleOutlined />, <SyncOutlined spin />, <ClockCircleOutlined />];
const entries = Object.entries;
const closingRules = [
  { topic: '设计判断', do: '依据自然、确定、有意义、成长四条价值观，选择更清晰、可读且一致的方案。', dont: '凭临时偏好牺牲信息清晰度、交互结构与状态反馈的一致性。' },
  { topic: '主要操作', do: '同一决策保留一个主要操作，其余操作使用次要样式。', dont: '堆叠多个同等强调的主要按钮，让操作争夺注意力。' },
  { topic: '主题表面', do: '按页面背景、内容容器与浮动表面的职责读取主题颜色。', dont: '写死白色或浅灰色来区分层级，绕过主题联动。' },
  { topic: '颜色职责', do: '主色表达交互，语义色表达状态，预设扩展色用于标签、图表与分类。', dont: '随意创造一次性强调色，或混淆操作、状态与分类的颜色含义。' },
  { topic: '间距网格', do: '使用统一间距刻度，将间隙、内边距与栅格对齐到 4px 网格。', dont: '用零散数值逐处修补布局；刻度不适用时先重新审视内容关系。' },
  { topic: '动画反馈', do: '沿用组件动效与命名令牌；没有更具体约定时使用中速时长与默认缓动。', dont: '随意编造缓动曲线，或用统一时长覆盖所有组件的进入与退出。' },
];
const typographyStyles = [
  { name: 'page-title', sample: '页面标题 · 标识当前页面，如组织架构、组织同步。', fontSize: '24px', lineHeight: '32px', fontWeight: 600, color: 'colorTextHeading' },
  { name: 'section-title', sample: '模块标题 · 说明这一区域的内容，如同步任务、成员详情。', fontSize: '16px', lineHeight: '24px', fontWeight: 600, color: 'colorTextHeading' },
  { name: 'body-text', sample: '主要内容 · 展示姓名、部门、手机号码等业务数据，以及表单输入与普通控件文字。', fontSize: '14px', lineHeight: '22px', fontWeight: 400, color: 'colorText' },
  { name: 'secondary-text', sample: '次要信息 · 解释主要内容，用于页面说明、详情字段名称和需要读懂的表单帮助。', fontSize: '14px', lineHeight: '22px', fontWeight: 400, color: 'colorTextSecondary' },
  { name: 'caption-text', sample: '附属注释 · 补充人数、单位与非关键更新时间，如部门名称旁的“共 20 人”。', fontSize: '12px', lineHeight: '20px', fontWeight: 400, color: 'colorTextSecondary' },
] as const;

function Section({ id, index, title, caption, children }: { id: string; index: string; title: string; caption?: string; children: ReactNode }) {
  return <section id={id}><div className="section-head"><span className="index">{index}</span><h2>{title}</h2><small>{caption}</small></div>{children}</section>;
}

function ColorCopy({ value, label, children, className = '', style }: { value: string; label: string; children?: ReactNode; className?: string; style?: CSSProperties }) {
  const { message } = App.useApp();
  async function copy() {
    try { await navigator.clipboard.writeText(value); message.success(`已复制 ${value}`); }
    catch { message.info(`复制未成功，请手动复制 ${value}`); }
  }
  return <button type="button" className={`color-copy ${className}`} style={style} title={`双击复制 ${value}`} aria-label={`${label}，双击或 Enter / 空格复制 ${value}`} onDoubleClick={() => void copy()} onKeyDown={event => {
    if ((event.key === 'Enter' || event.key === ' ') && !event.repeat) { event.preventDefault(); void copy(); }
  }}>{children}</button>;
}

function RoleCard({ role, name, usage }: { role: ColorRole; name: string; usage: string }) {
  const { colors, savedColors, setColor, saveColor, resetColor } = useThemeColors();
  const { message } = App.useApp();
  const changed = colors[role] !== savedColors[role];
  return <article className="swatch color-role-card" data-color-role={role}>
    <ColorCopy value={colors[role]} label={name} className="color-block" style={{ background: colors[role] }} />
    <h4 className="color-role-name">{name}</h4>
    <div className="color-details"><div className="role-editor"><code className="color-hex">{colors[role]}</code>
      <ColorPicker value={colors[role]} disabledAlpha format="hex" onChange={color => setColor(role, color.toHexString())}>
        <button type="button" className="role-icon role-picker" aria-label={`${name}取色`}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m14 5 5 5M4 16l10-10 4 4L8 20H4v-4Z" /><path d="m15 6 3-3a2.12 2.12 0 0 1 3 3l-3 3M3 21l1-1" /></svg>
        </button>
      </ColorPicker>
      {changed && <><button type="button" className="role-icon role-save" aria-label={`保存${name}`} onClick={() => { if (saveColor(role)) message.success('颜色已保存到当前浏览器'); }}><CheckOutlined /></button><button type="button" className="role-icon role-reset" aria-label={`重置${name}`} onClick={() => resetColor(role)}><UndoOutlined /></button></>}
    </div><p className="color-usage">{usage}</p></div>
  </article>;
}

function TypographyRow({ name, sample, value }: { name: string; sample: string; value: CSSProperties }) {
  const [code, setCode] = useState(false);
  return <div className={`type-row${code ? ' is-code' : ''}`}>
    <code className="token-name">{name}</code><div className="sample" style={value}>{sample}</div>
    <div className="type-meta">{value.fontSize} / {value.lineHeight}<br />{value.fontWeight}<br />{String(value.color).toUpperCase()}</div>
    <button type="button" className="code-icon type-code-button" aria-label={`${code ? '收起' : '查看'} ${name} 代码`} aria-expanded={code} onClick={() => setCode(!code)}>&lt;/&gt;</button>
    {code && <pre className="type-code-panel">{`.${name} {\n${entries(value).map(([key, item]) => `  ${key.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`)}: ${item};`).join('\n')}\n}`}</pre>}
  </div>;
}

function LayoutGuide() {
  const { token } = theme.useToken();
  return <div className="panel layout-guide" style={{ '--shadow-popup': token.boxShadowSecondary } as CSSProperties}>
    <div className="layout-intro"><h3>先分清表面，再安排内容和间距</h3><p>原文用三层表面组织界面：页面背景包围内容，内容容器承载日常工作，浮动表面承载临时操作。搭建列表页、表单页或工作台时，先判断内容属于哪一层，再选择相应表面。</p><p>表面与文字通过主题统一配置。扩展深色主题时，由 theme.algorithm 中的 darkAlgorithm 协调颜色、表面与阴影，不手工反转颜色；当前项目使用 defaultAlgorithm 浅色主题。</p></div>
    <div className="surface-stack" aria-label="页面背景、内容容器与浮动表面示意">
      <span className="mini-label">页面背景 · bg-layout</span><p className="surface-description">整个工作台的底板，留白与模块之间的空隙属于这一层。</p>
      <div className="surface-container-demo"><span className="mini-label">内容表面 · bg-container</span><h4>成员列表与筛选区</h4><p className="surface-description">列表、表单和卡片放在这里；同一任务的内容集中在一个容器内。</p><Space wrap><Button type="primary">新增成员</Button><Button>筛选成员</Button></Space>
        <div className="surface-popup-demo"><span className="mini-label">浮动表面 · bg-elevated · 示意</span><h4>临时选择筛选条件</h4><p className="surface-description">实际使用下拉菜单、弹出层或模态框承载，结束操作后关闭。</p></div>
      </div>
    </div>
    <div className="layout-usage-grid">
      <article><h4>页面背景</h4><p><strong>用在哪里：</strong>页面画布、模块周围的留白。</p><p><strong>什么时候用：</strong>搭建页面整体框架时，用它分隔卡片与区域，形成清晰的阅读分组。</p></article>
      <article><h4>内容表面</h4><p><strong>用在哪里：</strong>卡片、面板、表格和表单。</p><p><strong>什么时候用：</strong>内容需要持续展示或编辑时使用。优先用边框与色调对比区分区域，不给每张卡片都加阴影。</p></article>
      <article><h4>浮动表面</h4><p><strong>用在哪里：</strong>模态框、下拉菜单与弹出层。</p><p><strong>什么时候用：</strong>操作需要临时覆盖当前内容时使用。默认浅色主题下它与内容表面同色，通过阴影表达悬浮关系。</p></article>
    </div>
    <div className="layout-rules"><h3>落到页面时这样选</h3><ol><li>先画页面背景，再按任务划分内容容器；需要临时选择、补充信息或确认时，再使用浮动组件。</li><li>普通内容优先依靠边框与色调对比建立层级，真正悬浮的表面才使用相应阴影；具体效果见下方“阴影”模块。</li><li>容器内边距、模块间隔和控件间隙对齐 4px 网格，从 4、8、16、24、32px 中选择；例如卡片内边距 24px、内部控件间隔 16px。具体刻度见“间距应用”。</li><li>表面颜色读取主题中的对应角色，让它随主题联动；不要为了区分层级临时写死白色或浅灰色。浮层位置与交互交给对应组件处理。</li></ol></div>
    
  </div>;
}

function RadiusSmallExamples() {
  return <>
    <div className="radius-tag-example"><Tag color="blue">研发部</Tag><span className="radius-caption">分类标签 · 4px</span></div>
    <div className="radius-popup-examples">
      <div className="radius-popup-example"><span className="radius-field-label">文字提示浮层（Tooltip）· 4px</span>
        <div className="radius-popup-stage"><Tooltip title="部门名称用于识别成员所属组织" open arrow placement="top" autoAdjustOverflow={false} trigger={[]} getPopupContainer={trigger => trigger.parentElement!} styles={{ root: { maxWidth: '100%' } }}><span aria-hidden="true" /></Tooltip></div>
      </div>
      <div className="radius-popup-example"><span className="radius-field-label">气泡卡片浮层（Popover）· 4px</span>
        <div className="radius-popup-stage"><Popover title="部门说明" content="用于归类成员，便于按部门筛选。" open arrow placement="top" autoAdjustOverflow={false} trigger={[]} getPopupContainer={trigger => trigger.parentElement!} styles={{ root: { maxWidth: '100%' } }}><span aria-hidden="true" /></Popover></div>
      </div>
    </div>
    <p className="radius-small-explanation">文字提示用于简短解释，气泡卡片可包含标题和更多内容。</p>
  </>;
}

function RadiusGuide() {
  const { token } = theme.useToken();
  const avatarStyle: CSSProperties = { borderRadius: data.rounded.full, background: token.colorPrimary, color: token.colorTextLightSolid };
  const applications = [
    { name: '内部拼接', rounded: 'none' as const, usage: '表格内部、分段控件的相邻边缘。连续内容的接缝使用直角，外部容器可按所属类别保留圆角。',
      sample: <><div className="radius-table-shell"><table className="radius-table" aria-label="表格内部直角拼接示例"><thead><tr><th scope="col">成员</th><th scope="col">部门</th></tr></thead><tbody><tr><td><DesignMember name="林晓" /></td><td>研发部</td></tr></tbody></table></div><p className="radius-caption">内部单元格接缝 0px · 外部容器 8px</p></> },
    { name: '复选框', rounded: 'sm' as const, usage: '复选框的方框使用 2px 圆角。用于勾选筛选条件或选择多项内容，选中和未选中时保持一致的轮廓。',
      sample: <div className="radius-checkbox-examples"><Checkbox defaultChecked>包含子部门</Checkbox><Checkbox>仅显示负责人</Checkbox></div> },
    { name: '小型元素', rounded: 'md' as const, usage: '分类标签、小 chip、文字提示（Tooltip）和气泡卡片（Popover）。用于分类和补充说明；标签与浮层的外框使用 4px 圆角。',
      sample: <RadiusSmallExamples /> },
    { name: '默认控件与多选项', rounded: 'DEFAULT' as const, usage: '按钮、输入框、选择器和下拉触发器，以及多选器内的已选项。用于查询、录入与选择，控件外框和多选已选项均为 6px 圆角。',
      sample: <><div className="radius-controls"><Input aria-label="圆角示例姓名搜索" placeholder="搜索姓名" /><Select aria-label="圆角示例部门选择" defaultValue="all" options={[{ value: 'all', label: '全部部门' }, { value: 'engineering', label: '研发部' }]} /><Button>查询成员</Button></div><div className="radius-multiple-example"><label htmlFor="radius-selected-members" className="radius-field-label">多选成员 · 已选项 6px</label><Select id="radius-selected-members" mode="multiple" defaultValue={['lin', 'chen', 'zhou']} options={[{ value: 'lin', label: '林晓' }, { value: 'chen', label: '陈晨' }, { value: 'zhou', label: '周宁' }, { value: 'wang', label: '王悦' }]} /></div></> },
    { name: '内容表面', rounded: 'lg' as const, usage: '卡片、弹窗、抽屉和通知。用于承载一组相关内容，或提供临时确认与反馈。',
      sample: <div className="radius-surface-example"><h4>部门信息卡片</h4><p>研发部 · 成员与组织资料</p></div> },
    { name: '圆形元素', rounded: 'full' as const, usage: '圆形头像、徽标和状态圆点。头像内文字统一为 14px，头像与姓名间隔 1 个 unit（4px）；全圆角不用于普通按钮或分类标签。',
      sample: <div className="radius-round-examples">
        <div className="radius-round-member"><Avatar aria-label="圆形成员头像示例" style={avatarStyle}>林</Avatar><span>林晓</span></div>
        <div role="group" aria-label="成员头像叠加示例：林晓、陈晨、周宁"><Avatar.Group>{['林晓', '陈晨', '周宁'].map(name => <Avatar key={name} aria-label={name} style={avatarStyle}>{name[0]}</Avatar>)}</Avatar.Group></div>
        <Badge status="success" text="同步成功" />
      </div> },
  ];
  return <ConfigProvider theme={{ token: { borderRadius: parseFloat(data.rounded.DEFAULT), borderRadiusSM: parseFloat(data.rounded.md), borderRadiusLG: parseFloat(data.rounded.lg) }, components: { Checkbox: { borderRadiusSM: parseFloat(data.rounded.sm) }, Select: { borderRadiusSM: parseFloat(data.rounded.DEFAULT) }, Tooltip: { borderRadius: parseFloat(data.rounded.md) }, Popover: { borderRadiusLG: parseFloat(data.rounded.md) } } }}>
    <div className="panel radius-guide">
      <div id="note-5" className="radius-intro"><h3>按元素用途选择圆角</h3><p>默认圆角为 6px，兼顾友好感与密集表单的清晰轮廓。下方案例按 0px、2px、4px、6px、8px、full 排列，根据元素用途选择对应标准。</p><p>整体调整通过主题的 borderRadius 及相关圆角令牌统一完成；单类组件的差异放在 theme.components 中。本模块的局部配置只约束下方案例，未覆盖的颜色与其他令牌继续继承系统主题。</p></div>
      <div className="radius-applications">{applications.map(item => <article className="radius-application" key={item.rounded}>
        <div className="radius-standard"><strong>{item.rounded === 'full' ? 'full' : data.rounded[item.rounded]}</strong><code>rounded.{item.rounded}</code>{item.rounded === 'full' && <span>{data.rounded.full}</span>}</div>
        <div className="radius-usage"><h4>{item.name}</h4><p>{item.usage}</p></div>
        <div className="radius-example">{item.sample}</div>
      </article>)}</div>
      <div className="radius-composition"><h3>在一张部门信息卡片中组合使用</h3><div className="radius-composition-grid">
        <div className="radius-composite-card"><header><h4>部门信息卡片</h4><span className="radius-caption">外框 · 8px</span></header>
          <div className="radius-member"><div className="radius-member-person"><Avatar aria-label="卡片内圆形成员头像示例" style={{ borderRadius: data.rounded.full, background: token.colorPrimary, color: token.colorTextLightSolid }}>林</Avatar><div><span>林晓 · 示例成员</span><p className="radius-caption">头像 · 圆形，距姓名 4px</p></div></div><div className="radius-member-tag"><Tag color="blue">研发部</Tag><p className="radius-caption">标签 · 4px</p></div></div>
          <div className="radius-composite-controls"><label htmlFor="radius-member-name">姓名 · 6px<Input id="radius-member-name" placeholder="搜索姓名" /></label><label htmlFor="radius-member-department">部门 · 6px<Select id="radius-member-department" defaultValue="engineering" options={[{ value: 'engineering', label: '研发部' }, { value: 'product', label: '产品部' }]} /></label><div><span className="radius-field-label">按钮 · 6px</span><Button type="primary">查询成员</Button></div></div>
          <div className="radius-composite-status"><Badge status="success" text="同步成功" /><span className="radius-caption">状态点 · 圆形</span></div>
        </div>
        <div className="radius-combination-rules"><h4>组合时这样选</h4><ul><li>同类控件保持一致，例如输入框、选择器与按钮均为 6px。</li><li>不同类别按用途组合：卡片 8px、控件 6px、标签 4px，头像与状态点为圆形。</li><li>头像与姓名之间留 1 个 unit（4px）；全圆角仅用于头像、徽标和圆点，表格内部拼接使用 0px。</li></ul><div className="radius-bad-example"><span>不推荐 · 圆角关系不一致</span><div className="radius-bad-card"><span className="radius-caption">卡片 8px</span><Button style={{ borderRadius: data.rounded.xl }}>按钮 16px</Button></div></div></div>
      </div></div>
      <div className="radius-reference"><h3>完整圆角刻度</h3><p>七档刻度按数值从小到大排列。16px 当前未指定常规应用场景；日常界面优先按上方用途选择。</p><div className="shape-grid">{entries(data.rounded).sort(([, left], [, right]) => parseFloat(left) - parseFloat(right)).map(([name, value]) => <div className="shape-item" key={name}><div className="shape" style={{ borderRadius: value }} aria-hidden="true" /><code>{name}</code><code>{value}</code>{name === 'xl' && <span className="radius-caption">未指定常规场景</span>}</div>)}</div></div>
    </div>
  </ConfigProvider>;
}

function DoOrNotDoGuide() {
  return <div id="note-7" className="panel closing-rules">
    <table className="rules-table" aria-label="应该与不要的设计规则对照">
      <thead><tr><th scope="col"><span className="rule-verdict is-do" aria-hidden="true">✓</span>应该</th><th scope="col"><span className="rule-verdict is-dont" aria-hidden="true">×</span>不要</th></tr></thead>
      <tbody>{closingRules.map(rule => <tr key={rule.topic}>
        <td><span className="rule-mobile-label"><span className="rule-verdict is-do" aria-hidden="true">✓</span>应该</span><h3>{rule.topic}</h3><p>{rule.do}</p></td>
        <td><span className="rule-mobile-label"><span className="rule-verdict is-dont" aria-hidden="true">×</span>不要</span><h3>{rule.topic}</h3><p>{rule.dont}</p></td>
      </tr>)}</tbody>
    </table>
  </div>;
}

export default function DesignStandardsPage() {
  const { reset, storageError } = useThemeColors();
  const { token } = theme.useToken();
  const supplements = [token.colorPrimaryHover, token.colorPrimaryActive, token.colorPrimaryBg, token.colorFillAlter, token.colorTextDisabled, token.colorBorder];
  return <ConfigProvider avatar={{ style: { fontSize: 14 } }} theme={{ components: {
    Checkbox: { borderRadiusSM: 2 },
    Select: { optionSelectedFontWeight: 400 },
    Tabs: { itemColor: token.colorTextSecondary, itemHoverColor: token.colorPrimaryHover, itemSelectedColor: token.colorPrimary, itemActiveColor: token.colorPrimaryActive },
  } }}><div className="design-standards"><main className="design-main">
    <header className="hero"><div><div className="eyebrow">DESIGN REFERENCE / ALPHA</div><h1>让设计准则，清晰可见。</h1><p>{data.description}</p></div></header>
    <div className="value-grid" role="list" aria-label="设计价值观">{[['自然', 'Nature'], ['确定', 'Certainty'], ['有意义', 'Meaningfulness'], ['成长', 'Growth']].map(([name, english], index) => <article className="value-card" key={name} tabIndex={0} role="listitem"><span className="value-english" lang="en">{english}</span><h3><span className="value-title-icon" aria-hidden="true">{valueIcons[index]}</span>{name}</h3><p>{chapters[0].paragraphs.find(text => text.startsWith(`${name}。`))?.slice(name.length + 1).trim()}</p></article>)}</div>
    <div className="overview" aria-label="准则概览">{[[String(Object.values(colorReference).flat().length), '色彩'], [String(typographyStyles.length), '字体层级'], [String(entries(data.rounded).length), '圆角'], [String(spacingScaleCount), '间距'], [String(componentStyleCount), '组件样式'], [String(shadowStyleCount), '阴影'], [String(motionStyleCount), '动画']].map(([count, label]) => <div className="metric" key={label}><strong>{count.padStart(2, '0')}</strong><span>{label}</span></div>)}</div>
    <DesignSectionNav sections={sections} />
    <Section id="colors" index="01" title="色彩体系" caption="色彩职责 / 语义色 / 扩展色"><div className="panel">
      <div className="palette-group"><div className="palette-title"><h3>色彩职责</h3><Button onClick={reset}>恢复默认颜色</Button></div><p className="palette-description">主色负责主要操作，辅助色支持内容，点睛色少量强调；灰白色承担空间与阅读层级。双击色块可复制色值。</p><p className="theme-status" role="status">{storageError || '取色后即时预览；点击勾选才保存，重置恢复已保存的颜色。仅保存在当前浏览器，确认后同步到同源标签页。'}</p>
        <p id="note-8" className="palette-description">主题入口为 ConfigProvider.theme，主色与状态色通过 theme.token 的颜色种子配置，悬停、按下与浅背景由算法派生。优先调整最小必要的种子，保持颜色职责与状态含义一致。</p>
        <div className="swatches color-role-grid">{colorReference.roles.map(item => <RoleCard key={item.key} role={item.key as ColorRole} name={item.name} usage={item.usage} />)}</div>
        <div className="palette-supplement"><h4>交互与界面补充</h4><div className="swatches color-supplement-grid">{colorReference.supplements.map((item, i) => <article key={item.key} className="swatch color-role-card"><ColorCopy value={supplements[i].toUpperCase()} label={item.name} className="color-block" style={{ background: supplements[i] }} /><h4 className="color-role-name">{item.name}</h4><div className="color-details"><code className="color-hex">{supplements[i].toUpperCase()}</code><p className="color-usage">{item.usage}</p></div></article>)}</div></div>
      </div>
      <div className="palette-group"><div className="palette-title"><h3>语义色</h3></div><p className="palette-description">小圆点、浅色填充标签和带状态图标的标签共同表达状态。中性示例统一展示“未开始”；业务中的无效、未知状态保留各自文案，不互相替代。</p><div className="swatches color-example-grid color-semantic-grid">{colorReference.semantic.map((item, i) => {
        const neutral = item.key === 'invalid';
        // 原始附件保持不变；中性展示统一为「未开始」，不把不同业务状态当作同义词。
        const name = neutral ? item.filled : item.name;
        const hex = (neutral ? item.hex : [token.colorSuccess, token.colorWarning, token.colorError, token.colorInfo][i]).toUpperCase();
        const neutralStyle: CSSProperties | undefined = neutral ? { background: hex, color: token.colorText, borderColor: 'transparent' } : undefined;
        return <article className={`swatch color-example-card${neutral ? ' color-neutral-example' : ''}`} key={item.key}><div className="color-samples"><ColorCopy value={hex} label={name}><Badge color={hex} text={name} /></ColorCopy><ColorCopy value={hex} label={item.filled}><Tag color={statusTypes[i]} style={neutralStyle}>{item.filled}</Tag></ColorCopy><ColorCopy value={hex} label={`${item.filled} Status (filled)`}><Tag color={statusTypes[i]} style={neutralStyle} icon={statusIcons[i]}>{item.filled}</Tag></ColorCopy></div><code className="color-hex">{hex}</code></article>;
      })}</div></div>
      <div className="palette-group"><div className="palette-title"><h3>扩展色</h3></div><p className="palette-description">12 种预设色用于分类、标签和图表，保留统一的分类含义。</p><div className="swatches color-example-grid">{colorReference.presets.map(item => <article className="swatch color-example-card" key={item.key}><div className="color-samples"><ColorCopy value={item.hex} label={item.name}><Tag color={item.key}>{item.name}</Tag></ColorCopy></div><code className="color-hex">{item.hex}</code></article>)}</div></div>
      
    </div></Section>
    <Section id="typography" index="02" title="字体层级" caption="5 类常用文字 · 明确作用与使用位置"><div className="panel">{typographyStyles.map(({ name, sample, color, ...style }) => <TypographyRow key={name} name={name} sample={sample} value={{ ...style, fontFamily: data.typography['body-md'].fontFamily, color: token[color] }} />)}<div className="family">使用规则：表头沿用 14px 正文并加重至 600；时间统一使用说明灰；日志提交时间等关键数据保留 14px／22px，附属时间、单位与人数使用 12px／20px。尺寸标注使用三级文字色。占位与禁用文字使用 {token.colorTextDisabled.toUpperCase()}，字号继承所在控件。链接与选中项使用主题色，成功、告警与失败使用对应语义色。
      <div>产品 UI 中只出现两种字重：400（正文、控件、菜单项、标签页标签）和 600（fontWeightStrong——标题、表头以及任何标题级排版）。</div>
      <div>细体（100–300）、粗体（700+）和斜体不用于界面 chrome——它们会与系统追求的平静、确定基调相冲突。</div>
      <div>斜体仅在长篇文档正文中可接受。选中/激活状态的视觉强调来自颜色和描边（边框、下划线），而不是字重。</div>
      <div>字体与基础字号通过主题的 fontFamily、fontSize 统一调整；维持标题、正文和附属信息的层级关系，以及既定的 400／600 字重。规范页自身的展示标题与章节标题允许特殊层级，业务页面仍采用以上五类常用文字。</div>
      <code>字体栈：{data.typography['body-md'].fontFamily}</code></div></div></Section>
    <Section id="layout" index="03" title="布局" caption="三层表面 · 使用位置与选择方法"><LayoutGuide /></Section>
    <Section id="geometry" index="04" title="圆角与形状" caption="数值标准 · 适用场景 · 组合示例"><RadiusGuide /></Section>
    <Section id="spacing" index="05" title="间距应用" caption="4px 网格 · 适用场景 · 组合示例"><SpacingGuide /></Section>
    <Section id="components" index="06" title="组件样式" caption={`${componentStyleCount} 项 · 用途、规范与交互`}><ComponentGuide /></Section>
    <Section id="shadows" index="07" title="阴影" caption="使用位置 · 层级选择 · 组合示例"><ShadowGuide /></Section>
    <Section id="motion" index="08" title="动画" caption="三档时长 · 命名缓动 · 交互示例"><MotionGuide /></Section>
    <Section id="notes" index="09" title="Do Or Not Do" caption="设计判断 · 六组对照"><DoOrNotDoGuide /></Section>
    <footer className="page-foot"><span>Ant Design · 设计准则参考</span><span>Ant Design 默认准则与通用色彩职责</span></footer>
  </main></div></ConfigProvider>;
}
