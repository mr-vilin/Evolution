import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Card, type CardProps } from 'antd';
import type { TableProps } from 'antd';
import { ResourceTable } from './ResourceTable';

/** 管理后台的整块表格：以实际顶栏、工具栏、分页和三行预算决定容纳与吸顶。 */
export function AdaptiveTableCard<T extends object>({title,headerExtra,tabList,tabBarExtraContent,activeTabKey,onTabChange,children,showTable=true,...table}: Omit<TableProps<T>,'title'> & {title?:string;headerExtra?:ReactNode;children?:ReactNode;showTable?:boolean} & Pick<CardProps,'tabList'|'tabBarExtraContent'|'activeTabKey'|'onTabChange'>) {
  const marker = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const [layout,setLayout] = useState({body:240,top:0,tail:0,sticky:false,width:1000});
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
      const row=panel.querySelector<HTMLElement>('.ant-table-tbody > tr:not(.ant-table-measure-row):not(.ant-table-placeholder)');
      const rowHeight=row?.getBoundingClientRect().height || 47;
      const chrome=Math.max(0,panel.getBoundingClientRect().height-(body?.getBoundingClientRect().height ?? 0));
      const minimum=chrome+rowHeight*3;
      const full=Math.max(0,document.documentElement.clientHeight-top-gapTop-gapBottom);
      // 初始文档位置不随窗口滚动变化，避免滚动本身切换模式。
      const initialY=origin.getBoundingClientRect().top+window.scrollY;
      const available=Math.max(0,document.documentElement.clientHeight-gapBottom-initialY);
      const sticky=full>=minimum && (available<full*0.6 || available<minimum);
      const maxHeight=full<minimum ? minimum : sticky ? full:available;
      const next={body:Math.max(rowHeight*3,Math.floor(maxHeight-chrome)),top:top+gapTop,tail:sticky ? Math.max(0, Math.ceil(initialY-top-gapTop)) : 0,sticky,width:body?.clientWidth ?? panel.clientWidth};
      setLayout(previous=>Object.keys(next).every(key=>next[key as keyof typeof next]===previous[key as keyof typeof next]) ? previous:next);
    };
    const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(measure);};
    const observer=new ResizeObserver(schedule);
    observer.observe(panel);observer.observe(document.body);
    const header=document.querySelector<HTMLElement>('.ant-pro-layout-header');if(header) observer.observe(header);
    window.addEventListener('resize',schedule);measure();
    return ()=>{observer.disconnect();cancelAnimationFrame(frame);window.removeEventListener('resize',schedule);};
  },[]);
  const columns=table.columns?.map(column=>{
    const narrow=layout.width<600;
    if(column.fixed==='left' || column.fixed===true)return {...column,width:narrow?96:column.width};
    if(column.fixed==='right') {
      const left=table.columns?.filter(item=>item.fixed==='left'||item.fixed===true).reduce((total,item)=>total+(narrow?96:Number(item.width)||160),0) ?? 0;
      const width=narrow?96:Number(column.width)||96;
      return {...column,width,fixed:layout.width<left+width+96?false:column.fixed};
    }
    return column;
  });
  // ProTable 在内部缓存初始 fixed；布局模式变化时重建列状态，排序和页码仍由外部保留。
  return <div ref={marker} style={{minWidth:0,paddingBottom:layout.tail}}><div ref={card} style={{position:layout.sticky ? 'sticky':'relative',top:layout.sticky ? layout.top:undefined,zIndex:layout.sticky ? 2:undefined}}>
    <Card title={title} extra={headerExtra} tabList={tabList} tabBarExtraContent={tabBarExtraContent} activeTabKey={activeTabKey} onTabChange={onTabChange}>{children}{showTable && <ResourceTable<T> key={columns?.map(column=>`${String(column.key)}:${String(column.fixed)}`).join('|')} {...table} columns={columns} scroll={{...table.scroll,y:layout.body}} />}</Card>
  </div></div>;
}
