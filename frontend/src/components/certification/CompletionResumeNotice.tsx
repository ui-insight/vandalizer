import type { ModuleDefinition, PendingCompletion } from '../../types/certification'
import type { CourseIdentity } from '../../types/certification'
import { certificationSupportDraft } from '../../lib/certificationSupport'
import { openSupportDraft } from '../../utils/supportPanel'

export function CompletionResumeNotice({ pending = [], modules, busy, onOpen, onRetry, onRefresh, course, onHelp }: {
  pending?: PendingCompletion[]
  modules: ModuleDefinition[]
  busy: boolean
  onOpen: (moduleId: string) => void
  onRetry: (moduleId: string, requestId: string) => void
  onRefresh: () => void
  course?: CourseIdentity | null
  onHelp?: () => void
}) {
  if (!pending.length) return null
  return (
    <section aria-label="Pending certification completion" className="shrink-0 border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      {pending.map(item => {
        const module = modules.find(candidate => candidate.id === item.module_id)
        if (!module) return null
        const needsReview = item.state === 'review' || (item.state === 'evaluating' && !item.in_flight)
        return (
          <div key={item.attempt_id} className="space-y-2">
            <p className="font-semibold">{module.title}: completion needs confirmation</p>
            <p>{item.in_flight ? 'Your submission is still being processed. Refresh its status before trying again.'
              : needsReview ? 'This submission needs review before it can continue. Your existing credit is preserved.'
              : 'Resume this original completion request. It may finish validation and save credit; credit already earned will not be awarded again.'}</p>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => onOpen(item.module_id)} className="rounded border border-amber-700 px-3 py-2 font-medium">Open module</button>
              {!needsReview && !item.in_flight && <button type="button" disabled={busy} onClick={() => onRetry(item.module_id, item.attempt_id)} className="rounded bg-amber-900 px-3 py-2 font-medium text-white disabled:opacity-60">{busy ? 'Resuming original completion…' : 'Resume original completion'}</button>}
              <button type="button" disabled={busy} onClick={onRefresh} className="rounded border border-amber-700 px-3 py-2 font-medium disabled:opacity-60">Refresh status</button>
              {needsReview && <button type="button" onClick={() => {
                onHelp?.()
                openSupportDraft(certificationSupportDraft(course ?? {}, module, item))
              }} className="rounded border border-amber-700 px-3 py-2 font-medium">Prepare support request</button>}
            </div>
            {needsReview && <p className="text-xs">Opens an editable draft with this assessment’s reference. Review it before sending.</p>}
          </div>
        )
      })}
    </section>
  )
}
