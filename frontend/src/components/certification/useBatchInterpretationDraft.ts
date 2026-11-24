import { useEffect, useState } from 'react'
import { getBatchRun } from '../../api/batchAssessment'
import { useCourseDraft } from '../../hooks/useCourseDraft'
import type { BatchList, BatchRun } from '../../types/batchAssessment'
import { verifyBatchRun } from './batchAssessmentState'

type Draft = { answer: string; reference: string; retries: { run_id: string; result_sha256: string }[] }
const id = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value)
const digest = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
function valid(value: unknown): value is Draft {
  if (!value || typeof value !== 'object') return false
  const draft = value as Draft
  return typeof draft.answer === 'string' && draft.answer.length <= 8000
    && typeof draft.reference === 'string' && draft.reference.length <= 128
    && Array.isArray(draft.retries) && draft.retries.length <= 3
    && new Set(draft.retries.map(item => item?.run_id)).size === draft.retries.length
    && draft.retries.every(item => item && id(item.run_id) && digest(item.result_sha256))
}

export function useBatchInterpretationDraft(listing: BatchList, original: BatchRun, initialRetries: BatchRun[], initialAnswer: string, previous: string | null) {
  const [draft, setDraft, status] = useCourseDraft<Draft>(
    ['batch-interpretation', listing.enrollment_id, listing.manifest_sha256, original.run_id, original.result_sha256, listing.case.case_sha256, previous],
    { answer: initialAnswer, reference: '', retries: initialRetries.map(run => ({ run_id: run.run_id, result_sha256: run.result_sha256! })) }, valid)
  const [refresh, setRefresh] = useState(0)
  const [loaded, setLoaded] = useState<{ key: string; items: BatchRun[]; error: string } | null>(null)
  // A tab stores references only. Re-read and verify original owned receipts;
  // restoring local JSON can never make it authoritative server evidence.
  const key = JSON.stringify([listing.enrollment_id, listing.manifest_sha256, original.run_sha256, draft.retries])
  useEffect(() => {
    let active = true
    void Promise.all(draft.retries.map(async reference => {
      const run = verifyBatchRun(await getBatchRun(listing.enrollment_id, reference.run_id), listing)
      if (run.run_id !== reference.run_id || run.result_sha256 !== reference.result_sha256
        || run.phase !== 'retry' || run.state !== 'completed' || !run.failed_source_id
        || run.parent_run?.run_sha256 !== original.run_sha256) throw new Error('Changed retry receipt')
      return run
    })).then(items => {
      if (new Set(items.map(run => run.failed_source_id)).size !== items.length) throw new Error('Duplicate source recovery')
      if (active) setLoaded({ key, items, error: '' })
    }).catch(() => {
      if (active) setLoaded({ key, items: [], error: 'The selected retry receipts could not be verified for this original batch. Your explanation is kept. Read the selected receipts again before saving.' })
    })
    return () => { active = false }
  }, [key, refresh, draft.retries, listing, original.run_sha256])
  const current = loaded?.key === key ? loaded : null
  return { draft, setDraft, status, retries: current?.items || [], restoring: !current,
    restoreError: current?.error || '', reread: () => { setLoaded(null); setRefresh(value => value + 1) },
    clearReferences: () => setDraft(value => ({ ...value, retries: [] })) }
}
