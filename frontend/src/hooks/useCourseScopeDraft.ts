import { useCourseDraft } from './useCourseDraft'

type ScopeDraft = { choice: 'approve' | 'hold'; reason: string }
type Run = { enrollment_id: string; manifest_sha256: string; run_id: string; plan_sha256: string; case_sha256: string; scope_decision_id: string | null; scope_decision_sha256: string | null }
const valid = (value: unknown): value is ScopeDraft => !!value && typeof value === 'object'
  && ['approve', 'hold'].includes((value as ScopeDraft).choice)
  && typeof (value as ScopeDraft).reason === 'string' && (value as ScopeDraft).reason.length <= 4000

/** A restored choice is still unsubmitted. Only the form's explicit save can authorize it. */
export function useCourseScopeDraft(kind: string, run: Run) {
  const [draft, setDraft, status] = useCourseDraft<ScopeDraft>(
    [kind, run.enrollment_id, run.manifest_sha256, run.run_id, run.plan_sha256, run.case_sha256, run.scope_decision_id, run.scope_decision_sha256],
    { choice: 'hold', reason: '' }, valid)
  return { ...draft, status,
    setChoice: (choice: ScopeDraft['choice']) => setDraft(value => ({ ...value, choice })),
    setReason: (reason: string) => setDraft(value => ({ ...value, reason })),
  }
}
