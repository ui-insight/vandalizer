import { useCallback } from 'react'
import { MODULES } from './modules'
import type { CertificationProgress, ModuleDefinition } from '../../types/certification'

export function useModuleLock(progress: CertificationProgress | null, modules: ModuleDefinition[] = MODULES, prerequisites?: Record<string, string[]>) {
  return useCallback((moduleId: string): boolean => {
    const module = modules.find(m => m.id === moduleId)
    if (!module) return true
    if (prerequisites) return !prerequisites[moduleId] || prerequisites[moduleId].some(id => !progress?.modules[id]?.completed)
    // A pinned enrollment needs its actual definition. The preserved legacy
    // rubric has no prerequisites; display order must not invent new ones.
    return !progress || Boolean(progress.enrollment_id)
  }, [progress, modules, prerequisites])
}
