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
