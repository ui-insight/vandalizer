import { useCallback } from 'react'
import { MODULES } from '../../pages/Certification'
import type { CertificationProgress } from '../../types/certification'

export function useModuleLock(progress: CertificationProgress | null) {
  return useCallback((moduleId: string): boolean => {
    const module = MODULES.find(m => m.id === moduleId)
    if (!module) return true
    if (module.number === 0) return false
    if (progress?.unlocked) return false
    const prevModule = MODULES.find(m => m.number === module.number - 1)
    if (!prevModule) return false
    return !progress?.modules[prevModule.id]?.completed
  }, [progress])
}
