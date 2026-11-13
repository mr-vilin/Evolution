import { describe, expect, it } from 'vitest';
import { compareNumbers, displayValue, tableCapacity } from './tableStandardsModel';

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
});
