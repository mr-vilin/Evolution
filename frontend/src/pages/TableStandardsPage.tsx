import type { ReactNode } from 'react';
import { ConfigProvider, Tag, theme } from 'antd';
import DesignSectionNav from '../design/DesignSectionNav';
import TableDemo from '../design/TableDemo';
import TableHeightDemo from '../design/TableHeightDemo';
import { statusColors } from '../design/tableStandardsModel';
import '../design/standards.css';
import '../design/table-standards.css';

const sections = [['table-height', '高度与滚动'], ['table-columns', '列布局'], ['table-cells', '单元格与操作'], ['table-controlled', '筛选与排序'], ['table-filter', '工具栏与筛选'], ['table-rules', 'Do Or Not Do']];
const comparisons = [
  ['高度与滚动', '首屏空间同时满足 60% 比例与三行预算；不足时整块吸顶，一屏也不足时自然滚动。', '只让表头吸顶，将工具栏或分页留在屏幕之外；按记录多少判断模式。', '工具栏 → 表头 → 表体内部滚动 → 分页', '页面滚动 → 工具栏消失 → 分页落在屏幕外'],
  ['筛选入口', '左侧最多四项主要条件，其余条件进入各自表头；可选新增紧邻刷新左侧，搜索始终在右侧。', '持续往工具栏增加第 5、6 项，为同一字段重复添加入口，或因新增能力改变搜索位置。', '全部状态 · 全部类型 · 全部负责人 · 全部来源 · 新增（可选） · 刷新 ｜ 搜索', '状态 · 类型 · 负责人 · 来源 · 部门 · 优先级 · …'],
  ['固定与识别', '名称固定左侧，时间集中靠后，操作通常固定右侧；极窄容器让操作列参与横向滚动，技术 ID 放到复制入口。', '首列展示无关 UUID，隐藏名称，或固定区域互相覆盖中间数据。', '名称（复制 ID） ｜ 业务字段 ｜ 创建／更新时间 ｜ 操作', 'UUID ｜ 更新时间 ｜ 操作 ｜ 名称'],
  ['内容与操作', '状态带中文 Tag，缺失为 -、零值保留；不超过三个操作时全部显示，超过三个时使用两个高频图标加更多菜单。', '只靠颜色表达状态，把 0 当空值，或把所有操作平铺成文字链接。', '已完成 ｜ 0 ｜ - ｜ 查看 · 编辑 · …', '绿色圆点 ｜ 空白 ｜ 查看 编辑 重发 删除 复制'],
  ['数值与状态', '按原始数值排序，空值始终置底，同值顺序稳定；筛选与排序始终受控。', '按字符串字典序排序、只重排当前页，或重置后箭头和实际结果不一致。', '升序：0 → 2 → 10 → 100 → -', '错误顺序：- → 0 → 10 → 100 → 2'],
];
function Section({ id, alias, index, title, children }: { id: string; alias?: string; index: string; title: string; children: ReactNode }) {
  return <section id={id}>{alias && <span id={alias} className="table-section-alias" aria-hidden="true" />}<header className="section-head"><span className="index">{index}</span><h2>{title}</h2></header>{children}</section>;
}
export default function TableStandardsPage() {
  const { token } = theme.useToken();
  return <ConfigProvider avatar={{ style: { fontSize: 14 } }} theme={{ components: {
    Checkbox: { borderRadiusSM: 2 },
    Select: { borderRadiusSM: 6, optionSelectedFontWeight: 400, optionSelectedColor: token.colorPrimary },
    Tooltip: { borderRadius: 4 },
    Form: { labelColor: token.colorTextSecondary },
  } }}><div className="design-standards table-standards"><main className="design-main">
    <header className="hero"><div><div className="eyebrow">TABLE REFERENCE</div><h1>让表格，清晰有序。</h1><p>统一容器高度、列布局、内容表达与查询交互。以下示例均为本地数据，可搜索、筛选、排序和编辑；时间按北京时间（UTC+8）展示。</p></div></header>
    <DesignSectionNav sections={sections} />
    <Section id="table-height" index="01" title="高度与滚动"><div className="panel table-guide-panel"><div className="table-guide-copy"><h3>先测量空间，再选择滚动模式</h3><p>白底容器包含标题、工具栏、表头、表体、横向滚动条与分页。默认模式让完整容器留在首屏，数据行在表体内滚动；少量记录自然收缩。</p><dl className="table-formulas"><div><dt>一屏容量 H</dt><dd>可见高度 V − 固定顶栏 T − 顶部留白 Gt − 底部留白 Gb</dd></div><div><dt>首屏空间 A</dt><dd>可见高度 V − 底部留白 Gb − 表格初始顶部 Y</dd></div></dl><p>最小预算 M = 标题、工具栏、表头、分页、边框与横向滚动条的实际高度 + 三行完整记录的高度。A ≥ 60% × H 且 A ≥ M 才使用默认模式；否则在 H ≥ M 时按 H 布局，页面先滚动，整块容器在顶栏下方留白处吸顶。H &lt; M 时取消吸顶，以 M 为最大高度自然滚动。少量记录自然收缩，模式不按记录数量改变；吸顶保留占位，滚到边界后仍可离开表格。</p><p>模拟区顶栏 48px，上下留白各 16px；业务页面应读取实际布局。窗口、缩放、侧栏、摘要及工具栏换行后重新测量，滚动本身不改变模式。</p></div><TableHeightDemo /></div></Section>
    <Section id="table-columns" index="02" title="列布局"><div className="panel table-guide-copy"><h3>名称在前，时间靠后，首尾固定</h3><div className="table-column-map" aria-label="列顺序示意"><span>名称 · 固定左侧<br />附复制 ID</span><span>业务字段<br />中间区域横向滚动</span><span>业务时间 → 创建时间 → 更新时间</span><span>操作<br />固定右侧</span></div><ul><li>只在确有批量操作需求时增加固定勾选列；无关数据库 ID、UUID 不独立占列。工号、单号等业务识别字段可以展示。</li><li>长文本省略后，悬停或键盘聚焦可读完整内容。表格复制按钮使用无边框图标，默认图标色为控件边框色（colorBorder，默认 #D9D9D9），弱化辅助操作；悬停或键盘聚焦时使用主题色，保留中文提示与复制成功／失败反馈。复制按钮复制真实示例 ID，成功写入剪贴板后才提示成功；失败时提供手动复制。</li><li>所有列有唯一且稳定的 column.key，记录使用独立 rowKey。窄屏名称列收紧至 96px，操作列为 96px；当可见宽度不足以容纳首尾固定列与至少 96px 的中间区域时，保留名称固定，操作列随横向滚动访问。按钮和 8px 间距保持完整，页面本身不横向滚动。</li></ul><p>在下方表格内横向滚动，观察名称与操作两列的位置。</p></div></Section>
    <Section id="table-cells" index="03" title="单元格与操作"><div className="panel table-guide-copy"><h3>状态、空值和进度各有明确表达</h3><div className="table-status-samples">{Object.entries(statusColors).map(([label, color]) => <Tag key={label} color={color}>{label}</Tag>)}</div><ul><li>表格内所有时间（包括业务时间、创建时间、更新时间）统一使用 12px／20px、400 字重与说明灰（colorTextSecondary，默认 #595959）；按页面时区以 YYYY-MM-DD HH:mm:ss 展示，缺失显示 -，时间列均支持排序。</li><li>表格状态列使用带中文文字的语义 Tag：成功、进行中、告警、失败；未开始、无效与未知分别使用中性 Tag，不相互推断。页面级重要反馈继续使用 Badge 或 Alert。</li><li>人员列使用圆形头像加姓名，头像内文字统一为 14px，头像与姓名间隔 4px；没有头像时，中文取首字，英文取首单词，超过 5 个字母时显示前 3 个字母。</li><li>缺失值、空字符串、纯空白统一为半角 -。有效 0、0% 保留，布尔值使用真实业务文案。未完成进度以进度条和百分比呈现，100% 使用完成图标，无需重复显示百分比；没有依据时显示 -。本页任务示例的已完成对应 100%，未开始对应 0%，进行中及部分完成对应中间进度，无依据的状态不补造进度。</li><li>行操作使用有中文 Tooltip 和可访问名称的图标按钮；不超过三个操作时全部显示，超过三个时使用「两个高频图标 + 更多操作」。更多菜单包含图标与中文名称，删除标为危险操作并确认。</li><li>下方示例提供查看、编辑、重发、删除四项操作；前两项在行内，后两项进入更多菜单。新增、编辑、查看、删除确认与复制失败提示均由框架垂直居中，保留焦点与关闭交互。</li></ul></div></Section>
    <Section id="table-controlled" index="04" title="筛选与排序"><div className="panel table-guide-copy"><h3>查询状态只有一个来源</h3><p>搜索名称或负责人，与不同字段的筛选取交集；同一字段多选取并集。先处理完整数据源的搜索与筛选，再按唯一排序列排序，最后分页。所有筛选列始终传入 filteredValue，所有排序列始终传入 sortOrder，空状态均为 null。</p><p>数量、进度按真实数值比较；时间按统一格式的实际先后排序。升降序均将缺失值置底，同值保持基准顺序；取消排序恢复基准顺序。数字形态的 ID、手机号和工号属于标识，不自动按数值排序。</p><p>切换搜索、筛选或排序都返回第一页；翻页与刷新保留查询条件，结果缩减时校正页码。可在下方统一示例中直接观察筛选状态、排序箭头与数据变化。</p></div></Section>
    <Section id="table-filter" alias="table-create" index="05" title="工具栏与筛选"><div className="table-section-intro"><p>左侧按频率放置状态、类型、负责人、来源四项筛选，刷新位于组末；支持新增时，在刷新左侧显示“新增”，不支持时省略，其他布局一致。右侧始终搜索名称或负责人，部门与优先级进入对应表头，不另设“更多筛选”。</p><p>窄屏按筛选、操作、搜索的顺序换行，新增与刷新始终相邻。新增只添加本地示例记录并返回第一页，保留查询条件，不符合条件时提示暂不显示；高度模拟区的基础数量只控制原始样本，新增记录额外计入列表，切换数量保留本次新增、编辑和删除结果。刷新保留当前搜索、筛选、排序和有效页码。</p></div><TableDemo /></Section>
    <Section id="table-rules" index="06" title="Do Or Not Do"><div className="panel closing-rules"><table className="rules-table" aria-label="表格应该与不要对照"><thead><tr><th><span className="rule-verdict is-do">✓</span>应该</th><th><span className="rule-verdict is-dont">×</span>不要</th></tr></thead><tbody>{comparisons.map(([topic, good, bad, goodExample, badExample]) => <tr key={topic}><td><span className="rule-mobile-label"><span className="rule-verdict is-do">✓</span>应该</span><h3>{topic}</h3><p>{good}</p><div className="table-rule-diagram">{goodExample}</div></td><td><span className="rule-mobile-label"><span className="rule-verdict is-dont">×</span>不要</span><h3>{topic}</h3><p>{bad}</p><div className="table-rule-diagram">{badExample}</div></td></tr>)}</tbody></table></div></Section>
    <footer className="page-foot"><span>Ant Design · 表格规范</span><span>示例交互仅作用于本地数据</span></footer>
  </main></div></ConfigProvider>;
}
