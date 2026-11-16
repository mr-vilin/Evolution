import { describe, expect, it } from 'vitest';
import { compareNumbers, compareTimes, demoRecords, displayValue, personInitial, selectDemoRecords, tableCapacity, tableColumnLayout } from './tableStandardsModel';

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
  it('60% 还需满足三行预算；一屏也不足时采用自然滚动', () => {
    const measurements = { chromeHeight: 289, rowHeight: 41 };
    expect(tableCapacity(576, 48, 16, 16, 262.4, measurements)).toMatchObject({ reason: 'body', mode: 'sticky', minimum: 412, maxHeight: 496 });
    expect(tableCapacity(576, 48, 16, 16, 148, measurements)).toMatchObject({ reason: null, mode: 'default', maxHeight: 412 });
    expect(tableCapacity(490, 48, 16, 16, 100, measurements)).toMatchObject({ reason: 'viewport', mode: 'natural', exceptional: false, maxHeight: 412 });
  });
  it('极窄容器为业务字段留出至少 96px，足够宽时恢复固定操作', () => {
    expect(tableColumnLayout(194, true)).toEqual({ nameWidth: 96, actionWidth: 96, fixActions: false });
    expect(tableColumnLayout(287, true).fixActions).toBe(false);
    expect(tableColumnLayout(288, true).fixActions).toBe(true);
    expect(tableColumnLayout(800, false)).toEqual({ nameWidth: 208, actionWidth: 120, fixActions: true });
  });
  it('基础样本为零仍保留新增，切换数量保留编辑与删除且不补入隐藏样本', () => {
    const added = { ...demoRecords[0], id: 'local-test', name: '新增记录' };
    const edited = { ...demoRecords[0], name: '编辑后的名称' };
    const records = [added, edited, ...demoRecords.slice(2)];
    expect(selectDemoRecords(records, 0)).toEqual([added]);
    expect(selectDemoRecords(records, 2)).toEqual([added, edited]);
    expect(selectDemoRecords(records, 36)).toEqual(records);
    expect(selectDemoRecords(records)).toEqual(records);
  });
  it('任务状态和演示进度一致，并保留数值、零值与空值样本', () => {
    for (const row of demoRecords) {
      if (row.status === '已完成') expect(row.progress).toBe(100);
      else if (row.status === '未开始') expect(row.progress).toBe(0);
      else if (row.status === '进行中' || row.status === '部分完成') {
        expect(row.progress).toBeGreaterThan(0);
        expect(row.progress).toBeLessThan(100);
      } else expect(row.progress).toBeNull();
    }
    expect(new Set(demoRecords.map(row => row.quantity))).toEqual(new Set([0, 2, 10, 100, null]));
  });
  it('无头像时按人员名称生成圆形头像文字', () => {
    expect(['林晓', 'Amy Chen', 'Alexander Chen', ''].map(personInitial)).toEqual(['林', 'Amy', 'Ale', '?']);
  });
});
