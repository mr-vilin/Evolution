// 轻量本地 SVG 图表，无远程数据、字体或图表运行时；仅案例路由引用。
export const monthlySales = [42, 58, 45, 71, 62, 87, 69, 92, 76, 98, 83, 109];
export function DemoChart({ values = monthlySales, label, kind = 'bar', secondary }: { values?: number[]; label: string; kind?: 'bar' | 'line'; secondary?: number[] }) {
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => `${34 + index * 37},${165 - value / max * 140}`).join(' ');
  return <svg className="demo-chart" viewBox="0 0 480 205" role="img" aria-label={label}>
    <title>{label}</title>
    {[25, 60, 95, 130, 165].map(y => <line key={y} x1="24" x2="470" y1={y} y2={y} stroke="#f0f0f0" />)}
    {kind === 'line' ? <><polygon points={`34,165 ${points} ${34 + (values.length - 1) * 37},165`} fill="#e6f4ff" /><polyline points={points} fill="none" stroke="#1677ff" strokeWidth="3" /></> : values.map((value, index) => <rect key={index} x={24 + index * 37} y={165 - value / max * 140} width="22" height={value / max * 140} fill="#69b1ff"><title>{index + 1}月：{value}</title></rect>)}
    {secondary && <polyline points={secondary.map((value, index) => `${34 + index * 37},${165 - value / max * 140}`).join(' ')} fill="none" stroke="#13c2c2" strokeWidth="2" />}
    {values.map((_, index) => <text key={index} x={34 + index * 37} y="191" textAnchor="middle" fontSize="10" fill="#8c8c8c">{index + 1}月</text>)}
  </svg>;
}
export function DemoPie({ label, values, names }: { label: string; values: number[]; names: string[] }) {
  const sum = values.reduce((total, value) => total + value, 0);
  let offset = 0;
  const colors = ['#1677ff', '#13c2c2', '#52c41a', '#faad14', '#fa8c16', '#722ed1'];
  return <div className="demo-pie-layout"><svg className="demo-donut" viewBox="0 0 180 180" role="img" aria-label={label}><title>{label}</title>{values.map((value, i) => { const start = offset; const length = value / sum * 408.4; offset += length; return <circle key={i} cx="90" cy="90" r="65" fill="none" stroke={colors[i]} strokeWidth="24" strokeDasharray={`${length} ${408.4 - length}`} strokeDashoffset={-start} transform="rotate(-90 90 90)"><title>{names[i]}：{value} 元</title></circle>; })}<text x="90" y="85" textAnchor="middle" fill="#8c8c8c" fontSize="12">销售额</text><text x="90" y="110" textAnchor="middle" fontSize="20">¥ {sum.toLocaleString()}</text></svg><ul>{names.map((name, i) => <li key={name}><span style={{ color: colors[i] }}>●</span> {name} <strong>{Math.round(values[i] / sum * 100)}%</strong></li>)}</ul></div>;
}
export function DemoRadar() {
  const axis = ['引用', '口碑', '产量', '贡献', '热度', '性能'];
  const point = (i: number, radius: number) => `${140 + Math.sin(i * Math.PI / 3) * radius},${135 - Math.cos(i * Math.PI / 3) * radius}`;
  return <svg className="demo-chart" viewBox="0 0 280 275" role="img" aria-label="团队协作六维指数"><title>团队协作六维指数</title>{[30, 60, 90].map(radius => <polygon key={radius} points={axis.map((_, i) => point(i, radius)).join(' ')} fill="none" stroke="#e8e8e8" />)}{axis.map((label, i) => { const [x, y] = point(i, 115).split(','); return <g key={label}><line x1="140" y1="135" x2={point(i, 90).split(',')[0]} y2={point(i, 90).split(',')[1]} stroke="#e8e8e8" /><text x={x} y={y} textAnchor="middle" fontSize="12" fill="#8c8c8c">{label}</text></g>; })}<polygon points={[80, 55, 72, 85, 61, 78].map((radius, i) => point(i, radius)).join(' ')} fill="#1677ff33" stroke="#1677ff" strokeWidth="2" /><polygon points={[55, 77, 58, 62, 84, 60].map((radius, i) => point(i, radius)).join(' ')} fill="#13c2c233" stroke="#13c2c2" strokeWidth="2" /></svg>;
}
export function DemoDonut({ label, percent }: { label: string; percent: number }) {
  return <svg className="demo-donut" viewBox="0 0 180 180" role="img" aria-label={`${label} ${percent}%`}><title>{label} {percent}%</title><circle cx="90" cy="90" r="65" fill="none" stroke="#f0f0f0" strokeWidth="20" /><circle cx="90" cy="90" r="65" fill="none" stroke="#1677ff" strokeWidth="20" strokeDasharray={`${percent * 4.084} 408.4`} transform="rotate(-90 90 90)" /><text x="90" y="90" textAnchor="middle" fontSize="28">{percent}%</text><text x="90" y="115" textAnchor="middle" fill="#8c8c8c" fontSize="13">{label}</text></svg>;
}
