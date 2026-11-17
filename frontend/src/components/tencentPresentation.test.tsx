import { act, renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { decimalValue, formatTencentTime, useTencentSort } from './tencentPresentation';

it('非上海环境仍展示北京时间秒并拒绝无效日期', () => {
  vi.stubEnv('TZ','UTC');
  try {
    expect(formatTencentTime('2026-11-17T00:00:01Z')).toBe('2026-11-17 08:00:01');
    expect(formatTencentTime('2026-11-17T16:00:00Z')).toBe('2026-11-18 00:00:00');
    expect(formatTencentTime('invalid')).toBe('-');expect(formatTencentTime(null)).toBe('-');
  } finally {vi.unstubAllEnvs();}
});
it('小额负数保持八位精度，同值稳定、刷新新数据沿用排序且取消恢复源顺序', () => {
  const reset=vi.fn();const selectors={amount:(row:{id:string;amount:string|null})=>decimalValue(row.amount)};
  const {result}=renderHook(()=>useTencentSort(selectors,reset));
  const rows=[{id:'a',amount:'-0.00000001'},{id:'b',amount:null},{id:'c',amount:'-0.00000002'},{id:'d',amount:'-0.00000001'}];
  const change=(order:'ascend'|'descend'|null)=>act(()=>result.current.onChange({}, {}, {columnKey:'amount',order}, {action:'sort',currentDataSource:rows}));
  change('ascend');expect(result.current.rows(rows).map(row=>row.id)).toEqual(['c','a','d','b']);
  change('descend');expect(result.current.rows(rows).map(row=>row.id)).toEqual(['a','d','c','b']);
  expect(result.current.rows([...rows,{id:'e',amount:'0.00000000'}])[0].id).toBe('e');
  change(null);expect(result.current.rows(rows)).toEqual(rows);expect(reset).toHaveBeenCalledTimes(3);
});
