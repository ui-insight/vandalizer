import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../api/certification'
import { ApiError } from '../api/client'
import type { CertificationProgress, CourseDefinition } from '../types/certification'
import { useCertification } from './useCertification'
import { observeCertificationJourney } from '../api/certificationJourney'
vi.mock('../api/certificationJourney', () => ({ observeCertificationJourney: vi.fn() }))
vi.mock('../api/certification', () => ({ getProgress: vi.fn(), getCourse: vi.fn(), validateModule: vi.fn(), getExercise: vi.fn(), completeModule: vi.fn(), provisionModule: vi.fn(), submitAssessment: vi.fn(), savePosition: vi.fn() }))
const progress: CertificationProgress = { id: 'p1', user_id: 'u1', modules: {}, total_xp: 0, level: 'beginner', certified: false, certified_at: null, last_activity_date: null }
beforeEach(() => { vi.resetAllMocks(); sessionStorage.clear(); vi.mocked(api.getProgress).mockResolvedValue(progress) })

it('observes initial and later read failures without treating either as a saved grade', async () => {
  vi.mocked(api.getProgress).mockRejectedValueOnce(new Error('PRIVATE initial error'))
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(observeCertificationJourney).toHaveBeenLastCalledWith('initial_progress_load_failed', null)
  await act(async () => { await result.current.refresh() })
  vi.mocked(api.getProgress).mockRejectedValueOnce(new Error('PRIVATE later error'))
  await act(async () => { await result.current.refresh() })
  expect(observeCertificationJourney).toHaveBeenLastCalledWith('progress_refresh_failed', null)
  expect(result.current.progress).toEqual(progress)
  expect(JSON.stringify(vi.mocked(observeCertificationJourney).mock.calls)).not.toContain('PRIVATE')
})

it.each(['reflection', 'provision', 'validate'] as const)('coalesces simultaneous %s actions through response and refresh', async kind => {
  let finish!: () => void
  const pending = new Promise<never>(resolve => { finish = () => resolve(undefined as never) })
  const endpoint = kind === 'reflection' ? api.submitAssessment : kind === 'provision' ? api.provisionModule : api.validateModule
  vi.mocked(endpoint).mockReturnValue(pending)
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  const submit = () => kind === 'reflection' ? result.current.submitAssessment('ai_literacy', { experience: 'Some' })
    : kind === 'provision' ? result.current.provision('foundations') : result.current.validate('foundations')
  await act(async () => {
    const first = submit()
    const second = submit()
    await Promise.resolve()
    expect(endpoint).toHaveBeenCalledTimes(1)
    finish()
    await Promise.all([first, second])
  })
  expect(api.getProgress).toHaveBeenCalledTimes(kind === 'validate' ? 1 : 2)
})

it('does not submit changed reflection answers over a pending save and allows an explicit retry after failure', async () => {
  let fail!: (error: Error) => void
  vi.mocked(api.submitAssessment).mockImplementationOnce(() => new Promise((_, reject) => { fail = reject }))
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  await act(async () => {
    const first = result.current.submitAssessment('ai_literacy', { experience: 'Original' })
    const failed = expect(first).rejects.toThrow('Offline')
    await Promise.resolve()
    await expect(result.current.submitAssessment('ai_literacy', { experience: 'Changed' })).rejects.toThrow(/pending/)
    expect(api.submitAssessment).toHaveBeenCalledTimes(1)
    fail(new Error('Offline'))
    await failed
  })
  vi.mocked(api.submitAssessment).mockResolvedValueOnce({ stored: true })
  await act(async () => { await result.current.submitAssessment('ai_literacy', { experience: 'Original' }) })
  expect(api.submitAssessment).toHaveBeenCalledTimes(2)
})

it('keeps identical reflection saves coalesced while the confirmed write awaits its progress read', async () => {
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  let finishRead!: (value: CertificationProgress) => void
  vi.mocked(api.getProgress).mockImplementationOnce(() => new Promise(resolve => { finishRead = resolve }))
  vi.mocked(api.submitAssessment).mockResolvedValue({ stored: true })
  let first!: Promise<unknown>
  await act(async () => { first = result.current.submitAssessment('ai_literacy', { experience: 'Some', comfort: 'Open' }) })
  expect(result.current.savedWritePendingRefresh).toBe(true)
  await act(async () => {
    const same = result.current.submitAssessment('ai_literacy', { comfort: 'Open', experience: 'Some' })
    await Promise.resolve()
    expect(api.submitAssessment).toHaveBeenCalledTimes(1)
    finishRead(progress)
    await Promise.all([first, same])
  })
  expect(api.getProgress).toHaveBeenCalledTimes(2)
})

it('freezes reflection arguments before deferred dispatch and isolates different modules', async () => {
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  const answers = { experience: 'Original' }
  await act(async () => {
    const first = result.current.submitAssessment('ai_literacy', answers)
    answers.experience = 'Changed outside the form'
    const other = result.current.submitAssessment('process_mapping', { process: 'Original process' })
    await Promise.all([first, other])
  })
  expect(api.submitAssessment).toHaveBeenCalledTimes(2)
  expect(api.submitAssessment).toHaveBeenCalledWith('ai_literacy', { experience: 'Original' }, undefined)
  expect(api.submitAssessment).toHaveBeenCalledWith('process_mapping', { process: 'Original process' }, undefined)
})

it('does not dispatch an unbound action before course progress loads', async () => {
  vi.mocked(api.getProgress).mockImplementationOnce(() => new Promise(() => {}))
  const { result } = renderHook(useCertification)
  await expect(result.current.submitAssessment('ai_literacy', { experience: 'Some' })).rejects.toThrow(/Load course progress/)
  await expect(result.current.provision('foundations')).rejects.toThrow(/Load course progress/)
  await expect(result.current.validate('foundations')).rejects.toThrow(/Load course progress/)
  await expect(result.current.complete('foundations')).rejects.toThrow(/Load course progress/)
  expect(api.completeModule).not.toHaveBeenCalled()
  expect(api.submitAssessment).not.toHaveBeenCalled()
  expect(api.provisionModule).not.toHaveBeenCalled()
  expect(api.validateModule).not.toHaveBeenCalled()
})
it('retains a learner-scoped legacy completion reference after a lost response and remount', async () => {
  vi.mocked(api.completeModule).mockRejectedValueOnce(new Error('Response lost'))
  const first = renderHook(useCertification)
  await waitFor(() => expect(first.result.current.progress).toEqual(progress))
  await act(async () => { await expect(first.result.current.complete('ai_literacy')).rejects.toThrow('Response lost') })
  const requestId = vi.mocked(api.completeModule).mock.calls[0][2]
  expect(requestId).toMatch(/^[a-f0-9]{32}$/)
  first.unmount()
  const second = renderHook(useCertification)
  await waitFor(() => expect(second.result.current.progress).toEqual(progress))
  vi.mocked(api.completeModule).mockResolvedValueOnce({ module_id: 'ai_literacy', stars: 3, xp_earned: 125, total_xp: 125, level: 'apprentice', level_up: true, certified: false, validation: { passed: true, stars: 3, checks: [] }, attempt_id: requestId })
  await act(async () => { await second.result.current.complete('ai_literacy') })
  expect(api.completeModule).toHaveBeenLastCalledWith('ai_literacy', undefined, requestId, undefined, 0)
  expect(sessionStorage.getItem('certification-completion:legacy:u1:p1:ai_literacy')).toBeNull()
})
it('retains saved work and retries only the read after a write succeeds but refresh fails', async () => {
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  vi.mocked(api.getProgress).mockRejectedValueOnce(new Error('offline'))
  await act(async () => { await result.current.refreshAfterWrite() })
  expect(result.current.progress).toEqual(progress)
  expect(result.current.savedWritePendingRefresh).toBe(true)
  expect(result.current.refreshError).toBeTruthy()
  vi.mocked(api.getProgress).mockResolvedValueOnce({ ...progress, total_xp: 100 })
  await act(async () => { await result.current.refresh() })
  expect(result.current.progress?.total_xp).toBe(100)
  expect(result.current.savedWritePendingRefresh).toBe(false)
  expect(result.current.refreshError).toBeNull()
  expect(api.completeModule).not.toHaveBeenCalled()
  expect(api.provisionModule).not.toHaveBeenCalled()
  expect(api.submitAssessment).not.toHaveBeenCalled()
})
it('ignores an older progress read that finishes after the post-write read', async () => {
  let resolveOld!: (p: CertificationProgress) => void
  vi.mocked(api.getProgress).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
  const { result } = renderHook(useCertification)
  vi.mocked(api.getProgress).mockResolvedValueOnce({ ...progress, total_xp: 200 })
  await act(async () => { await result.current.refreshAfterWrite() })
  await act(async () => { resolveOld(progress) })
  expect(result.current.progress?.total_xp).toBe(200)
})
it('distinguishes initial load failure from a saved write awaiting refresh', async () => {
  vi.mocked(api.getProgress).mockRejectedValueOnce(new Error('offline'))
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.refreshError).toBeTruthy())
  expect(result.current.savedWritePendingRefresh).toBe(false)
  expect(result.current.progress).toBeNull()
})

const versionedProgress = { ...progress, enrollment_id: 'enrollment-a', course_version: 'course-a', manifest_sha256: 'hash-a' }
const course: CourseDefinition = {
  versioned: true, enrollment_id: 'enrollment-a', course_version: 'course-a', manifest_sha256: 'hash-a',
  course_title: 'Your existing course', modules_total: 0, maximum_xp: 2675,
  modules: [], levels: [], tiers: [], prerequisites: {},
}

it('loads a matching course once and pins subsequent writes to its enrollment', async () => {
  vi.mocked(api.getProgress).mockResolvedValue(versionedProgress)
  vi.mocked(api.getCourse).mockResolvedValue(course)
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.course).toEqual(course))
  await act(async () => { await result.current.submitAssessment('ai_literacy', { experience: 'Some' }) })
  expect(api.submitAssessment).toHaveBeenCalledWith('ai_literacy', { experience: 'Some' }, 'enrollment-a')
  expect(api.getCourse).toHaveBeenCalledTimes(1)
  expect(result.current.progress?.course_version).toBe('course-a')
})

it('keeps the saved course and progress together when a new definition cannot be loaded', async () => {
  vi.mocked(api.getProgress).mockResolvedValue(versionedProgress)
  vi.mocked(api.getCourse).mockResolvedValue(course)
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.course).toEqual(course))
  vi.mocked(api.getProgress).mockResolvedValueOnce({ ...versionedProgress, enrollment_id: 'enrollment-b', course_version: 'course-b', manifest_sha256: 'hash-b' })
  vi.mocked(api.getCourse).mockRejectedValueOnce(new Error('unavailable'))
  await act(async () => { await result.current.refresh() })
  expect(result.current.progress).toEqual(versionedProgress)
  expect(result.current.course).toEqual(course)
  expect(result.current.refreshError).toBeTruthy()
})

it('rejects a mismatched course definition before displaying progress', async () => {
  vi.mocked(api.getProgress).mockResolvedValue(versionedProgress)
  vi.mocked(api.getCourse).mockResolvedValue({ ...course, manifest_sha256: 'different-hash' })
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(result.current.progress).toBeNull()
  expect(result.current.course).toBeNull()
  expect(result.current.refreshError).toBeTruthy()
})

it('does not replace a pinned course with an unversioned fallback after a server change', async () => {
  vi.mocked(api.getProgress).mockResolvedValue(versionedProgress)
  vi.mocked(api.getCourse).mockResolvedValue(course)
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.course).toEqual(course))
  vi.mocked(api.getProgress).mockResolvedValueOnce(progress)
  await act(async () => { await result.current.refresh() })
  expect(result.current.progress).toEqual(versionedProgress)
  expect(result.current.course).toEqual(course)
  expect(result.current.refreshError).toBeTruthy()
})


it('saves navigation without changing credit and uses the latest position revision', async () => {
  const savedPlace = { module_id: 'ai_literacy', lesson_id: 'lesson-2', revision: 1, content_sha256: 'content', saved_at: '2026-10-05' }
  vi.mocked(api.getProgress).mockResolvedValue({ ...versionedProgress, total_xp: 125, position_revision: 7 })
  vi.mocked(api.getCourse).mockResolvedValue(course)
  vi.mocked(api.savePosition).mockResolvedValue({ saved: true, enrollment_id: 'enrollment-a', course_version: 'course-a', learning_position: savedPlace, position_revision: 8 })
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.course).toEqual(course))
  await act(async () => { await result.current.savePosition('ai_literacy', 'lesson-2') })
  expect(api.savePosition).toHaveBeenCalledWith('enrollment-a', 'ai_literacy', 'lesson-2', 7)
  expect(result.current.progress?.learning_position).toEqual(savedPlace)
  expect(result.current.progress?.total_xp).toBe(125)
  vi.mocked(api.savePosition).mockRejectedValueOnce(new Error('Another session changed your place'))
  await act(async () => { await expect(result.current.savePosition('ai_literacy', 'lesson-3')).rejects.toThrow('Another session') })
  expect(api.savePosition).toHaveBeenLastCalledWith('enrollment-a', 'ai_literacy', 'lesson-3', 8)
  expect(result.current.progress?.learning_position).toEqual(savedPlace)
  expect(api.completeModule).not.toHaveBeenCalled()
})

it('retains a completion identity after an uncertain response and panel remount', async () => {
  vi.mocked(api.getProgress).mockResolvedValue(versionedProgress)
  vi.mocked(api.getCourse).mockResolvedValue(course)
  vi.mocked(api.completeModule).mockRejectedValueOnce(new Error('Response lost'))
  const first = renderHook(useCertification)
  await waitFor(() => expect(first.result.current.course).toEqual(course))
  await act(async () => { await expect(first.result.current.complete('ai_literacy')).rejects.toThrow('Response lost') })
  const requestId = vi.mocked(api.completeModule).mock.calls[0][2]
  expect(requestId).toMatch(/^[a-f0-9]{32}$/)
  first.unmount()
  const second = renderHook(useCertification)
  await waitFor(() => expect(second.result.current.course).toEqual(course))
  vi.mocked(api.completeModule).mockResolvedValueOnce({ module_id: 'ai_literacy', stars: 1, xp_earned: 100, total_xp: 100, level: 'novice', level_up: false, certified: false, validation: { passed: true, stars: 1, checks: [] }, attempt_id: requestId })
  await act(async () => { await second.result.current.complete('ai_literacy') })
  expect(api.completeModule).toHaveBeenLastCalledWith('ai_literacy', 'enrollment-a', requestId, undefined, 0)
  expect(sessionStorage.getItem('certification-completion:enrollment-a:ai_literacy')).toBeNull()
})

it('uses a new request after a definite failed assessment', async () => {
  vi.mocked(api.getProgress).mockResolvedValue(versionedProgress)
  vi.mocked(api.getCourse).mockResolvedValue(course)
  vi.mocked(api.completeModule).mockRejectedValue(new ApiError(400, 'Validation did not pass'))
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.course).toEqual(course))
  for (let retry = 0; retry < 2; retry++) {
    await act(async () => { await expect(result.current.complete('ai_literacy')).rejects.toThrow('Validation did not pass') })
  }
  const calls = vi.mocked(api.completeModule).mock.calls
  expect(calls[0][2]).not.toEqual(calls[1][2])
  expect(sessionStorage.getItem('certification-completion:enrollment-a:ai_literacy')).toBeNull()
})

it('resumes a server-recorded submission on another device without inventing a new request', async () => {
  const attempt = { attempt_id: 'a'.repeat(32), module_id: 'ai_literacy', state: 'graded' as const, in_flight: false }
  vi.mocked(api.getProgress).mockResolvedValue({ ...versionedProgress, pending_completions: [attempt] })
  vi.mocked(api.getCourse).mockResolvedValue(course)
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.pendingCompletions).toEqual([attempt]))
  expect(api.completeModule).not.toHaveBeenCalled()
  vi.mocked(api.completeModule).mockResolvedValueOnce({ module_id: 'ai_literacy', stars: 1, xp_earned: 100, total_xp: 100, level: 'novice', level_up: false, certified: false, validation: { passed: true, stars: 1, checks: [] }, attempt_id: attempt.attempt_id })
  await act(async () => { await result.current.complete('ai_literacy', attempt.attempt_id) })
  expect(api.completeModule).toHaveBeenCalledWith('ai_literacy', 'enrollment-a', attempt.attempt_id)
})

it('does not offer a stored submission from another selected course', async () => {
  sessionStorage.setItem('certification-completion:another-enrollment:ai_literacy', 'b'.repeat(32))
  vi.mocked(api.getProgress).mockResolvedValue(versionedProgress)
  vi.mocked(api.getCourse).mockResolvedValue(course)
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.course).toEqual(course))
  expect(result.current.pendingCompletions).toEqual([])
})

const selected = { review_attempt_id: '1'.repeat(32), scenario_attempt_id: '2'.repeat(32) }
const completionCourse = { ...course, selected_outcome_completion: true, modules: [{ id: 'validation_qa' }] } as CourseDefinition
function completionResponse(moduleId: string, _enrollmentId?: string, attempt_id?: string) {
  return Promise.resolve({ ...versionedProgress, attempt_id, module_id: moduleId, stars: 1, xp_earned: 100, level_up: false, validation: { passed: true, stars: 1, checks: [] } })
}
async function selectedHook() {
  vi.mocked(api.getProgress).mockResolvedValue(versionedProgress)
  vi.mocked(api.getCourse).mockResolvedValue(completionCourse)
  const hook = renderHook(useCertification)
  await waitFor(() => expect(hook.result.current.course).toEqual(completionCourse))
  return hook
}
it('retains full explicit intent across remount when the server never received the request', async () => {
  const first = await selectedHook()
  vi.mocked(api.completeModule).mockRejectedValueOnce(new Error('Request never arrived'))
  await act(async () => { await expect(first.result.current.complete('validation_qa', undefined, selected)).rejects.toThrow('never arrived') })
  const original = vi.mocked(api.completeModule).mock.calls[0]
  expect(original[3]).toEqual(selected)
  first.unmount()
  const second = await selectedHook()
  expect(second.result.current.pendingCompletions).toHaveLength(1)
  vi.mocked(api.completeModule).mockImplementation(completionResponse)
  await act(async () => { await second.result.current.complete('validation_qa', original[2]) })
  expect(api.completeModule).toHaveBeenLastCalledWith(...original)
  expect(second.result.current.pendingCompletions).toEqual([])
  expect(sessionStorage.getItem('certification-completion:enrollment-a:validation_qa:evidence')).toBeNull()
})
it('cannot replace uncertain evidence with newer passing work', async () => {
  const { result } = await selectedHook()
  vi.mocked(api.completeModule).mockRejectedValueOnce(new Error('offline'))
  await act(async () => { await expect(result.current.complete('validation_qa', undefined, selected)).rejects.toThrow() })
  await act(async () => { await expect(result.current.complete('validation_qa', undefined, { ...selected, review_attempt_id: '3'.repeat(32) })).rejects.toThrow('original evidence') })
  expect(api.completeModule).toHaveBeenCalledTimes(1)
})
it('prevents duplicate dispatch while a selected completion is in flight', async () => {
  const { result } = await selectedHook()
  let finish!: () => void
  vi.mocked(api.completeModule).mockImplementation((module, enrollment, id) => new Promise(resolve => { finish = () => { void completionResponse(module, enrollment, id).then(resolve) } }))
  await act(async () => {
    const pending = result.current.complete('validation_qa', undefined, selected)
    await expect(result.current.complete('validation_qa', undefined, selected)).rejects.toThrow('already being checked')
    finish(); await pending
  })
  expect(api.completeModule).toHaveBeenCalledTimes(1)
})
it('requires explicit course capability and valid references before a new selected write', async () => {
  const { result } = await selectedHook()
  await act(async () => { await expect(result.current.complete('unknown', undefined, selected)).rejects.toThrow('unavailable') })
  await act(async () => { await expect(result.current.complete('validation_qa', undefined, { review_attempt_id: 'latest' })).rejects.toThrow('references') })
  expect(api.completeModule).not.toHaveBeenCalled()
})
it('retains the original request when a completion response has a foreign identity', async () => {
  const { result } = await selectedHook()
  vi.mocked(api.completeModule).mockImplementation(async (...args) => ({ ...await completionResponse(args[0], args[1], args[2]), enrollment_id: 'another' }))
  await act(async () => { await expect(result.current.complete('validation_qa', undefined, selected)).rejects.toThrow('could not be confirmed') })
  expect(result.current.pendingCompletions).toHaveLength(1)
})
it('does not lose successful completion when progress refresh fails', async () => {
  const { result } = await selectedHook()
  vi.mocked(api.completeModule).mockImplementation(completionResponse)
  vi.mocked(api.getProgress).mockRejectedValueOnce(new Error('offline'))
  await act(async () => { await result.current.complete('validation_qa', undefined, selected) })
  expect(result.current.savedWritePendingRefresh).toBe(true)
  expect(result.current.pendingCompletions).toEqual([])
  await act(async () => { await expect(result.current.complete('validation_qa', undefined, selected)).rejects.toThrow('Refresh course progress') })
  expect(api.completeModule).toHaveBeenCalledTimes(1)
})
it('starts a new request after a definite failed selected assessment', async () => {
  const { result } = await selectedHook()
  vi.mocked(api.completeModule).mockRejectedValueOnce(new ApiError(400, 'Required outcome failed'))
  await act(async () => { await expect(result.current.complete('validation_qa', undefined, selected)).rejects.toThrow('failed') })
  vi.mocked(api.completeModule).mockImplementation(completionResponse)
  await act(async () => { await result.current.complete('validation_qa', undefined, { ...selected, review_attempt_id: '3'.repeat(32) }) })
  const calls = vi.mocked(api.completeModule).mock.calls
  expect(calls[1][2]).not.toEqual(calls[0][2])
  expect(calls[1][3]?.review_attempt_id).toBe('3'.repeat(32))
})
it('keeps unsupported and draft courses unable to submit selected completion', async () => {
  vi.mocked(api.getProgress).mockResolvedValue(versionedProgress)
  vi.mocked(api.getCourse).mockResolvedValue({ ...completionCourse, selected_outcome_completion: false })
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.course).not.toBeNull())
  await act(async () => { await expect(result.current.complete('validation_qa', undefined, selected)).rejects.toThrow('unavailable') })
  expect(api.completeModule).not.toHaveBeenCalled()
})
it('never sends a fresh selected write when its complete retry intent cannot be stored', async () => {
  const { result } = await selectedHook()
  const store = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage denied') })
  try {
    await act(async () => { await expect(result.current.complete('validation_qa', undefined, selected)).rejects.toThrow('Browser storage is unavailable') })
    expect(api.completeModule).not.toHaveBeenCalled()
    expect(result.current.pendingCompletions).toEqual([])
  } finally { store.mockRestore() }
})


it('retains the original completion counter after a lost response even if reopened progress advanced', async () => {
  vi.mocked(api.completeModule).mockRejectedValueOnce(new Error('Lost response'))
  const first = renderHook(useCertification)
  await waitFor(() => expect(first.result.current.loading).toBe(false))
  await act(async () => { await expect(first.result.current.complete('ai_literacy')).rejects.toThrow('Lost response') })
  const original = vi.mocked(api.completeModule).mock.calls[0]
  expect(original[4]).toBe(0)
  first.unmount()
  vi.mocked(api.getProgress).mockResolvedValue({ ...progress, modules: { ai_literacy: { attempts: 2, completed: true, stars: 1, completed_at: null, xp_earned: 125 } } })
  const second = renderHook(useCertification)
  await waitFor(() => expect(second.result.current.loading).toBe(false))
  await act(async () => { await second.result.current.complete('ai_literacy') })
  expect(api.completeModule).toHaveBeenLastCalledWith(...original)
  expect(sessionStorage.getItem('certification-completion:legacy:u1:p1:ai_literacy:precondition')).toBeNull()
})

it('refreshes a definite stale completion conflict without automatically retrying it', async () => {
  const failure = new ApiError(409, 'Module completion changed')
  failure.code = 'CERTIFICATION_COMPLETION_CHANGED'
  vi.mocked(api.completeModule).mockRejectedValueOnce(failure)
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  vi.mocked(api.getProgress).mockResolvedValue({ ...progress, modules: { ai_literacy: { attempts: 1, completed: true, stars: 1, completed_at: null, xp_earned: 125 } } })
  await act(async () => { await expect(result.current.complete('ai_literacy')).rejects.toThrow('Module completion changed') })
  expect(api.completeModule).toHaveBeenCalledOnce()
  expect(result.current.progress?.modules.ai_literacy.attempts).toBe(1)
  expect(sessionStorage.getItem('certification-completion:legacy:u1:p1:ai_literacy')).toBeNull()
  expect(sessionStorage.getItem('certification-completion:legacy:u1:p1:ai_literacy:precondition')).toBeNull()
  await act(async () => { await result.current.complete('ai_literacy') })
  const calls = vi.mocked(api.completeModule).mock.calls
  expect(calls[1][2]).not.toBe(calls[0][2])
  expect(calls[1][4]).toBe(1)
})

it('rejects a stored completion counter belonging to another request before sending', async () => {
  const key = 'certification-completion:legacy:u1:p1:ai_literacy'
  sessionStorage.setItem(key, 'a'.repeat(32))
  sessionStorage.setItem(`${key}:precondition`, JSON.stringify({ requestId: 'b'.repeat(32), attempts: 0 }))
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  await act(async () => { await expect(result.current.complete('ai_literacy')).rejects.toThrow('does not match this request') })
  expect(api.completeModule).not.toHaveBeenCalled()
  expect(sessionStorage.getItem(key)).toBe('a'.repeat(32))
})


it('cannot reuse an in-memory completion counter for a different resume reference', async () => {
  vi.mocked(api.completeModule).mockRejectedValueOnce(new Error('Lost response'))
  const { result } = renderHook(useCertification)
  await waitFor(() => expect(result.current.loading).toBe(false))
  await act(async () => { await expect(result.current.complete('ai_literacy')).rejects.toThrow('Lost response') })
  await act(async () => { await expect(result.current.complete('ai_literacy', 'f'.repeat(32))).rejects.toThrow('does not match this request') })
  expect(api.completeModule).toHaveBeenCalledOnce()
})
