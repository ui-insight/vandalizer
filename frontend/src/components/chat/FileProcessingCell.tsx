import { Loader2, Check, AlertCircle, FileText } from 'lucide-react'
import { stageCopy } from '../../utils/processingStatus'

export interface ProcessingCellDoc {
  uuid: string
  name: string
  /** Backend `task_status` stage, used for stage copy + progress. */
  status: string | null
  phase: 'processing' | 'ready' | 'error'
}

interface Props {
  docs: ProcessingCellDoc[]
}

/**
 * In-conversation cell that shows the live processing state of files dropped /
 * attached to the chat. Lives at the tail of the message stream so the user can
 * watch a dropped file move through extraction → indexing and see a clear
 * "Ready" confirmation without scrolling up to the attachment bar. Empty docs
 * → renders nothing; the parent decides when to mount it.
 */
export function FileProcessingCell({ docs }: Props) {
  if (docs.length === 0) return null

  const anyProcessing = docs.some(d => d.phase === 'processing')
  const anyError = docs.some(d => d.phase === 'error')
  const count = docs.length

  const headline = anyProcessing
    ? count > 1 ? `Preparing ${count} files…` : 'Preparing your file…'
    : anyError
      ? count > 1 ? 'Files processed' : 'File processed'
      : count > 1 ? 'Files ready' : 'Ready to continue'

  const subtitle = anyProcessing
    ? 'You can keep typing — I’ll answer as soon as it’s ready.'
    : anyError
      ? 'Some files had trouble processing. You can still ask about the rest.'
      : 'Your file is indexed and ready to analyze.'

  return (
    <div
      style={{
        marginBottom: 15,
        borderRadius: 'var(--ui-radius, 12px)',
        border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, #e5e7eb)',
        background: 'color-mix(in srgb, var(--highlight-color, #eab308) 5%, white)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px' }}>
        <div className="shrink-0">
          {anyProcessing
            ? <Loader2 className="h-5 w-5 animate-spin" style={{ color: 'var(--highlight-color, #eab308)' }} />
            : anyError
              ? <AlertCircle className="h-5 w-5" style={{ color: '#d97706' }} />
              : <Check className="h-5 w-5" style={{ color: '#16a34a' }} />}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#191919' }}>{headline}</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 1 }}>{subtitle}</div>
        </div>
      </div>

      {/* Per-file rows */}
      <div style={{ borderTop: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 18%, #f3f4f6)' }}>
        {docs.map((d) => {
          const copy = stageCopy(d.status)
          return (
            <div key={d.uuid} style={{ padding: '8px 14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {d.phase === 'processing'
                  ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" style={{ color: 'var(--highlight-color, #eab308)' }} />
                  : d.phase === 'error'
                    ? <AlertCircle className="h-3.5 w-3.5 shrink-0" style={{ color: '#d97706' }} />
                    : <Check className="h-3.5 w-3.5 shrink-0" style={{ color: '#16a34a' }} />}
                <FileText className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                <span style={{ flex: 1, minWidth: 0, fontSize: 13, color: '#374151' }} className="truncate">{d.name}</span>
                <span style={{ fontSize: 11, color: d.phase === 'error' ? '#d97706' : d.phase === 'ready' ? '#16a34a' : '#6b7280' }}>
                  {d.phase === 'processing' ? copy.short : d.phase === 'error' ? 'Couldn’t process' : 'Ready'}
                </span>
              </div>
              {d.phase === 'processing' && (
                <div style={{ marginTop: 6, marginLeft: 24, height: 3, borderRadius: 2, background: 'color-mix(in srgb, var(--highlight-color, #eab308) 18%, #e5e7eb)', overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      borderRadius: 2,
                      background: 'var(--highlight-color, #eab308)',
                      width: `${Math.round(copy.progress * 100)}%`,
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
