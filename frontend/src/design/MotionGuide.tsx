import { useState, type CSSProperties } from 'react';
import { Button, Collapse, Input, Select, theme, type GlobalToken } from 'antd';
import { EffectEntry, EffectGuide, MemberPreviewDrawer } from './EffectGuide';

const durationNames = ['motionDurationFast', 'motionDurationMid', 'motionDurationSlow'] as const;
const easingNames = ['motionEaseInOut', 'motionEaseOut', 'motionEaseOutCirc', 'motionEaseOutBack'] as const;
export const motionStyleCount = durationNames.length + easingNames.length;
const easingLabels = ['平缓开始与结束', '减速停下', '更明显地减速', '轻微越过后回弹'];

function motionStyle(token: GlobalToken): CSSProperties {
  return { '--effect-fast': token.motionDurationFast, '--effect-ease': token.motionEaseInOut, '--effect-focus-shadow': `0 0 0 ${token.controlOutlineWidth}px ${token.controlOutline}` } as CSSProperties;
}

function FastStateExample() {
  const { token } = theme.useToken();
  const [selected, setSelected] = useState(false);
  return <div className="effect-demo-stack" style={motionStyle(token)}><button type="button" className="motion-state-control" aria-pressed={selected} onClick={() => setSelected(!selected)}>{selected ? '已选中林晓' : '选择林晓'}</button><p className="effect-caption" role="status">悬停、按住或按 Tab 聚焦，观察颜色与焦点反馈；点击切换选中状态。</p></div>;
}

function FilterExample() {
  const [department, setDepartment] = useState('all');
  const [name, setName] = useState('');
  const [result, setResult] = useState('');
  return <div className="effect-demo-stack"><Collapse className="motion-filter" items={[{ key: 'filters', label: '更多筛选条件', children: <div className="effect-demo-stack"><label className="effect-demo-field" htmlFor="motion-filter-name">成员姓名<Input id="motion-filter-name" placeholder="输入示例姓名" value={name} onChange={event => setName(event.target.value)} /></label><label className="effect-demo-field" htmlFor="motion-filter-department">所属部门<Select id="motion-filter-department" value={department} onChange={setDepartment} options={[{ value: 'all', label: '全部部门' }, { value: 'engineering', label: '研发部' }]} /></label><Button onClick={() => setResult(`当前条件：${name.trim() || '全部成员'} · ${department === 'all' ? '全部部门' : '研发部'}`)}>应用示例筛选</Button></div> }]} /><p className="effect-caption" role="status">{result || '点击标题展开与收起，在同一组件内体验高度和透明度过渡。'}</p></div>;
}

function SlowSurfaceExample() {
  const [open, setOpen] = useState(false);
  return <div className="effect-demo-stack"><Button onClick={() => setOpen(true)}>打开动画详情抽屉</Button><p className="effect-caption">观察抽屉进入与退出；关闭后回到原来的操作位置。</p><MemberPreviewDrawer open={open} onClose={() => setOpen(false)} title="成员详情 · 表面动画" /></div>;
}

function MotionComparison({ easing = false }: { easing?: boolean }) {
  const { token } = theme.useToken();
  const [replay, setReplay] = useState(0);
  const names = easing ? easingNames : durationNames;
  return <div className="effect-motion-comparison"><div className="effect-comparison-head"><h3>{easing ? '相同时长，对照不同缓动' : '相同距离，对照三档时长'}</h3><Button onClick={() => setReplay(value => value + 1)}>{replay ? '重新播放' : '同时播放'}</Button></div><p className="effect-caption">{easing ? `统一使用 ${token.motionDurationSlow}，观察开始、减速与停下的差别。` : '每条轨道只播放一次单程，移动时间与右侧标注一致。'}</p>
    <div className="effect-motion-tracks">{names.map((name, index) => <div className="effect-motion-row" key={name}><div className="effect-motion-label"><code>{name}</code>{easing && <span>{easingLabels[index]}</span>}</div><div className="effect-motion-track"><div key={replay} className={`effect-motion-runner${replay ? ' is-playing' : ''}`} data-duration={easing ? token.motionDurationSlow : token[durationNames[index]]} style={{ animationDuration: easing ? token.motionDurationSlow : token[durationNames[index]], animationTimingFunction: easing ? token[easingNames[index]] : token.motionEaseInOut }}><span /></div></div><span className="effect-motion-duration">{easing ? token.motionDurationSlow : token[durationNames[index]]}</span></div>)}</div>
    <p className="effect-reduced-note">已开启减少动态效果，直接显示变化结果。</p>
  </div>;
}

function MotionExamples() {
  const { token } = theme.useToken();
  return <>
    <div className="effect-guide-intro"><h3>按变化范围选择时长</h3><p>局部状态快速反馈，组件内部变化使用中速，较大表面的进出使用慢速。动画帮助用户看清状态与位置变化，结束后保留明确结果。</p><p>原文的默认时长为 100 / 200 / 300ms，示例读取当前主题的实际值。真实组件沿用框架的动画机制，开启减少动态效果时直接呈现结果。</p></div>
    <EffectEntry id="motion-fast" title="快速 · 状态反馈" tokens={`motionDurationFast · ${token.motionDurationFast}`} usage="用于悬停、聚焦、按下等小范围状态变化，让用户立即知道控件正在响应。" rule="只过渡与状态相关的颜色、边框与焦点，不让周围内容移动。" code={`.member-choice {\n  transition: background-color ${token.motionDurationFast} ${token.motionEaseInOut},\n    border-color ${token.motionDurationFast} ${token.motionEaseInOut},\n    color ${token.motionDurationFast} ${token.motionEaseInOut},\n    box-shadow ${token.motionDurationFast} ${token.motionEaseInOut};\n}\n/* motionDurationFast + motionEaseInOut；颜色读取主题职责。 */`}><FastStateExample /></EffectEntry>
    <EffectEntry id="motion-mid" title="中速 · 组件内部变化" tokens={`motionDurationMid · ${token.motionDurationMid}`} usage="用于折叠、展开、淡入淡出，示例以筛选区演示展开与收起，仅用于观察动画；业务列表的筛选与搜索布局以「表格规范」为准。" rule="变化范围仍属于同一个组件，保持上下文连续；无更具体约定时优先使用中速与默认缓动。" code={`.filter-collapse {\n  transition: height ${token.motionDurationMid} ${token.motionEaseInOut},\n    opacity ${token.motionDurationMid} ${token.motionEaseInOut};\n}\n/* motionDurationMid + motionEaseInOut。\n   示例使用 Collapse，由框架测量内容高度并处理折叠。 */`}><FilterExample /></EffectEntry>
    <EffectEntry id="motion-slow" title="慢速 · 表面进出" tokens={`motionDurationSlow · ${token.motionDurationSlow}`} usage="用于较大的表面变化，例如成员详情抽屉滑入与退出。弹窗等覆盖层同样需要清楚表达进入、离开与返回。" rule="真实 Drawer、Modal 沿用各自的进入与退出动画，不统一覆盖所有组件的时长。" code={`/* Drawer 的表面进出使用 motionDurationSlow：${token.motionDurationSlow}。\n   位置、遮罩、焦点与关闭由组件管理。 */\n<Drawer open={open} onClose={() => setOpen(false)} placement="right" />`}><SlowSurfaceExample /></EffectEntry>
    <div className="effect-comparison-section"><MotionComparison /></div>
    <div className="effect-comparison-section"><MotionComparison easing /><div className="effect-easing-rules"><p>优先使用 <code>motionEaseInOut</code>。减速与回弹等曲线按组件已有用途选取，不自行编造 cubic-bezier。</p><p className="effect-caption">缓动采用当前版本实际可用的命名令牌；原文列举的 motionEaseIn 未作为本版本的独立令牌提供，未匹配到更具体缓动时使用 motionEaseInOut。</p><pre>{easingNames.map(name => `${name}: ${token[name]}`).join('\n')}</pre></div></div>
  </>;
}

export default function MotionGuide() {
  return <EffectGuide className="motion-guide"><MotionExamples /></EffectGuide>;
}
