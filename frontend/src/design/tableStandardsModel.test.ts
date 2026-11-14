import { describe, expect, it } from 'vitest';
import { compareNumbers, compareTimes, displayValue, personInitial, tableCapacity } from './tableStandardsModel';

describe('表格规范的数值与高度边界', () => {
  it('按数值排序，升降序均保留有效零值并将空值置底', () => {
    const values = [2, 10, 100, 0, null];
    expect([...values].sort((a, b) => compareNumbers(a, b, 'ascend'))).toEqual([0, 2, 10, 100, null]);
    expect([...values].sort((a, b) => -compareNumbers(a, b, 'descend'))).toEqual([100, 10, 2, 0, null]);
    expect([null, undefined, '', '   ', 0, '0%'].map(displayValue)).toEqual(['-', '-', '-', '-', 0, '0%']);
  });
  it('恰好 60% 首屏容纳，低于 60% 才按一屏容量布局', () => {
    expect(tableCapacity(600, 48, 16, 16, 272)).toMatchObject({ full: 520, available: 312, exceptional: false, maxHeight: 312 });
    expect(tableCapacity(600, 48, 16, 16, 273)).toMatchObject({ full: 520, available: 311, exceptional: true, maxHeight: 520 });
  });
  it('时间升降序都将缺失值置底', () => {
    const values = ['2026-11-12 10:00:00', null, '2026-11-13 09:00:00'];
    expect([...values].sort((a, b) => compareTimes(a, b, 'ascend'))).toEqual(['2026-11-12 10:00:00', '2026-11-13 09:00:00', null]);
    expect([...values].sort((a, b) => -compareTimes(a, b, 'descend'))).toEqual(['2026-11-13 09:00:00', '2026-11-12 10:00:00', null]);
  });
  it('无头像时按人员名称生成圆形头像文字', () => {
    expect(['林晓', 'Amy Chen', 'Alexander Chen', ''].map(personInitial)).toEqual(['林', 'Amy', 'Ale', '?']);
  });
});
