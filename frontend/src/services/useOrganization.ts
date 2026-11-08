import { useCallback, useEffect, useRef, useState } from 'react';
import type { Department, Employee } from '../domain';
import { ApiError, type Meta, query, request } from './http';

export function sameDataset(a: Meta, b: Meta) {
  return a.dataset_epoch === b.dataset_epoch && a.data_version === b.data_version;
}
export function datasetQuery(meta: Meta) {
  return { dataset_epoch: meta.dataset_epoch, data_version: meta.data_version };
}
const asError = (error: unknown) => error instanceof ApiError ? error : new ApiError(0, 'REQUEST_FAILED', '读取失败，请重试');
interface Branch { loaded?: boolean; loading?: boolean; cursor?: string | null; error?: ApiError | null }

export function useOrganizationTree(includeInactive: boolean) {
  const [nodes, setNodes] = useState<Department[]>([]);
  const [meta, setMeta] = useState<Meta>({});
  const [branches, setBranches] = useState<Record<string, Branch>>({});
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const current = useRef({ meta, branches, includeInactive });
  current.current = { meta, branches, includeInactive };
  const pending = useRef(new Set<string>());
  const reload = useCallback(() => setRevision(value => value + 1), []);
  const load = useCallback(async (parentId: string, append = false) => {
    const stamp = generation.current;
    const context = current.current;
    if (pending.current.has(parentId)) return;
    pending.current.add(parentId);
    setBranches(value => ({ ...value, [parentId]: { ...value[parentId], loading: true, error: null } }));
    try {
      const result = await request<Department[]>('/admin/api/organization/departments' + query({
        parent_id: parentId, include_inactive: context.includeInactive, limit: 100,
        ...datasetQuery(context.meta), cursor: append ? context.branches[parentId]?.cursor : undefined,
      }));
      if (stamp !== generation.current) return;
      if (context.meta.dataset_epoch && !sameDataset(context.meta, result.meta)) throw new ApiError(409, 'DATASET_CHANGED', '数据已变化，请重新读取');
      setMeta(result.meta);
      setNodes(value => {
        const incoming = new Set(result.data.map(item => item.id));
        return [...value.filter(item => !incoming.has(item.id) && (append || (item.parent_id ?? '0') !== parentId)), ...result.data];
      });
      setBranches(value => ({ ...value, [parentId]: { loaded: true, loading: false, cursor: result.meta.next_cursor, error: null } }));
    } catch (error) {
      if (stamp === generation.current) setBranches(value => ({ ...value, [parentId]: { ...value[parentId], loading: false, error: asError(error) } }));
    } finally {
      if (stamp === generation.current) pending.current.delete(parentId);
    }
  }, []);
  useEffect(() => {
    generation.current += 1;
    pending.current.clear();
    setNodes([]); setMeta({}); setBranches({});
    current.current = { meta: {}, branches: {}, includeInactive };
    void load('0');
    return () => { generation.current += 1; };
  }, [includeInactive, revision, load]);
  return { nodes, meta, branches, load, reload, ready: Boolean(meta.dataset_epoch && meta.data_version !== undefined) };
}

export function useOrganizationPeople(departmentId: string | undefined, descendants: boolean, keyword: string, accountStatus: string, meta: Meta) {
  const [data, setData] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const pending = useRef(false);
  const seenCursors = useRef(new Set<string>());
  const path = departmentId && meta.dataset_epoch && meta.data_version !== undefined
    ? '/admin/api/organization/employees' + query({ department_id: departmentId, include_descendants: descendants,
      keyword: keyword.trim(), account_status: accountStatus, limit: 20, ...datasetQuery(meta) }) : null;
  const context = useRef({ path, meta });
  context.current = { path, meta };
  const read = useCallback(async (next?: string | null) => {
    const stamp = generation.current;
    const active = context.current;
    if (!active.path || pending.current) return;
    pending.current = true;
    setLoading(true); setError(null);
    try {
      const result = await request<Employee[]>(active.path + (next ? `&cursor=${encodeURIComponent(next)}` : ''));
      if (stamp !== generation.current) return;
      if (!sameDataset(active.meta, result.meta)) throw new ApiError(409, 'DATASET_CHANGED', '数据版本已变化');
      if (result.meta.next_cursor && seenCursors.current.has(result.meta.next_cursor)) throw new ApiError(200, 'INVALID_CURSOR', '分页标记重复，请重新读取');
      if (result.meta.next_cursor) seenCursors.current.add(result.meta.next_cursor);
      setData(previous => next ? [...new Map([...previous, ...result.data].map(row => [row.id, row])).values()] : result.data);
      setTotal(Number(result.meta.total_count ?? 0));
      setCursor(result.meta.next_cursor ?? null);
    } catch (reason) {
      if (stamp === generation.current) setError(asError(reason));
    } finally {
      if (stamp === generation.current) { pending.current = false; setLoading(false); }
    }
  }, []);
  useEffect(() => {
    generation.current += 1; pending.current = false; seenCursors.current.clear();
    setData([]); setTotal(0); setCursor(null); setError(null); setLoading(false);
    void read();
    return () => { generation.current += 1; };
  }, [path, revision, read]);
  return { data, total, cursor, loading, error, path, more: () => read(cursor), reload: () => setRevision(value => value + 1) };
}
