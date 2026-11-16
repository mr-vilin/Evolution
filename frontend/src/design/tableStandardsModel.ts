import type { SortOrder } from 'antd/es/table/interface';

export const filterFields = [
  ['status', '状态'], ['category', '类型'], ['owner', '负责人'],
  ['source', '来源'], ['department', '部门'], ['priority', '优先级'],
] as const;
export type FilterField = typeof filterFields[number][0];
export type DemoRecord = {
  id: string; name: string; status: string; category: string; owner: string;
  ownerAvatar?: string;
  source: string; department: string; priority: string;
  quantity: number | null; progress: number | null; createdAt: string | null; updatedAt: string | null;
};
export const statusColors = {
  已完成: 'success', 进行中: 'processing', 部分完成: 'warning', 失败: 'error',
  未开始: 'default', 无效: 'default', 未知: 'default',
} as const;
export const demoRecords: DemoRecord[] = Array.from({ length: 36 }, (_, i) => ({
  id: `demo-table-${String(i + 1).padStart(3, '0')}`,
  name: i === 1 ? '华东组织资料同步与成员信息补全任务（长名称示例）' : `组织资料任务 ${String(i + 1).padStart(2, '0')}`,
  status: Object.keys(statusColors)[i % 7],
  category: ['成员', '部门', '门店'][i % 3], owner: ['林晓', '陈晨', '周宁', 'Alexander Chen'][i % 4],
  source: ['飞书', '手动录入'][i % 2], department: ['研发部', '运营部', '产品部'][Math.floor(i / 3) % 3],
  priority: ['普通', '高', '低'][Math.floor(i / 2) % 3],
  quantity: [2, 10, 100, 0, null][i % 5], progress: [100, 10, 65, null, 0, null, null][i % 7],
  createdAt: `2026-11-${String(1 + Math.floor(i / 3)).padStart(2, '0')} ${String(9 + i % 3).padStart(2, '0')}:00:00`,
  updatedAt: i % 5 === 4 ? null : `2026-11-${String(1 + Math.floor(i / 3)).padStart(2, '0')} ${String(10 + i % 3).padStart(2, '0')}:30:00`,
}));

export function displayValue(value: string | number | null | undefined): string | number {
  return value == null || (typeof value === 'string' && !value.trim()) ? '-' : value;
}

export function personInitial(name: string): string {
  const firstWord = name.trim().split(/\s+/)[0] ?? '';
  if (!firstWord) return '?';
  return /^[A-Za-z]+$/.test(firstWord)
    ? firstWord.length > 5 ? firstWord.slice(0, 3) : firstWord
    : Array.from(firstWord)[0];
}

// Table 会在降序时反转比较值；空值及同值的基准顺序先补偿该反转。
export function compareNumbers(a: number | null, b: number | null, order: SortOrder = 'ascend'): number {
  if (a == null && b == null) return 0;
  if (a == null) return order === 'descend' ? -1 : 1;
  if (b == null) return order === 'descend' ? 1 : -1;
  return a - b;
}

export function compareTimes(a: string | null, b: string | null, order: SortOrder = 'ascend'): number {
  if (a == null && b == null) return 0;
  if (a == null) return order === 'descend' ? -1 : 1;
  if (b == null) return order === 'descend' ? 1 : -1;
  return a.localeCompare(b);
}

// 样本数量只限制原始示例，新增记录始终参与查询；按 ID 选样避免删除后补入隐藏样本。
export function selectDemoRecords(records: DemoRecord[], sampleSize?: number) {
  if (sampleSize == null) return records;
  const originalIds = new Set(demoRecords.map(row => row.id));
  const sampleIds = new Set(demoRecords.slice(0, sampleSize).map(row => row.id));
  return records.filter(row => !originalIds.has(row.id) || sampleIds.has(row.id));
}

export type TableMeasurements = { chromeHeight: number; rowHeight: number };

export function tableColumnLayout(width: number, narrow: boolean) {
  const nameWidth = narrow ? 96 : 208;
  const actionWidth = narrow ? 96 : 120;
  return { nameWidth, actionWidth, fixActions: width >= nameWidth + actionWidth + 96 };
}

export function tableCapacity(viewport: number, top: number, gapTop: number, gapBottom: number, initialY: number, measurements: TableMeasurements = { chromeHeight: 0, rowHeight: 0 }) {
  const full = Math.max(0, viewport - top - gapTop - gapBottom);
  const available = Math.max(0, viewport - gapBottom - initialY);
  const ratio = full ? available / full : 0;
  const minimum = Math.ceil(measurements.chromeHeight + measurements.rowHeight * 3);
  const reason = full < minimum ? 'viewport' : available + 0.01 < full * 0.6 ? 'ratio' : available < minimum ? 'body' : null;
  const mode = reason === 'viewport' ? 'natural' : reason ? 'sticky' : 'default';
  const exceptional = mode === 'sticky';
  return { full, available, ratio, minimum, reason, mode, exceptional, maxHeight: mode === 'natural' ? minimum : exceptional ? full : available };
}
