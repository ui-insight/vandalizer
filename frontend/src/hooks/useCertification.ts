import { useState, useEffect, useCallback, useRef } from 'react'
import * as api from '../api/certification'
import { ApiError } from '../api/client'
import { observeCertificationJourney } from '../api/certificationJourney'
import type { CertificationProgress, ValidationResult, CompletionResult, CertExercise, CourseDefinition, PendingCompletion, OutcomeCompletionSelection } from '../types/certification'
function sessionRequest(key: string) {
  try { return sessionStorage.getItem(key) } catch { return null }
}


export function useCertification() {
  const [progress, setProgress] = useState<CertificationProgress | null>(null)
  const [loading, setLoading] = useState(true)
  const [course, setCourse] = useState<CourseDefinition | null>(null)
  const cachedCourse = useRef<CourseDefinition | null>(null)
  const hasLoadedProgress = useRef(false)

  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [savedWritePendingRefresh, setSavedWritePendingRefresh] = useState(false)
  const requestVersion = useRef(0)
  const positionWritePending = useRef(false)
  const completionRequests = useRef(new Map<string, string>())
  const completionPreconditions = useRef(new Map<string, { requestId: string; attempts: number }>())
  const selectedRequests = useRef(new Map<string, { requestId: string; selection: OutcomeCompletionSelection }>())
  const completingRequests = useRef(new Set<string>())
  const pendingActions = useRef(new Map<string, { body: string; promise: Promise<unknown> }>())
  const [, setCompletionRevision] = useState(0)

  const refresh = useCallback(async () => {
    const version = ++requestVersion.current
    setLoading(true)
    let observationIdentity: Pick<CertificationProgress, 'enrollment_id' | 'manifest_sha256'> | null = cachedCourse.current
    try {
      const data = await api.getProgress()
      if (version !== requestVersion.current) return
      observationIdentity = data
      let definition: CourseDefinition | null = null
      if (data.enrollment_id) {
        const cached = cachedCourse.current
        definition = cached?.enrollment_id === data.enrollment_id && cached.manifest_sha256 === data.manifest_sha256
          ? cached : await api.getCourse(data.enrollment_id)
        if (!definition.versioned || definition.enrollment_id !== data.enrollment_id || definition.course_version !== data.course_version || definition.manifest_sha256 !== data.manifest_sha256) {
          throw new Error('The course definition does not match saved progress')
        }
      } else if (cachedCourse.current) {
        throw new Error('The saved course is temporarily unavailable')
      }
      if (version !== requestVersion.current) return
      cachedCourse.current = definition
      setCourse(definition)
      setProgress(data)
      hasLoadedProgress.current = true
      setRefreshError(null)
      setSavedWritePendingRefresh(false)
    } catch {
      if (version !== requestVersion.current) return
      observeCertificationJourney(hasLoadedProgress.current ? 'progress_refresh_failed' : 'initial_progress_load_failed', observationIdentity)
      setRefreshError('Certification progress could not be refreshed.')
    } finally {
      if (version === requestVersion.current) setLoading(false)
    }
  }, [])

  const refreshAfterWrite = useCallback(async () => {
    setSavedWritePendingRefresh(true)
    await refresh()
  }, [refresh])

  useEffect(() => { refresh() }, [refresh])

  function sharePendingAction<T>(kind: string, moduleId: string, body: string, action: () => Promise<T>): Promise<T> {
    if (!progress?.id || !progress.user_id) return Promise.reject(new Error('Load course progress before continuing'))
    const key = JSON.stringify([progress.user_id, progress.id, progress.enrollment_id, progress.manifest_sha256, kind, moduleId])
    const pending = pendingActions.current.get(key)
    if (pending) {
      if (pending.body !== body) return Promise.reject(new Error('Wait for the pending save before changing these answers'))
      return pending.promise as Promise<T>
    }
    // Register synchronously, before the API dispatch or a React state update.
    // Retain the promise through the post-write read so a repeated click cannot
    // submit again merely because the original response has arrived.
    const promise = Promise.resolve().then(action).finally(() => { pendingActions.current.delete(key) })
    pendingActions.current.set(key, { body, promise })
    return promise
  }

  const validate = async (moduleId: string): Promise<ValidationResult> => {
    return sharePendingAction('validate', moduleId, '', () => api.validateModule(moduleId, progress?.enrollment_id))
  }

  const complete = async (moduleId: string, resumeRequestId?: string, selection?: OutcomeCompletionSelection): Promise<CompletionResult> => {
    if (!progress?.id || !progress.user_id) throw new Error('Load course progress before submitting work')
    const enrollmentId = progress?.enrollment_id
    const key = enrollmentId ? `certification-completion:${enrollmentId}:${moduleId}`
      : progress?.id && progress.user_id ? `certification-completion:legacy:${progress.user_id}:${progress.id}:${moduleId}` : null
    let requestId: string | undefined
    let originalSelection: OutcomeCompletionSelection | undefined
    let originalExpectedAttempts: number | undefined
    if (selection && savedWritePendingRefresh) throw new Error('Refresh course progress before starting another completion')
    if (selection && (!course?.selected_outcome_completion || !enrollmentId
      || course.enrollment_id !== enrollmentId || course.manifest_sha256 !== progress?.manifest_sha256
      || !course.modules.some(module => module.id === moduleId))) throw new Error('Selected evidence completion is unavailable for this course')
    const validSelection = (value: OutcomeCompletionSelection) => value && Object.keys(value).length > 0
      && Object.entries(value).every(([name, id]) => ['review_attempt_id', 'scenario_attempt_id'].includes(name) && typeof id === 'string' && /^[a-f0-9]{32}$/.test(id))
    if (selection && !validSelection(selection)) throw new Error('Choose complete saved assessment references')
    if (key && completingRequests.current.has(key)) throw new Error('This completion is already being checked')
    if (resumeRequestId && (!key || !/^[a-f0-9]{32}$/.test(resumeRequestId))) throw new Error('Load this assessment’s course before retrying')
    if (key) {
      let retained = selectedRequests.current.get(key)
      if (!retained) {
        let raw: string | null = null
        try { raw = sessionStorage.getItem(`${key}:evidence`) } catch { /* Memory retains the current request. */ }
        if (raw) {
          try { retained = JSON.parse(raw) } catch { throw new Error('The saved completion needs recovery before another submission') }
          if (!retained || !/^[a-f0-9]{32}$/.test(retained.requestId) || !validSelection(retained.selection)) throw new Error('The saved completion needs recovery before another submission')
        }
      }
      if (retained && resumeRequestId && retained.requestId !== resumeRequestId) throw new Error('Retry the pending completion before selecting another submission')
      requestId = resumeRequestId ?? retained?.requestId ?? completionRequests.current.get(key)
      if (!requestId) {
        let saved: string | null = null
        try { saved = sessionStorage.getItem(key) } catch { /* Retain in memory if browser storage is unavailable. */ }
        requestId = saved && /^[a-f0-9]{32}$/.test(saved) ? saved
          : progress?.pending_completions?.find(item => item.module_id === moduleId)?.attempt_id ?? crypto.randomUUID().replaceAll('-', '')
      }
      const existing = retained || completionRequests.current.has(key) || sessionRequest(key)
        || progress?.pending_completions?.some(item => item.module_id === moduleId)
      if (selection && existing && (!retained || ['review_attempt_id', 'scenario_attempt_id'].some(name =>
        retained.selection[name as keyof OutcomeCompletionSelection] !== selection[name as keyof OutcomeCompletionSelection]))) {
        throw new Error('Retry the pending completion with its original evidence before changing selections')
      }
      originalSelection = retained?.selection ?? (selection ? { ...selection } : undefined)
      if (originalSelection) {
        const envelope = { requestId, selection: originalSelection }
        // Save the full intent before dispatch; the ID alone cannot replay a request the server never received.
        try { sessionStorage.setItem(`${key}:evidence`, JSON.stringify(envelope)) } catch {
          if (!retained) throw new Error('Browser storage is unavailable. Restore it before completing selected evidence')
        }
        selectedRequests.current.set(key, envelope)
      }
      if (!originalSelection) {
        let precondition = completionPreconditions.current.get(key)
        if (!precondition) {
          const raw = sessionRequest(`${key}:precondition`)
          if (raw) {
            try { precondition = JSON.parse(raw) } catch { throw new Error('The saved completion counter needs recovery before another submission') }
            if (!precondition || precondition.requestId !== requestId || !Number.isSafeInteger(precondition.attempts) || precondition.attempts < 0) {
              throw new Error('The saved completion counter does not match this request. Keep the original reference and reload your course')
            }
          }
        }
        if (precondition && precondition.requestId !== requestId) throw new Error('The saved completion counter does not match this request. Keep the original reference and reload your course')
        // Older pending requests have no recorded counter. Preserve their
        // original replay contract instead of inventing a new precondition.
        if (!precondition && !existing && !resumeRequestId) {
          const attempts = progress?.modules[moduleId]?.attempts ?? 0
          if (!Number.isSafeInteger(attempts) || attempts < 0) throw new Error('Refresh the module completion history before submitting')
          precondition = { requestId, attempts }
        }
        if (precondition) {
          originalExpectedAttempts = precondition.attempts
          completionPreconditions.current.set(key, precondition)
          try { sessionStorage.setItem(`${key}:precondition`, JSON.stringify(precondition)) } catch { /* The current panel retains the original precondition. */ }
        }
      }
      completionRequests.current.set(key, requestId)
      try { sessionStorage.setItem(key, requestId) } catch { /* The current panel can still retry safely. */ }
      setCompletionRevision(value => value + 1)
    }
    const finishRequest = () => {
      if (!key) return
      completionRequests.current.delete(key)
      completionPreconditions.current.delete(key)
      try { sessionStorage.removeItem(`${key}:precondition`) } catch { /* The confirmed result remains authoritative. */ }
      selectedRequests.current.delete(key)
      try { sessionStorage.removeItem(`${key}:evidence`) } catch { /* The successful server result remains authoritative. */ }
      try { sessionStorage.removeItem(key) } catch { /* Storage is optional. */ }
      setCompletionRevision(value => value + 1)
    }
    if (key) completingRequests.current.add(key)
    try {
      const result = originalExpectedAttempts !== undefined
        ? await api.completeModule(moduleId, enrollmentId, requestId, undefined, originalExpectedAttempts)
        : originalSelection
        ? await api.completeModule(moduleId, enrollmentId, requestId, originalSelection)
        : requestId
        ? await api.completeModule(moduleId, enrollmentId, requestId)
        : await api.completeModule(moduleId, enrollmentId)
      if (originalSelection && (result.attempt_id !== requestId || result.module_id !== moduleId
        || result.enrollment_id !== enrollmentId || result.course_version !== course?.course_version
        || result.manifest_sha256 !== course?.manifest_sha256 || result.validation?.passed !== true)) {
        throw new Error('Completion could not be confirmed for this course. Retry the original request')
      }
      finishRequest()
      await refreshAfterWrite()
      return result
    } catch (error) {
      // A definite failed assessment ends this submission. Network/server
      // uncertainty retains its identity, including across a panel remount.
      if (error instanceof ApiError && error.status === 409 && error.code === 'CERTIFICATION_COMPLETION_CHANGED') {
        finishRequest()
        try { await refresh() } catch { /* Keep the refresh failure notice and original conflict. */ }
      } else if (error instanceof ApiError && error.status === 400) finishRequest()
      throw error
    } finally { if (key) completingRequests.current.delete(key) }
  }

  const provision = async (moduleId: string) => {
    return sharePendingAction('provision', moduleId, '', async () => {
      const result = await api.provisionModule(moduleId, progress?.enrollment_id)
      await refreshAfterWrite()
      return result
    })
  }

  const progressId = progress?.id
  const enrollmentId = progress?.enrollment_id
  const getExercise = useCallback(async (moduleId: string): Promise<CertExercise> => {
    if (!progressId) throw new Error('Load certification progress before opening an exercise')
    return api.getExercise(moduleId, enrollmentId)
  }, [progressId, enrollmentId])

  const submitAssessment = async (moduleId: string, answers: Record<string, string>) => {
    const originalAnswers = { ...answers }
    const body = JSON.stringify(Object.entries(originalAnswers).sort(([left], [right]) => left.localeCompare(right)))
    return sharePendingAction('reflection', moduleId, body, async () => {
      const result = await api.submitAssessment(moduleId, originalAnswers, progress?.enrollment_id)
      await refreshAfterWrite()
      return result
    })
  }

  const savePosition = async (moduleId: string, lessonId: string) => {
    if (!progress?.enrollment_id || positionWritePending.current) throw new Error('Wait for the current save before continuing')
    const enrollmentId = progress.enrollment_id
    positionWritePending.current = true
    // An older progress read must not replace this successfully saved cursor.
    ++requestVersion.current
    try {
      const result = await api.savePosition(enrollmentId, moduleId, lessonId, progress.position_revision ?? 0)
      if (result.enrollment_id !== enrollmentId) throw new Error('The saved position belongs to another course')
      ++requestVersion.current
      setProgress(previous => previous?.enrollment_id === enrollmentId ? {
        ...previous, learning_position: result.learning_position, position_revision: result.position_revision,
        modules: { ...previous.modules, [moduleId]: { ...previous.modules[moduleId], learning_position: result.learning_position } },
      } : previous)
    } catch (error) {
      observeCertificationJourney('position_save_failed', progress)
      throw error
    } finally {
      positionWritePending.current = false
      setLoading(false)
    }
  }

  const pendingCompletions: PendingCompletion[] = [...(progress?.pending_completions ?? [])]
  if (progress?.enrollment_id && course) {
    for (const module of course.modules) {
      const key = `certification-completion:${progress.enrollment_id}:${module.id}`
      let requestId = completionRequests.current.get(key)
      if (!requestId) {
        try { requestId = sessionStorage.getItem(key) ?? JSON.parse(sessionStorage.getItem(`${key}:evidence`) || 'null')?.requestId } catch { /* Memory remains available. */ }
      }
      if (requestId && /^[a-f0-9]{32}$/.test(requestId) && !pendingCompletions.some(item => item.attempt_id === requestId)) {
        pendingCompletions.push({ attempt_id: requestId, module_id: module.id, state: 'uncertain', in_flight: false })
      }
    }
  }

  return { pendingCompletions, progress, course, loading, refresh, refreshAfterWrite, refreshError, savedWritePendingRefresh, validate, complete, provision, getExercise, submitAssessment, savePosition }
}
