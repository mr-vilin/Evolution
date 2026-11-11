import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useResource } from './useResource';

afterEach(() => vi.unstubAllGlobals());

it('快速切换部门时，较慢的旧响应不能覆盖新部门数据', async () => {
  let resolveOld!: (value: Response) => void;
  vi.stubGlobal('fetch', (path: string) => path === '/old'
    ? new Promise<Response>(resolve => { resolveOld = resolve; })
    : Promise.resolve(new Response(JSON.stringify({ data: ['new'], meta: {} }))));
  const { result, rerender } = renderHook(({ path }) => useResource<string[]>(path), { initialProps: { path: '/old' } });
  rerender({ path: '/new' });
  await waitFor(() => expect(result.current.data).toEqual(['new']));
  await act(async () => { resolveOld(new Response(JSON.stringify({ data: ['old'], meta: {} }))); });
  expect(result.current.data).toEqual(['new']);
});

it('错误后重试成功会清除旧错误', async () => {
  let fail = true;
  vi.stubGlobal('fetch', async () => fail
    ? new Response(JSON.stringify({ error: { code: 'UNAVAILABLE', message: '暂不可用' } }), { status: 503 })
    : new Response(JSON.stringify({ data: [1], meta: {} })));
  const { result } = renderHook(() => useResource<number[]>('/items'));
  await waitFor(() => expect(result.current.error?.status).toBe(503));
  fail = false;
  act(() => result.current.reload());
  await waitFor(() => expect(result.current.data).toEqual([1]));
  expect(result.current.error).toBeNull();
});

it('轮询保留上次结果，但切换资源立即清除旧数据', async () => {
  let resolveReload!: (value: Response) => void;
  let reads = 0;
  vi.stubGlobal('fetch', async (path: string) => {
    reads += 1;
    if (reads > 1) return new Promise<Response>(resolve => { resolveReload = resolve; });
    return Response.json({ data: path, meta: {} });
  });
  const { result, rerender } = renderHook(({ path }) => useResource<string>(path, true), { initialProps: { path: '/first' } });
  await waitFor(() => expect(result.current.data).toBe('/first'));
  act(() => result.current.reload());
  expect(result.current.data).toBe('/first');
  rerender({ path: '/second' });
  expect(result.current.data).toBeNull();
  await act(async () => resolveReload(Response.json({ data: '/second', meta: {} })));
  expect(result.current.data).toBe('/second');
});
