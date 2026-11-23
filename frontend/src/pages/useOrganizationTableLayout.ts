import { useLayoutEffect, useRef, useState } from 'react';
import { tableCapacity, tableColumnLayout } from '../components/tableLayout';

const gap = 16;
const initialBodyHeight = 240;
const normalRowHeight = 56;
const narrowTableWidth = 424;

export function useOrganizationTableLayout(recordCount: number, feedbackVisible: boolean) {
  const position = useRef<HTMLDivElement>(null);
  const table = useRef<HTMLDivElement>(null);
  const [layout, setLayout] = useState({ width: narrowTableWidth, bodyHeight: initialBodyHeight, mode: 'default', stickyTop: 72 });

  useLayoutEffect(() => {
    const anchor = position.current;
    const tableRegion = table.current;
    const card = anchor?.nextElementSibling;
    if (!anchor || !tableRegion || !card) return;
    const workspace = anchor.closest('.ant-pro-layout');
    const topBar = [...(workspace?.querySelectorAll('header.ant-layout-header') ?? [])]
      .find(element => getComputedStyle(element).position === 'fixed');
    const summary = anchor.previousElementSibling;
    const cardHeader = card.querySelector('.ant-card-head');
    const feedback = card.querySelector('.org-people-feedback');
    const header = tableRegion.querySelector('.ant-table-header');
    const body = tableRegion.querySelector<HTMLElement>('.ant-table-body');
    if (!body || !header) return;
    const rows = Array.from(body.querySelectorAll('tr[data-row-key]')).slice(0, 3);

    function measure() {
      if (!anchor || !tableRegion || !card || !body || !header) return;
      const top = topBar?.getBoundingClientRect().height ?? 0;
      const initialY = anchor.getBoundingClientRect().top + window.scrollY;
      const rowHeight = Math.max(normalRowHeight, ...rows.map(row => row.getBoundingClientRect().height));
      const scrollbar = body.offsetHeight - body.clientHeight;
      const chrome = Math.ceil(card.getBoundingClientRect().height - body.getBoundingClientRect().height);
      const capacity = tableCapacity(document.documentElement.clientHeight, top, gap, gap, initialY, {
        chromeHeight: chrome + scrollbar, rowHeight,
      });
      const next = {
        width: tableRegion.clientWidth || narrowTableWidth,
        bodyHeight: Math.max(rowHeight * 3 + scrollbar, Math.floor(capacity.maxHeight - chrome)),
        mode: capacity.mode,
        stickyTop: top + gap,
      };
      setLayout(previous => previous.width === next.width && previous.bodyHeight === next.bodyHeight &&
        previous.mode === next.mode && previous.stickyTop === next.stickyTop ? previous : next);
    }

    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    const observer = new ResizeObserver(schedule);
    for (const element of [workspace, topBar, summary, card, cardHeader, feedback, tableRegion, header, body, ...rows]) {
      if (element) observer.observe(element);
    }
    window.addEventListener('resize', schedule);
    measure();
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', schedule);
    };
  }, [recordCount, feedbackVisible]);

  return { position, table, ...layout, ...tableColumnLayout(layout.width, layout.width < narrowTableWidth) };
}
