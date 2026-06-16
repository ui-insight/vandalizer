import { useEffect, useRef, useState } from 'react'
import { Brain, Loader2, Trash2 } from 'lucide-react'
import { getUserMemory, clearUserMemory, type UserMemoryResponse, type MemoryItem } from '../../api/chat'
import { useToast } from '../../contexts/ToastContext'

/** Format an ISO timestamp as a short relative age ("3d ago", "2h ago"). */
function relativeAge(iso: string): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return ''
  const secs = Math.max(0, (Date.now() - then) / 1000)
  if (secs < 90) return 'just now'
  const mins = secs / 60
  if (mins < 90) return `${Math.round(mins)}m ago`
  const hours = mins / 60
  if (hours < 36) return `${Math.round(hours)}h ago`
  const days = hours / 24
  if (days < 14) return `${Math.round(days)}d ago`
  const weeks = days / 7
  if (weeks < 9) return `${Math.round(weeks)}w ago`
  return `${Math.round(days / 30)}mo ago`
}

function MemoryGroup({ heading, items }: { heading: string; items: MemoryItem[] }) {
  if (!items.length) return null
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4, color: '#9ca3af', marginBottom: 4 }}>
        {heading}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {items.map((item, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 6, fontSize: 12 }}>
            <span style={{ color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
              {item.title}
            </span>
            <span style={{ color: '#9ca3af', fontSize: 11, flexShrink: 0 }}>
              {item.count}&times;{item.last_used ? ` · ${relativeAge(item.last_used)}` : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * Surfaces (and lets the user wipe) the behavioral memory the assistant keeps
 * for the current (user, team) scope — the same "Your patterns" the system
 * prompt references. Backs the otherwise-orphaned GET/DELETE /api/chat/memory.
 */
export function MemoryPanel() {
  const { toast } = useToast()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [memory, setMemory] = useState<UserMemoryResponse | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const load = () => {
    setLoading(true)
    getUserMemory()
      .then(setMemory)
      .catch(() => toast('Could not load memory', 'error'))
      .finally(() => setLoading(false))
  }

  const handleToggle = () => {
    const next = !open
    setOpen(next)
    if (next) load()
  }

  const handleClear = () => {
    if (!window.confirm('Forget everything the assistant has learned about your habits? This only affects the current team.')) return
    setClearing(true)
    clearUserMemory()
      .then((res) => {
        setMemory({ extractions: [], workflows: [], kbs: [] })
        toast(res.removed ? 'Memory cleared' : 'Nothing to clear', 'success')
      })
      .catch(() => toast('Could not clear memory', 'error'))
      .finally(() => setClearing(false))
  }

  const isEmpty = memory != null &&
    memory.extractions.length === 0 &&
    memory.workflows.length === 0 &&
    memory.kbs.length === 0

  return (
    <div ref={ref} className="relative">
      <button
        onClick={handleToggle}
        aria-expanded={open}
        aria-haspopup="dialog"
        title="What the assistant remembers about you"
        className="flex items-center justify-center rounded-[var(--ui-radius)] p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
      >
        <Brain className="h-4 w-4" />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Assistant memory"
          className="absolute right-0 z-[1000] rounded-[var(--ui-radius)] border bg-white"
          style={{ bottom: 'calc(100% + 8px)', width: 320, borderColor: 'rgba(0,0,0,0.14)', boxShadow: '0 10px 28px rgba(0,0,0,0.16)' }}
          onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }}
        >
          <div style={{ padding: '12px 14px', borderBottom: '1px solid #f3f4f6' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#1f2937' }}>What the assistant remembers</div>
            <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
              Habits it references to tailor suggestions. Scoped to your current team.
            </div>
          </div>

          <div style={{ padding: '12px 14px', maxHeight: 320, overflowY: 'auto' }}>
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#9ca3af', fontSize: 12, padding: '8px 0' }}>
                <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> Loading&hellip;
              </div>
            ) : isEmpty ? (
              <div style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.5 }}>
                Nothing remembered yet. As you run extractions, workflows, and query knowledge bases,
                the assistant notes what you use most so it can suggest the right tools.
              </div>
            ) : memory ? (
              <>
                <MemoryGroup heading="Extraction templates" items={memory.extractions} />
                <MemoryGroup heading="Workflows" items={memory.workflows} />
                <MemoryGroup heading="Knowledge bases" items={memory.kbs} />
              </>
            ) : null}
          </div>

          {!isEmpty && !loading && memory && (
            <div style={{ padding: '10px 14px', borderTop: '1px solid #f3f4f6', display: 'flex', justifyContent: 'flex-end' }}>
              <button
                onClick={handleClear}
                disabled={clearing}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  fontSize: 12, fontWeight: 500, padding: '5px 12px',
                  borderRadius: 8, border: '1px solid #fecaca',
                  background: '#fff', color: '#b91c1c',
                  cursor: clearing ? 'default' : 'pointer', opacity: clearing ? 0.6 : 1,
                }}
              >
                {clearing ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Trash2 size={12} />}
                Forget all
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
