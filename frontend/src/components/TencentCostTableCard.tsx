import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Card } from 'antd';
import type { TableProps } from 'antd';
import { ResourceTable } from './ResourceTable';

/** 费用看板的整块表格：以实际顶栏、工具栏、分页和三行预算决定容纳与吸顶。 */
export function TencentCostTableCard<T extends object>({title,children,...table}: Omit<TableProps<T>,'title'> & {title:string;children?:ReactNode}) {
  const marker = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const [layout,setLayout] = useState({body:240,top:0,tail:0,sticky:false});
  useEffect(()=>{
    const origin=marker.current, panel=card.current;
    if (!origin || !panel) return;
    let frame=0;
    const measure=()=>{
      const header=document.querySelector<HTMLElement>('.ant-pro-layout-header');
      const top=header?.getBoundingClientRect().height ?? 0;
      const content=origin.closest<HTMLElement>('.ant-pro-layout-content');
      const style=content ? getComputedStyle(content):null;
      const gapTop=parseFloat(style?.paddingTop ?? '') || 24;
      const gapBottom=parseFloat(style?.paddingBottom ?? '') || 24;
      const body=panel.querySelector<HTMLElement>('.ant-table-body');
      const row=panel.querySelector<HTMLElement>('.ant-table-tbody > tr:not(.ant-table-measure-row)');
      const rowHeight=row?.getBoundingClientRect().height || 47;
      const chrome=Math.max(0,panel.getBoundingClientRect().height-(body?.getBoundingClientRect().height ?? 0));
      const minimum=chrome+rowHeight*3;
      const full=Math.max(0,window.innerHeight-top-gapTop-gapBottom);
      // 初始文档位置不随窗口滚动变化，避免滚动本身切换模式。
      const initialY=origin.getBoundingClientRect().top+window.scrollY;
      const available=Math.max(0,window.innerHeight-gapBottom-initialY);
      const sticky=full>=minimum && (available<full*0.6 || available<minimum);
      const maxHeight=full<minimum ? minimum : sticky ? full:available;
      const next={body:Math.max(rowHeight*3,Math.floor(maxHeight-chrome)),top:top+gapTop,tail:sticky ? Math.ceil(full*0.6):0,sticky};
      setLayout(previous=>Object.keys(next).every(key=>next[key as keyof typeof next]===previous[key as keyof typeof next]) ? previous:next);
    };
    const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(measure);};
    const observer=new ResizeObserver(schedule);
    observer.observe(panel);observer.observe(document.body);
    const header=document.querySelector<HTMLElement>('.ant-pro-layout-header');if(header) observer.observe(header);
    window.addEventListener('resize',schedule);measure();
    return ()=>{observer.disconnect();cancelAnimationFrame(frame);window.removeEventListener('resize',schedule);};
  },[]);
  return <div ref={marker} style={{minWidth:0,paddingBottom:layout.tail}}><div ref={card} style={{position:layout.sticky ? 'sticky':'relative',top:layout.sticky ? layout.top:undefined,zIndex:layout.sticky ? 2:undefined}}>
    <Card title={title}>{children}<ResourceTable<T> {...table} scroll={{...table.scroll,y:layout.body}} /></Card>
  </div></div>;
}
