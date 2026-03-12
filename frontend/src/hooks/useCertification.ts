import { useState, useEffect, useCallback } from 'react'
import * as api from '../api/certification'
import type { CertificationProgress, ValidationResult, CompletionResult } from '../types/certification'

export function useCertification() {
  const [progress, setProgress] = useState<CertificationProgress | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getProgress()
      setProgress(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const validate = async (moduleId: string): Promise<ValidationResult> => {
    return api.validateModule(moduleId)
  }

  const complete = async (moduleId: string): Promise<CompletionResult> => {
    const result = await api.completeModule(moduleId)
    await refresh()
    return result
  }

  return { progress, loading, refresh, validate, complete }
}
