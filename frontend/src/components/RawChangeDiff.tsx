import { Empty, Space, Tag, Typography } from 'antd';
import { CopyValue } from './CopyValue';

export interface RawRecord { id: number; object_type: string; before: unknown; after: unknown }
interface Line { text: string; changed: boolean }
interface LinePair { before?: Line; after?: Line }

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? null, null, 2) ?? 'null';
}

function compareLines(before: unknown, after: unknown): LinePair[] {
  const left = formatJson(before).split('\n');
  const right = formatJson(after).split('\n');
  // Align unchanged lines using the longest common subsequence.
  const lengths = Array.from({ length: left.length + 1 }, () => new Uint32Array(right.length + 1));
  for (let i = left.length - 1; i >= 0; i--) {
    for (let j = right.length - 1; j >= 0; j--) {
      lengths[i][j] = left[i] === right[j] ? 1 + lengths[i + 1][j + 1] : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  const result: LinePair[] = [];
  let i = 0;
  let j = 0;
  while (i < left.length || j < right.length) {
    if (i < left.length && j < right.length && left[i] === right[j]) {
      result.push({ before: { text: left[i++], changed: false }, after: { text: right[j++], changed: false } });
      continue;
    }
    const removed: Line[] = [];
    const added: Line[] = [];
    while ((i < left.length || j < right.length) && (i === left.length || j === right.length || left[i] !== right[j])) {
      if (i < left.length && (j === right.length || lengths[i + 1][j] >= lengths[i][j + 1])) {
        removed.push({ text: left[i++], changed: true });
      } else {
        added.push({ text: right[j++], changed: true });
      }
    }
    for (let k = 0; k < Math.max(removed.length, added.length); k++) {
      result.push({ before: removed[k], after: added[k] });
    }
  }
  return result;
}

const types: Record<string, string> = { employee: '人员信息', department: '部门信息', membership: '部门归属' };

export function RawChangeDiff({ records }: { records: RawRecord[] }) {
  if (!records.length) return <Empty description="暂无原始记录" />;
  return <Space orientation="vertical" size={16} style={{ width: '100%' }}>
    {records.map(record => <section key={record.id}>
      <Space size={8}>
        <Typography.Text strong>{types[record.object_type] ?? record.object_type}</Typography.Text>
        {records.length > 1 && <Tag variant="filled">{record.id}</Tag>}
      </Space>
      <div className="raw-change-diff" role="table" aria-label="原始 JSON 对比">
        <div className="raw-change-diff-header" role="row">
          <span role="columnheader"><Space size={4}>变更前<CopyValue value={formatJson(record.before)} label="变更前 JSON" /></Space></span>
          <span role="columnheader"><Space size={4}>变更后<CopyValue value={formatJson(record.after)} label="变更后 JSON" /></Space></span>
        </div>
        {compareLines(record.before, record.after).map((pair, index) => <div className="raw-change-diff-row" role="row" key={index}>
          <code role="cell" className={pair.before?.changed ? 'raw-change-before' : undefined}>{pair.before?.text ?? ''}</code>
          <code role="cell" className={pair.after?.changed ? 'raw-change-after' : undefined}>{pair.after?.text ?? ''}</code>
        </div>)}
      </div>
    </section>)}
  </Space>;
}