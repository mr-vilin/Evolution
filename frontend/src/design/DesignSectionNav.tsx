import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Button, theme } from 'antd';
import { ArrowUpOutlined } from '@ant-design/icons';

type NavigationPosition = { floating: boolean; top: number; left: number; width: number; height: number };

export default function DesignSectionNav({ sections }: { sections: string[][] }) {
  const slotRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const { token } = theme.useToken();
  const [position, setPosition] = useState<NavigationPosition>({ floating: false, top: 0, left: 0, width: 0, height: 0 });

  useEffect(() => {
    const slot = slotRef.current!;
    const nav = navRef.current!;
    const page = slot.closest<HTMLElement>('.design-standards')!;
    const content = slot.closest<HTMLElement>('.ant-pro-layout-content');
    let frame = 0;
    const measure = () => {
      const bounds = slot.getBoundingClientRect();
      // 左侧内容留白与顶栏下的留白使用同一数值；不把侧栏宽度计入留白。
      const inset = content ? parseFloat(getComputedStyle(content).paddingInlineStart) || 0 : 24;
      const header = document.querySelector<HTMLElement>('.ant-pro-layout-header');
      const headerBounds = header?.getBoundingClientRect();
      const headerBottom = headerBounds && headerBounds.top <= 0 ? Math.max(0, headerBounds.bottom) : 0;
      const top = headerBottom + inset;
      const floating = bounds.top < top;
      setPosition(previous => {
        const next = { floating, top, left: bounds.left, width: bounds.width, height: floating ? previous.height || nav.offsetHeight : nav.offsetHeight };
        return Object.keys(next).every(key => next[key as keyof NavigationPosition] === previous[key as keyof NavigationPosition]) ? previous : next;
      });
      page.style.setProperty('--design-anchor-offset', `${top + nav.offsetHeight + 16}px`);
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(slot);
    observer.observe(nav);
    if (content) observer.observe(content);
    const header = document.querySelector('.ant-pro-layout-header');
    if (header) observer.observe(header);
    window.addEventListener('scroll', schedule, { passive: true, capture: true });
    window.addEventListener('resize', schedule);
    measure();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener('scroll', schedule, true);
      window.removeEventListener('resize', schedule);
      page.style.removeProperty('--design-anchor-offset');
    };
  }, []);

  function returnToTop() {
    const page = slotRef.current?.closest<HTMLElement>('.design-standards');
    if (!page) return;
    const behavior = token.motion && !window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'instant';
    // 回到滚动容器起点，保留工作台顶栏下原有的页首留白。
    for (let parent = page.parentElement; parent; parent = parent.parentElement) {
      if (/(auto|scroll)/.test(getComputedStyle(parent).overflowY)) parent.scrollTo({ top: 0, behavior });
    }
    window.scrollTo({ top: 0, behavior });
  }

  const style = {
    '--design-nav-shadow': token.boxShadowSecondary,
    '--design-nav-surface': token.colorBgElevated,
    '--design-nav-duration': token.motion ? token.motionDurationMid : '0s',
    '--design-nav-ease': token.motionEaseInOut,
    ...(position.floating ? { top: position.top, left: position.left, width: position.width } : {}),
  } as CSSProperties;
  return <div ref={slotRef} className="design-jumps-slot" style={{ minHeight: position.height || undefined }}>
    <nav ref={navRef} className={`design-jumps${position.floating ? ' is-floating' : ''}`} aria-label="设计标准章节" style={style}>
      <div className="design-jump-links">{sections.map(([id, title]) => <a key={id} href={`#${id}`}>{title}</a>)}</div>
      {position.floating && <Button className="design-back-top" aria-label="返回顶部" icon={<ArrowUpOutlined aria-hidden />} onClick={returnToTop}>返回顶部</Button>}
    </nav>
  </div>;
}
