import { useState, type CSSProperties } from 'react';
import { Button, Card, Checkbox, Dropdown, Popover, Select, Tabs, theme, type DrawerProps, type GlobalToken } from 'antd';
import { DownOutlined, TeamOutlined } from '@ant-design/icons';
import { EffectEntry, EffectGuide, MemberPreviewDrawer, resolvedEffectToken } from './EffectGuide';

const directions = [
  { value: 'right', label: '从右侧展开' }, { value: 'left', label: '从左侧展开' },
  { value: 'top', label: '从顶部展开' }, { value: 'bottom', label: '从底部展开' },
] as const;
const departmentNames = ['研发部', '产品部', '运营部', '市场部', '销售部', '财务部', '人事部', '行政部', '客户服务部', '质量保障部'];

function shadowCode(token: GlobalToken, selector: string, names: string[]) {
  return names.map(name => {
    const shadow = resolvedEffectToken(token, name);
    return shadow ? `/* ${name} · 当前主题 */\n${selector} {\n  box-shadow: ${shadow};\n}` : `/* ${name} 由对应组件内部生成，沿用组件默认样式。 */`;
  }).join('\n\n');
}

function BatchToolbar() {
  const { token } = theme.useToken();
  const [selected, setSelected] = useState(['林晓', '陈晨']);
  return <div className="shadow-batch-scene">
    <span className="effect-caption">成员列表</span>
    {['林晓', '陈晨'].map(name => <div className="shadow-member-line" key={name}><Checkbox checked={selected.includes(name)} onChange={event => setSelected(previous => event.target.checked ? [...previous, name] : previous.filter(item => item !== name))}>{name}</Checkbox><span className="effect-caption">研发部</span></div>)}
    {!!selected.length && <div className="shadow-batch-toolbar" style={{ boxShadow: token.boxShadowTertiary }}><span role="status">已选 {selected.length} 人</span><Button type="text" size="small" onClick={() => setSelected([])}>取消选择</Button></div>}
    <p className="effect-caption">勾选成员后，操作条轻微浮在列表之上。</p>
  </div>;
}

function PopupExample() {
  const [selected, setSelected] = useState('');
  return <div className="effect-demo-stack"><Dropdown trigger={['click']} menu={{ items: [{ key: '资料', label: '查看成员资料' }, { key: '部门', label: '查看所属部门' }], onClick: ({ key }) => setSelected(key) }}><Button>成员更多操作<DownOutlined /></Button></Dropdown><p className="effect-caption" role="status">{selected ? `已选择查看${selected}` : '点击展开菜单，观察浮层与底板的关系。'}</p></div>;
}

function CardExample() {
  const { token } = theme.useToken();
  const [expanded, setExpanded] = useState(false);
  return <Card hoverable className="shadow-action-card" style={{ '--effect-card-shadow': resolvedEffectToken(token, 'boxShadowCard') } as CSSProperties}>
    <div className="effect-demo-stack"><h4><TeamOutlined aria-hidden />研发部</h4><p>12 位成员 · 部门入口</p><Button type="link" onClick={() => setExpanded(!expanded)}>{expanded ? '收起部门概况' : '查看部门概况'}</Button>{expanded && <p role="status">负责组织服务研发与技术支持。</p>}</div>
  </Card>;
}

function DirectionalDrawer() {
  const [placement, setPlacement] = useState<NonNullable<DrawerProps['placement']>>('right');
  const [open, setOpen] = useState(false);
  return <div className="effect-demo-stack"><label className="effect-demo-field" htmlFor="shadow-drawer-direction">展开方向<Select id="shadow-drawer-direction" value={placement} onChange={setPlacement} options={[...directions]} /></label><Button onClick={() => setOpen(true)}>打开方向阴影示例</Button><p className="effect-caption">阴影出现在抽屉与下层内容接壤的一侧。</p><MemberPreviewDrawer open={open} onClose={() => setOpen(false)} placement={placement} title="成员详情 · 方向阴影" /></div>;
}

function OverflowTabs() {
  const [activeKey, setActiveKey] = useState('0');
  return <div className="effect-demo-stack"><div className="shadow-overflow-tabs"><Tabs aria-label="部门溢出阴影示例" activeKey={activeKey} onChange={setActiveKey} items={departmentNames.map((name, index) => ({ key: String(index), label: name, children: <p className="effect-caption">{name} · 部门概况</p> }))} /></div><div className="effect-demo-actions"><Button onClick={() => setActiveKey('0')}>首个部门</Button><Button onClick={() => setActiveKey(String(departmentNames.length - 1))}>最后部门</Button></div><p className="effect-caption">横向滚动页签，或切换首尾部门，观察边缘阴影随隐藏内容变化。</p></div>;
}

function ShadowComposition() {
  const [member, setMember] = useState('林晓');
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState('');
  return <div className="effect-composition"><h3>在成员管理中组合使用</h3><p>列表承载持续展示的内容，菜单承载临时操作，抽屉承载成员详情。</p><div className="effect-composition-grid">
    <div className="shadow-composition-paper"><header><h4>研发部成员</h4><span className="effect-caption">普通列表 · 边框分层</span></header>{['林晓', '陈晨'].map(name => <div className="shadow-member-line" key={name}><span>{name}</span><Dropdown trigger={['click']} menu={{ items: [{ key: 'details', label: '查看成员资料' }, { key: 'department', label: '查看所属部门' }], onClick: ({ key }) => { setMember(name); if (key === 'details') setOpen(true); else setResult(`${name} · 研发部`); } }}><Button aria-label={`${name}的更多操作`}>更多<DownOutlined /></Button></Dropdown></div>)}<p className="effect-caption" role="status">{result || '从“更多”菜单打开成员资料。'}</p></div>
    <ol className="effect-usage-list"><li><strong>列表：</strong>使用边框与内容表面保持清晰，不叠加装饰阴影。</li><li><strong>菜单：</strong>使用标准浮层阴影，说明它临时覆盖在列表上。</li><li><strong>详情：</strong>使用抽屉方向阴影，表达详情与原列表的前后关系。</li></ol>
  </div><MemberPreviewDrawer name={member} open={open} onClose={() => setOpen(false)} title="成员详情 · 组合示例" /></div>;
}

function ShadowExamples() {
  const { token } = theme.useToken();
  return <>
    <div className="effect-guide-intro" id="note-4"><h3>按悬浮关系选择阴影</h3><p>普通卡片、表格与表单优先通过边框和表面色区分层级。内容真正悬浮于当前界面之上，或确实需要抬升时，再使用对应阴影。</p><p>阴影由 colorShadow 派生，读取当前主题并适配其表面；浮层的定位、箭头、方向与关闭交互交给组件处理。</p></div>
    <EffectEntry id="shadow-flat" title="普通内容 · 无阴影" tokens="box-shadow: none" usage="用在部门概览、成员列表和常规表单中。持续展示的内容依靠边框与背景组织，无需全部抬升。" rule="先看无阴影是否已经足够清晰，再判断是否需要悬浮层级。" code={`.department-summary {\n  background: ${token.colorBgContainer}; /* colorBgContainer */\n  border: 1px solid ${token.colorBorderSecondary}; /* colorBorderSecondary */\n  box-shadow: none;\n}`}>
      <Card className="shadow-flat-card"><div className="effect-demo-stack"><h4>研发部概览</h4><p>成员人数：12 人</p><span className="effect-caption">常规内容表面 · 无阴影</span></div></Card>
    </EffectEntry>
    <EffectEntry id="shadow-tertiary" title="轻型抬升" tokens="boxShadowTertiary" usage="用于轻微脱离底板的临时表面，例如悬浮在成员列表上的批量操作条。" rule="轻阴影表达有限的抬升，避免与菜单、弹窗争夺层级。" code={shadowCode(token, '.batch-toolbar', ['boxShadowTertiary'])}><BatchToolbar /></EffectEntry>
    <EffectEntry id="shadow-popup" title="标准浮层" tokens="boxShadow / boxShadowSecondary" usage="用于下拉菜单、弹出层与弹窗。它们临时覆盖当前内容，操作结束后关闭。" rule="这两个令牌在当前默认主题下可同值，按组件既有职责使用，不额外叠加阴影。" code={shadowCode(token, '.floating-surface', ['boxShadow', 'boxShadowSecondary'])}><PopupExample /></EffectEntry>
    <EffectEntry id="shadow-card" title="卡片按需抬升" tokens="boxShadowCard" usage="用于需要与容器区分的卡片，例如可点击的部门入口。悬停或键盘聚焦其操作时，突出当前对象。" rule="普通信息卡片保持扁平；只对确实可操作、需要强调的卡片启用抬升。" code={`${shadowCode(token, '.department-entry:hover, .department-entry:focus-within', ['boxShadowCard'])}\n\n/* Card hoverable 提供悬停效果；聚焦内部操作时显示相同阴影。 */`}><CardExample /></EffectEntry>
    <EffectEntry id="shadow-drawer" title="抽屉方向阴影" tokens="boxShadowDrawerRight / Left / Up / Down" usage="用于贴着屏幕边缘展开的成员详情、筛选面板与补充信息。根据展开方向，在与内容接壤的一侧形成阴影。" rule="方向由 Drawer 的 placement 决定，避免给四个方向套用同一投影。" code={`${shadowCode(token, '.drawer-wrapper', ['boxShadowDrawerRight', 'boxShadowDrawerLeft', 'boxShadowDrawerUp', 'boxShadowDrawerDown'])}\n\n/* Drawer placement="right" | "left" | "top" | "bottom"，由组件选择方向。 */`}><DirectionalDrawer /></EffectEntry>
    <EffectEntry id="shadow-overflow" title="可滚动内容的边缘阴影" tokens="boxShadowTabsOverflow*" usage="用于页签超出容器的情况，提示左侧、右侧或其他边缘之外还有内容。" rule="只在对应边缘确实有隐藏内容时出现，滚动到尽头后由组件更新。" code={`${shadowCode(token, '.tabs-overflow-edge', ['boxShadowTabsOverflowLeft', 'boxShadowTabsOverflowRight', 'boxShadowTabsOverflowTop', 'boxShadowTabsOverflowBottom'])}\n\n/* 使用真实 Tabs，由组件测量溢出范围并更新阴影。 */`}><OverflowTabs /></EffectEntry>
    <EffectEntry id="shadow-arrow" title="浮层箭头的局部阴影" tokens="boxShadowPopoverArrow" usage="原文用它说明 Tooltip / Popover 三角指针上的局部阴影。箭头指向触发对象，帮助理解补充信息的来源。" rule="箭头的具体绘制跟随当前组件版本，不把箭头阴影直接套到整个浮层上。" code={`${shadowCode(token, '.popover-arrow', ['boxShadowPopoverArrow'])}\n\n/* Popover arrow；箭头及浮层本体均由框架绘制与定位。 */`}><div className="effect-demo-stack"><Popover title="研发部说明" content="负责组织服务研发与技术支持。" arrow placement="top" trigger={['click']}><Button>查看部门说明</Button></Popover><p className="effect-caption">打开气泡卡片，观察本体与指向按钮的三角箭头。</p></div></EffectEntry>
    <ShadowComposition />
  </>;
}

export default function ShadowGuide() {
  return <EffectGuide className="shadow-guide"><ShadowExamples /></EffectGuide>;
}
