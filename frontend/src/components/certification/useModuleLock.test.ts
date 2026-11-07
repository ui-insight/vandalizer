import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CertificationProgress } from '../../types/certification'
import { MODULES } from './modules'
import { useModuleLock } from './useModuleLock'

const legacy: CertificationProgress = {
  id: 'legacy', user_id: 'learner', modules: {}, total_xp: 0, level: 'novice',
  certified: false, certified_at: null, last_activity_date: null, unlocked: false,
}
const completed = { completed: true, stars: 1, completed_at: '2026-10-08', attempts: 1, xp_earned: 100 }

describe('course access follows assessed prerequisites, not display order', () => {
  it.each([false, true])('preserves legacy any-order access with historical unlocked=%s', unlocked => {
    const { result } = renderHook(() => useModuleLock({ ...legacy, unlocked }))
    for (const module of MODULES) expect(result.current(module.id)).toBe(false)
    expect(result.current('not-in-this-course')).toBe(true)
  })

  it('waits for a pinned definition instead of falling back to legacy rules', () => {
    const { result } = renderHook(() => useModuleLock({ ...legacy, enrollment_id: 'enrollment', unlocked: true }))
    for (const module of MODULES) expect(result.current(module.id)).toBe(true)
  })

  it('uses the pinned prerequisite even when it differs from the preceding module', () => {
    const requirements = { ai_literacy: [], foundations: [], process_mapping: ['ai_literacy'] }
    const { result, rerender } = renderHook(({ progress }) => useModuleLock(progress, MODULES, requirements), {
      initialProps: { progress: { ...legacy, unlocked: true, modules: { foundations: completed } } as CertificationProgress },
    })
    expect(result.current('process_mapping')).toBe(true)
    rerender({ progress: { ...legacy, modules: { ai_literacy: completed } } })
    expect(result.current('process_mapping')).toBe(false)
    expect(result.current('governance')).toBe(true)
  })
})
