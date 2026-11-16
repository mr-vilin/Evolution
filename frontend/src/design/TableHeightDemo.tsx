import { useEffect, useRef, useState } from 'react';
import { Button, Select, Slider, Tag } from 'antd';
import TableDemo from './TableDemo';
import { tableCapacity } from './tableStandardsModel';

export default function TableHeightDemo() {
  const viewportRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const markerRef = useRef<HTMLDivElement>(null);
  const [summaryPercent, setSummaryPercent] = useState(20);
  const [recordLimit, setRecordLimit] = useState(36);
  const [capacity, setCapacity] = useState({ ...tableCapacity(640, 48, 16, 16, 176), viewport: 640, top: 48 });

  useEffect(() => {
    const viewport = viewportRef.current!;
    const header = headerRef.current!;
    const summary = summaryRef.current!;
    const marker = markerRef.current!;
    let frame = 0;
    const measure = () => {
      const full = Math.max(0, viewport.clientHeight - header.offsetHeight - 32);
      summary.style.height = `${full * summaryPercent / 100}px`;
      // 加回 scrollTop，保持初始位置口径，模式不随滚动来回切换。
      const initialY = marker.getBoundingClientRect().top - viewport.getBoundingClientRect().top - viewport.clientTop + viewport.scrollTop;
      const next = { ...tableCapacity(viewport.clientHeight, header.offsetHeight, 16, 16, initialY), viewport: viewport.clientHeight, top: header.offsetHeight };
      setCapacity(previous => Object.keys(next).every(key => next[key as keyof typeof next] === previous[key as keyof typeof next]) ? previous : next);
    };
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    const observer = new ResizeObserver(schedule);
    observer.observe(viewport); observer.observe(header); observer.observe(summary);
    window.addEventListener('resize', schedule);
    viewport.scrollTop = 0;
    measure();
    return () => { observer.disconnect(); cancelAnimationFrame(frame); window.removeEventListener('resize', schedule); };
  }, [summaryPercent]);

  return <div className="table-height-demo">
    <div className="table-height-controls"><label htmlFor="table-summary-height">上方摘要占一屏容量：{summaryPercent}%<Slider id="table-summary-height" min={0} max={70} step={1} value={summaryPercent} onChange={setSummaryPercent} /></label><div className="table-control-buttons"><Button onClick={() => setSummaryPercent(20)}>常规 80%</Button><Button onClick={() => setSummaryPercent(40)}>临界 60%</Button><Button onClick={() => setSummaryPercent(41)}>不足 60%</Button><Button onClick={() => setSummaryPercent(70)}>较长摘要</Button></div><label>记录数量<Select aria-label="高度示例记录数量" value={recordLimit} options={[{ value: 36, label: '36 条' }, { value: 2, label: '2 条' }, { value: 0, label: '0 条' }]} onChange={setRecordLimit} /></label></div>
    <div className="table-height-readout" role="status"><Tag color={capacity.exceptional ? 'warning' : 'processing'}>{capacity.exceptional ? '例外模式 · 页面先滚动，整块表格再吸顶' : '默认模式 · 首屏容纳'}</Tag><span>V {capacity.viewport}px · H {Math.round(capacity.full)}px · A {Math.round(capacity.available)}px · A/H {(capacity.ratio * 100).toFixed(1)}%</span></div>
    <div ref={viewportRef} className="table-workspace" tabIndex={0} aria-label="可滚动的模拟工作区">
      <div ref={headerRef} className="table-workspace-header">模拟工作区 · 固定顶栏</div>
      <div className="table-workspace-content">
        <div ref={summaryRef} className="table-workspace-summary"><div><strong>上方摘要区域</strong><p>调整摘要高度，再向下滚动观察表格。可用空间取决于布局，与记录多少无关。</p></div></div>
        <div ref={markerRef} className="table-height-marker" />
        <div className="table-height-track">
          <div className={capacity.exceptional ? 'table-height-sticky' : ''} style={{ top: capacity.top + 16 }}>
            <TableDemo maxHeight={capacity.maxHeight} recordLimit={recordLimit} compact />
          </div>
          {capacity.exceptional && <div aria-hidden style={{ height: capacity.full * 0.6 }} />}
        </div>
        <div className="table-workspace-after"><strong>表格之后的内容</strong><p>继续滚动可以离开表格；向上滚动可以返回摘要。也可聚焦工作区后使用方向键、Page Up / Page Down。</p><Button onClick={() => viewportRef.current?.scrollTo({ top: 0, behavior: 'instant' })}>返回摘要</Button></div>
      </div>
    </div>
  </div>;
}
