import { useState } from 'react';
import { Alert, Badge, Button, Card, ConfigProvider, Dropdown, Input, Menu, Modal, Select, Table, Tabs, Tag, Tooltip, theme, type GlobalToken, type ThemeConfig } from 'antd';
import { ApartmentOutlined, DownOutlined, TeamOutlined, UnorderedListOutlined } from '@ant-design/icons';
import './component-guide.css';
import DesignMember from './DesignMember';

const guidelines = [
  { id: 'button-primary', title: '主要按钮', component: 'Button · primary',
    purpose: '用于当前决策中最重要的操作，例如保存修改、确认提交。',
    rules: '32px 高、6px 圆角，主色填充与反色文字。悬停时填充变亮，按住时加深。',
    reminder: '同一决策只保留一个主要按钮，其余操作使用默认按钮。' },
  { id: 'button-default', title: '默认按钮', component: 'Button · default',
    purpose: '用于重置、取消等次要操作，与主要操作形成清晰层级。',
    rules: '32px 高、6px 圆角，使用内容表面、正文文字和 1px 边框。悬停时文字与边框同步变为主色悬停色。',
    reminder: '保持轻量外观，让用户先看到当前最重要的操作。' },
  { id: 'input-field', title: '输入框', component: 'Input',
    purpose: '用于录入姓名、关键词等信息，高度与同行按钮保持一致。',
    rules: '32px 高、6px 圆角、1px 边框。聚焦时使用主色边框和框架焦点光晕，占位文字使用占位色。',
    reminder: '聚焦前后保持相同尺寸，避免边框变化挤动周围内容。' },
  { id: 'select-field', title: '选择器', component: 'Select',
    purpose: '用于从已知选项中选择部门、类型等内容。',
    rules: '触发器与输入框采用相同的 32px 高度、6px 圆角、内容表面和边框规则。',
    reminder: '交互前就能识别为录入控件；点击后在同一控件中体验选择与清除。' },
  { id: 'card', title: '卡片', component: 'Card',
    purpose: '承载同一任务下的内容，例如部门概览、成员资料和筛选条件。',
    rules: '使用内容表面和 8px 圆角；四边内边距均为 24px，内部内容与嵌套控件保持 16px 间隔。',
    reminder: '默认依靠边框和表面分层，需要抬升时再使用框架的卡片阴影。' },
  { id: 'modal', title: '弹窗', component: 'Modal',
    purpose: '用于需要临时集中注意力的确认、补充信息与短流程。',
    rules: '浮动表面、8px 圆角和次级阴影；在遮罩上居中。主体内边距为上下 20px、左右 24px。',
    reminder: '弹窗里同样只保留一个主要操作，并允许取消、关闭或按 Esc 返回。' },
  { id: 'menu', title: '菜单', component: 'Menu',
    purpose: '用于在功能或页面之间导航，让用户知道自己当前在哪里。',
    rules: '选中项使用主色浅背景和主色文字，文字保持 400 字重。',
    reminder: '单选导航只突出当前项；点击示例菜单查看选中位置的变化。' },
  { id: 'tabs', title: '页签', component: 'Tabs',
    purpose: '用于切换同一上下文中的不同内容，例如部门概况与成员信息。',
    rules: '活动项使用主色文字和 2px 主色下划线，非活动项使用说明色；文字均为 400 字重。',
    reminder: '各状态都不填充背景，通过文字和下划线表达当前位置。' },
  { id: 'table', title: '表格', component: 'Table',
    purpose: '用于并列呈现需要比较、查阅的成员和部门等结构化数据。',
    rules: '表头使用浅表面色与 14px／600 排版；正文使用 14px／400，人员列使用圆形头像加姓名、间距 4px；悬停时只高亮当前行。',
    reminder: '默认不使用斑马纹，依靠对齐、间距和表头组织密集数据。' },
  { id: 'tag', title: '分类标签', component: 'Tag',
    purpose: '用于标记部门、类别或分组，帮助快速识别内容归属。',
    rules: '4px 圆角、12px 字体，使用现有扩展色的浅色填充；同一类别保持一致配色。',
    reminder: '分类颜色沿用扩展色体系；表格状态列使用带中文文字的语义 Tag，页面级关键反馈使用提示反馈或状态点。' },
  { id: 'alert', title: '提示反馈', component: 'Alert',
    purpose: '用于明确反馈操作结果，或说明需要用户关注的信息。',
    rules: '成功、告警、错误、信息采用对应语义浅背景与图标，正文保持正常文字颜色。',
    reminder: '通过图标、色调和文字共同表达含义，避免低对比度的彩色正文。' },
  { id: 'badge', title: '状态点', component: 'Badge',
    purpose: '用于列表、摘要等紧凑区域中的状态指示。',
    rules: '6px 圆点配合状态文字；成功、告警、错误和进行中使用对应语义色。',
    reminder: '关键流程中圆点必须配文字，让用户无需辨别颜色也能理解状态。' },
  { id: 'tooltip', title: '文字提示', component: 'Tooltip',
    purpose: '用于解释字段、按钮和简短术语，不承载复杂操作。',
    rules: '使用高对比度反色表面、反色文字和 4px 圆角；悬停或键盘聚焦后出现。',
    reminder: '浮层的位置、箭头和空间避让由框架处理。' },
  { id: 'dropdown', title: '下拉菜单', component: 'Dropdown',
    purpose: '用于收纳同一对象的多个次要操作，保持页面简洁。',
    rules: '使用浮动表面；条目悬停时填充浅表面色，文字颜色保持一致。',
    reminder: '通过背景变化提示可操作性，打开菜单并悬停条目查看效果。' },
] as const;

type ComponentName = typeof guidelines[number]['id'];
export const componentStyleCount = guidelines.length;
const departments = ['研发部', '产品部', '运营部'].map(name => ({ value: name, label: name }));
const members = [{ name: '林晓', department: '研发部' }, { name: '陈晨', department: '产品部' }, { name: '周宁', department: '运营部' }];
const menuItems = [
  { key: 'overview', label: '组织概览', icon: <ApartmentOutlined aria-hidden /> },
  { key: 'members', label: '成员信息', icon: <TeamOutlined aria-hidden /> },
  { key: 'records', label: '变更记录', icon: <UnorderedListOutlined aria-hidden /> },
];
const alerts = [
  { type: 'success', title: '成员信息已保存', background: 'colorSuccessBg', border: 'colorSuccessBorder', icon: 'colorSuccess' },
  { type: 'warning', title: '部分成员资料待补全', background: 'colorWarningBg', border: 'colorWarningBorder', icon: 'colorWarning' },
  { type: 'error', title: '保存失败，请检查后重试', background: 'colorErrorBg', border: 'colorErrorBorder', icon: 'colorError' },
  { type: 'info', title: '可以按部门筛选成员', background: 'colorInfoBg', border: 'colorInfoBorder', icon: 'colorInfo' },
] as const;

function guideTheme(token: GlobalToken) {
  return {
    token: { controlHeight: 32, borderRadius: 6, borderRadiusLG: 8, borderRadiusSM: 4 },
    components: {
      Button: {
        fontWeight: 400, primaryColor: token.colorTextLightSolid, solidTextColor: token.colorTextLightSolid,
        defaultBg: token.colorBgContainer, defaultColor: token.colorText, defaultBorderColor: token.colorBorder,
        defaultHoverBg: token.colorBgContainer, defaultHoverColor: token.colorPrimaryHover, defaultHoverBorderColor: token.colorPrimaryHover,
        defaultActiveBg: token.colorBgContainer, defaultActiveColor: token.colorPrimaryActive, defaultActiveBorderColor: token.colorPrimaryActive,
      },
      Input: { activeBorderColor: token.colorPrimary, hoverBorderColor: token.colorPrimaryHover },
      Select: { selectorBg: token.colorBgContainer, activeBorderColor: token.colorPrimary, activeOutlineColor: token.controlOutline, hoverBorderColor: token.colorPrimaryHover, optionSelectedFontWeight: 400 },
      Card: { bodyPadding: 24 },
      Modal: { contentBg: token.colorBgElevated, headerBg: token.colorBgElevated },
      Menu: { itemBg: token.colorBgContainer, itemColor: token.colorText, itemHoverBg: token.colorFillAlter, itemHoverColor: token.colorText, itemSelectedBg: token.colorPrimaryBg, itemSelectedColor: token.colorPrimary, activeBarWidth: 0 },
      Tabs: { itemColor: token.colorTextSecondary, itemHoverColor: token.colorPrimaryHover, itemSelectedColor: token.colorPrimary, itemActiveColor: token.colorPrimaryActive, inkBarColor: token.colorPrimary },
      Table: { headerBg: token.colorFillAlter, headerColor: token.colorText, rowHoverBg: token.colorFillAlter, cellFontSizeSM: 14, cellPaddingBlockSM: 16, cellPaddingInlineSM: 16 },
      Tag: { fontSizeSM: 12 },
      Alert: { borderRadius: 8, defaultPadding: '8px 12px' },
      Badge: { statusSize: 6, textFontSize: 14 },
      Tooltip: { borderRadius: 4 },
      Dropdown: { controlItemBgHover: token.colorFillAlter },
    },
  } satisfies ThemeConfig;
}

function modalStyles(token: GlobalToken) {
  return {
    container: { padding: 0, borderRadius: 8, boxShadow: token.boxShadowSecondary },
    header: { padding: '20px 24px', margin: 0, borderBottom: `1px solid ${token.colorBorderSecondary}` },
    title: { paddingInlineEnd: 24 },
    body: { padding: '20px 24px' },
    footer: { padding: '0 24px 20px', margin: 0 },
    mask: { backgroundColor: token.colorBgMask },
  };
}

function rule(selector: string, declarations: Record<string, string | number>) {
  return `${selector} {\n${Object.entries(declarations).map(([property, value]) => `  ${property}: ${value};`).join('\n')}\n}`;
}

function componentCode(name: ComponentName, token: GlobalToken) {
  const color = (key: keyof GlobalToken) => `${String(token[key]).replace(/#[\da-f]{6}/gi, hex => hex.toUpperCase())} /* ${key} */`;
  const control = { height: '32px', 'border-radius': '6px', 'font-size': '14px', 'font-weight': 400 };
  const border = `1px solid ${color('colorBorder')}`;
  const focus = `0 0 0 ${token.controlOutlineWidth}px ${color('controlOutline')}`;
  let rules: string[];
  switch (name) {
    case 'button-primary': rules = [
      rule('.ant-btn-primary', { ...control, background: color('colorPrimary'), color: color('colorTextLightSolid') }),
      rule('.ant-btn-primary:hover', { background: color('colorPrimaryHover') }),
      rule('.ant-btn-primary:active', { background: color('colorPrimaryActive') }),
    ]; break;
    case 'button-default': rules = [
      rule('.ant-btn-default', { ...control, background: color('colorBgContainer'), color: color('colorText'), border }),
      rule('.ant-btn-default:hover', { color: color('colorPrimaryHover'), 'border-color': color('colorPrimaryHover') }),
      rule('.ant-btn-default:active', { color: color('colorPrimaryActive'), 'border-color': color('colorPrimaryActive') }),
    ]; break;
    case 'input-field': rules = [
      rule('.ant-input', { ...control, background: color('colorBgContainer'), color: color('colorText'), border }),
      rule('.ant-input::placeholder', { color: color('colorTextPlaceholder') }),
      rule('.ant-input:hover', { 'border-color': color('colorPrimaryHover') }),
      rule('.ant-input:focus', { 'border-color': color('colorPrimary'), 'box-shadow': focus }),
    ]; break;
    case 'select-field': rules = [
      rule('.ant-select', { ...control, background: color('colorBgContainer'), color: color('colorText'), border }),
      rule('.ant-select-placeholder', { color: color('colorTextPlaceholder') }),
      rule('.ant-select:hover', { 'border-color': color('colorPrimaryHover') }),
      rule('.ant-select-focused', { 'border-color': color('colorPrimary'), 'box-shadow': focus }),
    ]; break;
    case 'card': rules = [
      rule('.ant-card', { background: color('colorBgContainer'), color: color('colorText'), 'border-radius': '8px', border: `1px solid ${color('colorBorderSecondary')}` }),
      rule('.ant-card-body', { padding: '24px' }), rule('.component-card-content', { display: 'grid', gap: '16px' }),
      '/* 普通内容默认使用边框分层，抬升阴影按需使用框架 token。 */',
    ]; break;
    case 'modal': rules = [
      rule('.ant-modal-container', { background: color('colorBgElevated'), color: color('colorText'), 'border-radius': '8px', padding: 0, 'box-shadow': token.boxShadowSecondary.trim().replace(/\s+/g, ' ') }),
      rule('.ant-modal-body', { padding: modalStyles(token).body.padding }), rule('.ant-modal-mask', { background: color('colorBgMask') }),
      '/* centered：由 Modal 负责居中、焦点管理与关闭交互。 */',
    ]; break;
    case 'menu': rules = [
      rule('.ant-menu-item', { color: color('colorText'), 'font-weight': 400 }),
      rule('.ant-menu-item-selected', { background: color('colorPrimaryBg'), color: color('colorPrimary') }),
    ]; break;
    case 'tabs': rules = [
      rule('.ant-tabs-tab', { background: 'transparent', color: color('colorTextSecondary'), 'font-weight': 400 }),
      rule('.ant-tabs-tab-active .ant-tabs-tab-btn', { color: color('colorPrimary'), 'font-weight': 400 }),
      rule('.ant-tabs-ink-bar', { height: '2px', background: color('colorPrimary') }),
    ]; break;
    case 'table': rules = [
      rule('.ant-table-thead > tr > th', { background: color('colorFillAlter'), color: color('colorText'), 'font-size': '14px', 'font-weight': 600, padding: '16px' }),
      rule('.ant-table-tbody > tr > td', { background: color('colorBgContainer'), color: color('colorText'), 'font-size': '14px', 'font-weight': 400 }),
      rule('.ant-table-tbody > tr:hover > td', { background: color('colorFillAlter') }),
    ]; break;
    case 'tag': rules = [
      rule('.ant-tag', { 'border-radius': '4px', 'font-size': '12px', 'font-weight': 400 }),
      '/* Tag color="blue" / "purple" / "cyan"，variant="filled"。\n   背景、边框、文字由现有预设调色板派生。 */',
    ]; break;
    case 'alert': rules = alerts.flatMap(item => [
      rule(`.component-alert-${item.type}`, { background: color(item.background), 'border-color': color(item.border), color: color('colorText'), 'border-radius': '8px', padding: '8px 12px' }),
      rule(`.component-alert-${item.type} .ant-alert-icon`, { color: color(item.icon) }),
    ]); break;
    case 'badge': rules = [
      rule('.ant-badge-status-dot', { width: '6px', height: '6px', 'border-radius': '50%' }),
      ...(['Success', 'Warning', 'Error', 'Info'] as const).map((status, index) => rule(`.ant-badge-status-${['success', 'warning', 'error', 'processing'][index]}`, { background: color(`color${status}`) })),
      rule('.ant-badge-status-text', { color: color('colorText') }),
    ]; break;
    case 'tooltip': rules = [
      rule('.ant-tooltip-container', { background: color('colorBgSpotlight'), color: color('colorTextLightSolid'), 'border-radius': '4px' }),
      '/* trigger={["hover", "focus"]}；位置、箭头和溢出避让由 Tooltip 处理。 */',
    ]; break;
    case 'dropdown': rules = [
      rule('.ant-dropdown-menu', { background: color('colorBgElevated'), color: color('colorText') }),
      rule('.ant-dropdown-menu-item:hover', { background: color('colorFillAlter'), color: color('colorText') }),
    ]; break;
  }
  return `/* 当前主题下的关键样式；交互由 Ant Design 组件负责。
 * React 内通过 theme.useToken() 读取当前作用域的令牌；
 * React 外通过 theme.getDesignToken() 读取，并传入一致的主题配置。
 * 本项目将解析后的令牌输出为项目 CSS 变量；
 * theme.cssVar 可配置官方 CSS 变量输出。
 * theme.zeroRuntime 是可选的静态样式方案，需要配套预构建或提取的 CSS；
 * 当前项目未启用零运行时模式。
 */\n\n${rules.join('\n\n')}`;
}

function ComponentExample({ name }: { name: ComponentName }) {
  const { token } = theme.useToken();
  const [value, setValue] = useState('');
  const [open, setOpen] = useState(false);
  switch (name) {
    case 'button-primary': return <div className="component-demo-stack"><Button type="primary" onClick={() => setValue('示例修改已保存')}>保存修改</Button><p className="component-demo-caption" role="status">{value || '悬停时变亮，按住时加深。'}</p></div>;
    case 'button-default': return <div className="component-demo-stack"><div className="component-demo-actions"><Input aria-label="默认按钮示例筛选条件" value={value} onChange={event => setValue(event.target.value)} placeholder="输入一个筛选条件" /><Button onClick={() => setValue('')}>重置条件</Button></div><p className="component-demo-caption">输入内容后，点击次要操作清空条件。</p></div>;
    case 'input-field': return <div className="component-demo-stack"><label className="component-demo-field" htmlFor="component-member-name">成员姓名<Input id="component-member-name" placeholder="请输入成员姓名" /></label><p className="component-demo-caption">点击或按 Tab 聚焦，移开焦点后恢复默认边框。</p></div>;
    case 'select-field': return <div className="component-demo-stack"><label className="component-demo-field" htmlFor="component-department">所属部门<Select id="component-department" placeholder="请选择部门" allowClear options={departments} /></label><p className="component-demo-caption">展开选项，选择后也可以清除。</p></div>;
    case 'card': return <Card className="component-card"><div className="component-card-content"><h4>研发部概览</h4><p>集中查看部门信息与相关操作。</p><div className="component-card-summary"><span>成员人数</span><strong>12 人</strong></div><Button onClick={() => setValue(value ? '' : '林晓、陈晨、周宁等 12 位成员')}>{value ? '收起成员' : '查看成员'}</Button>{value && <p role="status">{value}</p>}</div></Card>;
    case 'modal': return <div className="component-demo-stack"><Button onClick={() => setOpen(true)}>打开确认弹窗</Button><p className="component-demo-caption" role="status">{value || '打开后可确认、取消，或按 Esc 返回。'}</p><Modal title="调整示例成员部门" centered open={open} onCancel={() => setOpen(false)} onOk={() => { setOpen(false); setValue('已确认本次示例调整'); }} okText="确认调整" cancelText="取消" mask={{ blur: false, closable: true }} styles={modalStyles(token)}><p style={{ margin: 0 }}>确认将示例成员林晓移至产品部？</p></Modal></div>;
    case 'menu': return <div className="component-demo-stack"><Menu className="component-menu" aria-label="组件样式导航示例" mode="inline" selectedKeys={[value || 'overview']} onClick={({ key }) => setValue(key)} items={menuItems} /><p className="component-demo-caption" role="status">当前位置：{menuItems.find(item => item.key === (value || 'overview'))?.label}</p></div>;
    case 'tabs': return <Tabs className="component-tabs" defaultActiveKey="overview" items={[{ key: 'overview', label: '部门概况', children: <p className="component-demo-caption">研发部 · 共 12 位成员，按职责协同工作。</p> }, { key: 'members', label: '成员信息', children: <p className="component-demo-caption">林晓、陈晨、周宁 · 示例成员。</p> }]} />;
    case 'table': return <Table className="component-table" aria-label="组件样式成员表格" size="small" pagination={false} rowKey="name" tableLayout="fixed" dataSource={members} columns={[{ title: '成员姓名', dataIndex: 'name', render: (name: string) => <DesignMember name={name} /> }, { title: '所属部门', dataIndex: 'department' }]} />;
    case 'tag': return <div className="component-demo-stack"><div className="component-demo-tags"><Tag color="blue" variant="filled">研发部</Tag><Tag color="purple" variant="filled">产品部</Tag><Tag color="cyan" variant="filled">运营部</Tag></div><p className="component-demo-caption">浅色分类标签，颜色来自上方扩展色。</p></div>;
    case 'alert': return <div className="component-demo-alerts">{alerts.map(item => <Alert key={item.type} className={`component-alert-${item.type}`} showIcon type={item.type} title={item.title} styles={{ title: { color: token.colorText, fontWeight: 400 } }} />)}</div>;
    case 'badge': return <div className="component-demo-statuses"><Badge status="success" text="同步完成" /><Badge status="warning" text="部分完成" /><Badge status="error" text="同步失败" /><Badge status="processing" text="正在同步" /></div>;
    case 'tooltip': return <div className="component-demo-stack"><Tooltip title="所属部门用于组织归类和成员筛选。" trigger={['hover', 'focus']}><Button>查看字段说明</Button></Tooltip><p className="component-demo-caption">鼠标悬停或按 Tab 聚焦，查看简短解释。</p></div>;
    case 'dropdown': return <div className="component-demo-stack"><Dropdown trigger={['click']} menu={{ items: [{ key: 'overview', label: '查看概览' }, { key: 'members', label: '查看成员' }, { key: 'records', label: '查看记录' }], onClick: ({ key }) => setValue({ overview: '查看概览', members: '查看成员', records: '查看记录' }[key] ?? '') }}><Button>更多操作<DownOutlined /></Button></Dropdown><p className="component-demo-caption" role="status">{value ? `已选择：${value}` : '点击展开，再悬停条目查看背景变化。'}</p></div>;
  }
}

function ComponentEntry({ guideline }: { guideline: typeof guidelines[number] }) {
  const { token } = theme.useToken();
  const [code, setCode] = useState(false);
  const titleId = `component-${guideline.id}-title`;
  const previewId = `component-${guideline.id}-preview`;
  return <article className="component-entry" data-component={guideline.id} aria-labelledby={titleId}>
    <div className="component-explanation"><h3 id={titleId}>{guideline.title}<span>{guideline.component}</span></h3><p>{guideline.purpose}</p><p>{guideline.rules}</p><p className="component-reminder">{guideline.reminder}</p></div>
    <div className="component-example"><div className="component-example-head"><span>{code ? '当前主题 · 样式规则' : '交互示例'}</span><button type="button" className="code-icon" aria-label={`${code ? '收起' : '查看'} ${guideline.title} 代码`} aria-expanded={code} aria-controls={previewId} onClick={() => setCode(!code)}>&lt;/&gt;</button></div>
      <div id={previewId} className={`component-stage${code ? ' is-code' : ''}`}><div className="component-live-example" hidden={code}><ComponentExample name={guideline.id} /></div>{code && <pre>{componentCode(guideline.id, token)}</pre>}</div>
    </div>
  </article>;
}

export default function ComponentGuide() {
  const { token } = theme.useToken();
  return <ConfigProvider theme={guideTheme(token)}><div className="panel component-guide">
    <div className="component-guide-intro" id="note-6"><h3>把用途、规则和交互放在一起看</h3><p>每个组件集中展示完整用法。悬停、按下、聚焦或切换选项，体验同一组件的状态变化；右上角可查看当前主题下的样式规则。</p><p>主色及交互色随上方色彩规则联动，表面、文字和边框沿用各自职责；成功、告警、错误与分类颜色保持原有含义。</p><p>单类组件通过 theme.components 覆盖自身令牌及其使用的通用令牌，需要派生时配置该组件的 algorithm。嵌套 ConfigProvider 默认继承外层主题，只覆盖当前子树中的差异；动态修改 theme 时同步更新该作用域。</p><p>消息、通知与弹窗反馈使用 App 或基于 hook 的 API，并放在对应主题作用域中；直接调用 message.xxx、notification.xxx、Modal.xxx 等静态方法不会自动继承周围上下文。</p><p>调整主题时保留表单、表格、导航、浮层、聚焦与校验的交互语义。优先通过令牌与组件配置表达差异，超出官方主题能力时统一评估设计系统扩展。</p></div>
    {guidelines.map(guideline => <ComponentEntry key={guideline.id} guideline={guideline} />)}
  </div></ConfigProvider>;
}
