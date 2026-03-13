import { useState, useEffect, useCallback } from 'react'
import * as api from '../api/certification'
import type { CertificationProgress, ValidationResult, CompletionResult, CertExercise } from '../types/certification'

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

  const provision = async (moduleId: string) => {
    const result = await api.provisionModule(moduleId)
    await refresh()
    return result
  }

  const getExercise = useCallback(async (moduleId: string): Promise<CertExercise> => {
    return api.getExercise(moduleId)
  }, [])

  const submitAssessment = async (moduleId: string, answers: Record<string, string>) => {
    const result = await api.submitAssessment(moduleId, answers)
    await refresh()
    return result
  }

  return { progress, loading, refresh, validate, complete, provision, getExercise, submitAssessment }
}
