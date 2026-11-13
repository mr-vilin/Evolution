import type { SortOrder } from 'antd/es/table/interface';

export const filterFields = [
  ['status', '状态'], ['category', '类型'], ['owner', '负责人'],
  ['source', '来源'], ['department', '部门'], ['priority', '优先级'],
] as const;
export type FilterField = typeof filterFields[number][0];
export type DemoRecord = {
  id: string; name: string; status: string; category: string; owner: string;
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
  category: ['成员', '部门', '门店'][i % 3], owner: ['林晓', '陈晨', '周宁'][i % 3],
  source: ['飞书', '手动录入'][i % 2], department: ['研发部', '运营部', '产品部'][Math.floor(i / 3) % 3],
  priority: ['普通', '高', '低'][Math.floor(i / 2) % 3],
  quantity: [2, 10, 100, 0, null][i % 5], progress: [0, 10, 100, null, 65][i % 5],
  createdAt: '2026-11-13 09:00:00', updatedAt: i % 5 === 4 ? null : '2026-11-13 10:30:00',
}));

export function displayValue(value: string | number | null | undefined): string | number {
  return value == null || (typeof value === 'string' && !value.trim()) ? '-' : value;
}

// Table 会在降序时反转比较值；空值及同值的基准顺序先补偿该反转。
export function compareNumbers(a: number | null, b: number | null, order: SortOrder = 'ascend'): number {
  if (a == null && b == null) return 0;
  if (a == null) return order === 'descend' ? -1 : 1;
  if (b == null) return order === 'descend' ? 1 : -1;
  return a - b;
}

export function tableCapacity(viewport: number, top: number, gapTop: number, gapBottom: number, initialY: number) {
  const full = Math.max(0, viewport - top - gapTop - gapBottom);
  const available = Math.max(0, viewport - gapBottom - initialY);
  const ratio = full ? available / full : 0;
  const exceptional = available + 0.01 < full * 0.6;
  return { full, available, ratio, exceptional, maxHeight: exceptional ? full : available };
}
