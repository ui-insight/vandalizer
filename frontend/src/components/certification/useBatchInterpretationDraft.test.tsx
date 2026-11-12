import type { ContextType, ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { AuthContext } from '../../contexts/AuthContext'
import { getBatchRun } from '../../api/batchAssessment'
import { verifyBatchRun } from './batchAssessmentState'
import { useBatchInterpretationDraft } from './useBatchInterpretationDraft'
import type { BatchList, BatchRun } from '../../types/batchAssessment'
vi.mock('../../api/batchAssessment', () => ({ getBatchRun: vi.fn() }))
vi.mock('./batchAssessmentState', () => ({ verifyBatchRun: vi.fn(value => value) }))
const original = { run_id: 'a'.repeat(32), run_sha256: 'b'.repeat(64), result_sha256: 'c'.repeat(64) } as BatchRun
const first = { run_id: 'd'.repeat(32), result_sha256: 'e'.repeat(64), phase: 'retry', state: 'completed', failed_source_id: 'proposal_2', parent_run: { run_sha256: original.run_sha256 } } as BatchRun
const second = { ...first, run_id: 'f'.repeat(32), result_sha256: '1'.repeat(64), failed_source_id: 'proposal_3' } as BatchRun
const listing = { enrollment_id: 'batch-draft-course', manifest_sha256: '2'.repeat(64), case: { case_sha256: '3'.repeat(64) } } as BatchList
function wrapper({ children }: { children: ReactNode }) { return <AuthContext.Provider value={{ user: { user_id: 'batch-learner' } } as NonNullable<ContextType<typeof AuthContext>>}>{children}</AuthContext.Provider> }
const useDraft = () => useBatchInterpretationDraft(listing, original, [first], '', null)
beforeEach(() => {
  sessionStorage.clear(); vi.clearAllMocks()
  vi.mocked(getBatchRun).mockImplementation(async (_enrollment, id) => structuredClone(id === first.run_id ? first : second))
})
it('restores the explanation and selected references but rereads their original owned receipts', async () => {
  let view = renderHook(useDraft, { wrapper })
  await waitFor(() => expect(view.result.current.restoring).toBe(false))
  act(() => view.result.current.setDraft({ answer: 'Original source-based recovery explanation.', reference: 'unfinished reference', retries: [first, second].map(run => ({ run_id: run.run_id, result_sha256: run.result_sha256! })) }))
  await waitFor(() => expect(view.result.current.retries).toHaveLength(2))
  view.unmount(); vi.mocked(getBatchRun).mockClear()
  view = renderHook(useDraft, { wrapper })
  expect(view.result.current.retries).toEqual([])
  expect(view.result.current.restoring).toBe(true)
  await waitFor(() => expect(view.result.current.retries).toHaveLength(2))
  expect(view.result.current.draft.answer).toBe('Original source-based recovery explanation.')
  expect(view.result.current.draft.reference).toBe('unfinished reference')
  expect(getBatchRun).toHaveBeenCalledTimes(2)
  expect(getBatchRun).toHaveBeenCalledWith(listing.enrollment_id, first.run_id)
  expect(verifyBatchRun).toHaveBeenCalledWith(second, listing)
})
it.each(['hash', 'parent', 'state', 'ownership'])('keeps the explanation but refuses a changed or unavailable %s receipt', async change => {
  const view = renderHook(useDraft, { wrapper })
  await waitFor(() => expect(view.result.current.restoring).toBe(false))
  act(() => view.result.current.setDraft(value => ({ ...value, answer: 'Keep my original explanation.' })))
  if (change === 'ownership') vi.mocked(getBatchRun).mockRejectedValue(new Error('Not available'))
  else vi.mocked(getBatchRun).mockResolvedValue({ ...first,
    ...(change === 'hash' ? { result_sha256: '0'.repeat(64) } : {}),
    ...(change === 'parent' ? { parent_run: { run_sha256: '0'.repeat(64) } } : {}),
    ...(change === 'state' ? { state: 'executing' } : {}),
  } as BatchRun)
  act(() => view.result.current.reread())
  expect(view.result.current.restoring).toBe(true)
  await waitFor(() => expect(view.result.current.restoreError).toContain('could not be verified'))
  expect(view.result.current.retries).toEqual([])
  expect(view.result.current.draft.answer).toBe('Keep my original explanation.')
  act(() => view.result.current.clearReferences())
  await waitFor(() => expect(view.result.current.restoring).toBe(false))
  expect(view.result.current.restoreError).toBe('')
  expect(view.result.current.draft.answer).toBe('Keep my original explanation.')
  expect(view.result.current.draft.retries).toEqual([])
})
it('ignores a delayed read after leaving the original draft', async () => {
  let resolve!: (run: BatchRun) => void
  vi.mocked(getBatchRun).mockReturnValueOnce(new Promise(done => { resolve = done }))
  const view = renderHook(useDraft, { wrapper })
  act(() => view.result.current.setDraft(value => ({ ...value, answer: 'Draft before leaving.' })))
  view.unmount()
  await act(async () => { resolve(first) })
  expect(JSON.parse(sessionStorage.getItem(sessionStorage.key(0)!)!).value.answer).toBe('Draft before leaving.')
})
