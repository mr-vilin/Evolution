import { useEffect, useRef, useState } from 'react';
import type { Department } from '../domain';
import { ApiError, type Meta, request } from './http';
import { datasetQuery, sameDataset } from './useOrganization';

export interface RangeState { self_selected: boolean; descendants: 'none' | 'partial' | 'all' }
interface Selection { selected_ids: string[]; count: number; states: Record<string, RangeState>; departments: Department[] }
export function rangeLabel(state?: RangeState) {
  if (!state || (!state.self_selected && state.descendants === 'none')) return '未选';
  if (state.descendants === 'none') return '仅本部门';
  return `${state.self_selected ? '本部门及下级' : '仅下级'} · ${state.descendants === 'all' ? '全部下级' : '部分下级'}`;
}
export function useOrganizationSelection(meta: Meta, onConflict: () => void) {
  const [selection, setSelection] = useState<Selection>({ selected_ids: [], count: 0, states: {}, departments: [] });
  const [bound, setBound] = useState<Meta>({});
  const [calculating, setCalculating] = useState(true);
  const [error, setError] = useState('');
  const context = useRef({ meta, selection });
  context.current = { meta, selection };
  const generation = useRef(0);
  const pending = useRef(false);
  const available = Boolean(meta.dataset_epoch && meta.data_version !== undefined);
  const ready = available && sameDataset(meta, bound) && !calculating && !error;
  async function resolve(ids: string[], toggleId?: string, details = false) {
    const version = context.current.meta;
    const result = await request<Selection>('/admin/api/organization/selection', {
      method: 'POST', body: { ...datasetQuery(version), selected_ids: ids, toggle_id: toggleId, include_details: details },
    });
    if (!sameDataset(version, result.meta) || !sameDataset(context.current.meta, result.meta)) throw new ApiError(409, 'DATASET_CHANGED', '范围版本已变化，请重新核对');
    return result;
  }
  useEffect(() => {
    const stamp = ++generation.current;
    pending.current = false;
    setCalculating(true); setError('');
    if (available) void resolve(context.current.selection.selected_ids).then(result => {
      if (stamp === generation.current) { setSelection(result.data); setBound(result.meta); }
    }).catch(reason => {
      if (stamp === generation.current) setError(reason instanceof Error ? reason.message : '范围解析失败');
    }).finally(() => { if (stamp === generation.current) setCalculating(false); });
    return () => { generation.current += 1; };
  }, [meta.dataset_epoch, meta.data_version, available]);
  async function toggle(id: string) {
    if (!ready || pending.current) return;
    const stamp = generation.current;
    pending.current = true; setCalculating(true); setError('');
    try {
      const result = await resolve(context.current.selection.selected_ids, id);
      if (stamp === generation.current) { setSelection(result.data); setBound(result.meta); }
    } catch (reason) {
      if (stamp === generation.current) {
        setError(reason instanceof Error ? reason.message : '范围解析失败');
        if (reason instanceof ApiError && reason.status === 409) onConflict();
      }
    } finally { if (stamp === generation.current) { pending.current = false; setCalculating(false); } }
  }
  async function details(ids = context.current.selection.selected_ids) {
    const result = await resolve(ids, undefined, true);
    return { departments: result.data.departments, meta: result.meta };
  }
  return { ...selection, calculating, ready, error, toggle, details };
}
