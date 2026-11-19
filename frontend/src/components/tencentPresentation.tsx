import { useState } from 'react';
import type { TableProps } from 'antd';

export const tencentTimeStyle = {fontSize:12,lineHeight:'20px',fontWeight:400,color:'var(--app-muted)'} as const;
export function formatTencentTime(value?: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return '-';
  return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(value));
}
export function TencentTime({value}:{value?:string|null}) {return <span style={tencentTimeStyle}>{formatTencentTime(value)}</span>;}
export const timeValue = (value?:string|null) => value && !Number.isNaN(Date.parse(value)) ? Date.parse(value) : null;
/** 所有财务字段最多八位，转换固定单位时不经过二进制金额。 */
export function decimalValue(value?:string|null) {
  if (value===null || value===undefined || !/^-?\d+(?:\.\d{1,8})?$/.test(value))return null;
  const [whole,fraction='']=value.split('.');return BigInt(whole+fraction.padEnd(8,'0'));
}
type SortValue=number|bigint|null|undefined;
export function useTencentSort<T extends object>(selectors:Record<string,(row:T)=>SortValue>,resetPage?:()=>void) {
  const [sort,setSort]=useState<{key:string|null;order:'ascend'|'descend'|null}>({key:null,order:null});
  const onChange:NonNullable<TableProps<T>['onChange']>=(_,__,sorter,extra)=>{
    if(extra.action!=='sort')return;
    const value=Array.isArray(sorter)?sorter[0]:sorter;
    setSort({key:value?.order?String(value.columnKey):null,order:value?.order ?? null});resetPage?.();
  };
  function rows(values:T[]) {
    const select=sort.key ? selectors[sort.key]:null;
    if(!select || !sort.order)return values;
    return values.map((row,index)=>({row,index})).sort((a,b)=>{
      const x=select(a.row),y=select(b.row);
      if(x===null || x===undefined)return y===null || y===undefined?a.index-b.index:1;
      if(y===null || y===undefined)return -1;
      const order=x<y?-1:x>y?1:0;return order?(sort.order==='ascend'?order:-order):a.index-b.index;
    }).map(item=>item.row);
  }
  return {rows,onChange,column:(key:string)=>({sorter:true,sortOrder:sort.key===key?sort.order:null})};
}
