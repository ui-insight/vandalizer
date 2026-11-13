import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, it } from 'vitest'
import { PREFERENCE_KEY, hasFoldersKey, useLibrarySidebar } from './useLibrarySidebar'

type Props = Parameters<typeof useLibrarySidebar>[0]
const settled: Props = { scope: 'personal', folderCount: 0, loading: false, error: false }

beforeEach(() => localStorage.clear())

it('follows the folders until the person chooses', () => {
  const { result, rerender } = renderHook((props: Props) => useLibrarySidebar(props), { initialProps: settled })
  expect(result.current.collapsed).toBe(true)
  // A first folder expands it.
  rerender({ ...settled, folderCount: 1 })
  expect(result.current.collapsed).toBe(false)
  expect(result.current.remembered).toBe(false)
})

it('keeps the person\'s choice over the folder count, across mounts', () => {
  const { result, rerender } = renderHook((props: Props) => useLibrarySidebar(props), { initialProps: { ...settled, folderCount: 3 } })
  act(() => result.current.setCollapsed(true))
  expect(result.current.collapsed).toBe(true)
  expect(localStorage.getItem(PREFERENCE_KEY)).toBe('collapsed')
  rerender({ ...settled, folderCount: 4 })
  expect(result.current.collapsed).toBe(true)
  const next = renderHook(() => useLibrarySidebar(settled))
  act(() => next.result.current.setCollapsed(false))
  expect(renderHook(() => useLibrarySidebar(settled)).result.current.collapsed).toBe(false)
})

it('stays open when folders fail to load, so Retry is visible', () => {
  expect(renderHook(() => useLibrarySidebar({ ...settled, error: true })).result.current.collapsed).toBe(false)
})

it('uses each scope and team\'s last known folders while loading', () => {
  renderHook(() => useLibrarySidebar({ ...settled, scope: 'team', teamId: 't1', folderCount: 2 }))
  expect(localStorage.getItem(hasFoldersKey('team', 't1'))).toBe('1')
  const loading = { ...settled, loading: true }
  expect(renderHook(() => useLibrarySidebar({ ...loading, scope: 'team', teamId: 't1' })).result.current.collapsed).toBe(false)
  expect(renderHook(() => useLibrarySidebar({ ...loading, scope: 'team', teamId: 't2' })).result.current.collapsed).toBe(true)
  expect(renderHook(() => useLibrarySidebar({ ...loading, scope: 'personal', teamId: 't1' })).result.current.collapsed).toBe(true)
})

it('works when storage is unavailable', () => {
  const original = Storage.prototype.getItem
  const originalSet = Storage.prototype.setItem
  Storage.prototype.getItem = () => { throw new Error('blocked') }
  Storage.prototype.setItem = () => { throw new Error('blocked') }
  try {
    const { result } = renderHook(() => useLibrarySidebar(settled))
    expect(result.current.collapsed).toBe(true)
    act(() => result.current.setCollapsed(false))
    expect(result.current.collapsed).toBe(false)
  } finally {
    Storage.prototype.getItem = original
    Storage.prototype.setItem = originalSet
  }
})
