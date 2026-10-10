import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { AlertTriangle, CalendarClock, Check, EyeOff, FileText, Inbox } from 'lucide-react'
import { getInbox, setInboxHidden, setObligationDismissed, setObligationDone } from '../../api/obligations'
import type { Obligation } from '../../api/obligations'
import { useWorkspace } from '../../contexts/WorkspaceContext'

// The RA inbox (#999): what each proposal or award needs, from its own
// documents, every row cited to its page. Done is shared with the project;
// Dismiss and Hide inbox only change this person's Home.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function dueLabel(item: Obligation): string {
  if (!item.due_at) return ''
  const [y, m, d] = item.due_at.slice(0, 10).split('-').map(Number)
  const date = `${MONTHS[m - 1]} ${d}, ${y}`
  return item.due_text ? `${date}, ${item.due_text}` : date
}

function daysUntil(item: Obligation): number | null {
  if (!item.due_at) return null
  const [y, m, d] = item.due_at.slice(0, 10).split('-').map(Number)
  const due = Date.UTC(y, m - 1, d)
  const now = new Date()
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())
  return Math.round((due - today) / 86_400_000)
}

function money(value: number | null, unit: string | null): string {
  if (value == null) return ''
  return unit === '%' ? `${value}%` : `${unit === '$' ? '$' : ''}${value.toLocaleString('en-US')}`
}

function summary(item: Obligation): string {
  if (item.kind === 'deadline') return dueLabel(item)
  if (item.kind === 'limit') {
    const verdict = item.in_conflict ? 'exceeds' : 'within'
    return `${money(item.observed_value, item.unit)} ${verdict} the ${money(item.limit_value, item.unit)} limit`
  }
  return 'Still needed'
}

function urgency(item: Obligation): string | null {
  const days = daysUntil(item)
  if (days == null) return null
  if (days < 0) return `${-days} day${days === -1 ? '' : 's'} past`
  if (days === 0) return 'today'
  if (days <= 14) return `in ${days} day${days === 1 ? '' : 's'}`
  return null
}

const BUTTON = {
  display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)',
  padding: 'var(--workspace-space-4) var(--workspace-space-8)', fontSize: 'var(--workspace-font-meta)',
  fontFamily: 'inherit', borderRadius: 'var(--workspace-radius-small)', cursor: 'pointer',
  border: '1px solid var(--workspace-border)', backgroundColor: '#fff', color: '#374151',
} as const

function InboxRow({ item, onChanged, onError }: {
  item: Obligation
  onChanged: (uuid: string, change: 'done' | 'dismissed') => void
  onError: (message: string) => void
}) {
  const navigate = useNavigate()
  const { viewDocument } = useWorkspace()
  const [busy, setBusy] = useState(false)
  const source = item.sources[0]
  const soon = urgency(item)
  const Icon = item.kind === 'deadline' ? CalendarClock : item.kind === 'limit' ? AlertTriangle : FileText
  const alert = item.in_conflict || (soon != null && (daysUntil(item) ?? 99) <= 7)

  const act = async (change: 'done' | 'dismissed', fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true)
    try {
      await fn()
      onChanged(item.uuid, change)
    } catch (e) {
      onError(e instanceof Error ? e.message : 'That change could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <li style={{ display: 'flex', gap: 'var(--workspace-space-8)', padding: 'var(--workspace-space-8) var(--workspace-space-12)', borderRadius: 'var(--workspace-radius-medium)', listStyle: 'none' }}>
      <Icon size={16} aria-hidden style={{ flexShrink: 0, marginTop: 2, color: alert ? '#b45309' : '#6b7280' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 'var(--workspace-font-control)', color: '#111827', fontWeight: 500 }}>
          {item.title}
          {soon && <span style={{ marginLeft: 'var(--workspace-space-8)', fontSize: 'var(--workspace-font-meta)', color: alert ? '#b45309' : '#6b7280', fontWeight: 600 }}>{soon}</span>}
        </div>
        <div style={{ fontSize: 'var(--workspace-font-meta)', color: item.in_conflict ? '#92400e' : '#4b5563' }}>
          {summary(item)}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 'var(--workspace-space-6)', marginTop: 'var(--workspace-space-4)' }}>
          <button type="button" style={{ ...BUTTON, border: 'none', padding: 0, color: '#2563eb', textDecoration: 'underline' }}
            onClick={() => navigate({ to: '/', search: { project: item.project_uuid } as never })}>
            {item.project_title || 'Project'}
          </button>
          {source && (
            <button type="button" title={source.quote} style={BUTTON}
              aria-label={`Open ${source.document_title}${source.page ? ` at page ${source.page}` : ''}`}
              onClick={() => viewDocument(source.document_uuid, source.document_title, {
                terms: [source.quote.split(/\s+/).slice(0, 8).join(' ')],
                page: source.page,
              })}>
              {source.document_title}{source.page ? ` · p. ${source.page}` : ''}
            </button>
          )}
          <span style={{ flex: 1 }} />
          <button type="button" style={BUTTON} disabled={busy}
            aria-label={`Mark "${item.title}" done for everyone on the project`}
            onClick={() => act('done', () => setObligationDone(item.uuid, true))}>
            <Check size={12} aria-hidden /> Done
          </button>
          <button type="button" style={BUTTON} disabled={busy}
            aria-label={`Hide "${item.title}" from your Home`}
            onClick={() => act('dismissed', () => setObligationDismissed(item.uuid, true))}>
            <EyeOff size={12} aria-hidden /> Dismiss
          </button>
        </div>
      </div>
    </li>
  )
}

export function RAInbox() {
  const [items, setItems] = useState<Obligation[] | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [hidden, setHidden] = useState(false)
  const [showDismissed, setShowDismissed] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (includeDismissed: boolean) => {
    try {
      const data = await getInbox(includeDismissed)
      setLoadError(false)
      setItems(data.items)
      setHidden(data.inbox_hidden)
      setError(null)
    } catch {
      setLoadError(true)
    }
  }, [])

  useEffect(() => { void load(showDismissed) }, [load, showDismissed])

  if (loadError) return <p role="status" className="home-meta">Project obligations could not be loaded. <button type="button" className="home-text-action" onClick={() => void load(showDismissed)}>Retry obligations</button></p>
  if (hidden || items == null) return null
  const visible = showDismissed ? items : items.filter(i => !i.dismissed)
  const dismissedCount = items.filter(i => i.dismissed).length
  if (visible.length === 0 && !showDismissed) return null

  // Done leaves the inbox for everyone; Dismiss only hides it here, so it
  // stays countable under "Show dismissed".
  const changed = (uuid: string, change: 'done' | 'dismissed') => setItems(current =>
    change === 'done'
      ? (current ?? []).filter(i => i.uuid !== uuid)
      : (current ?? []).map(i => (i.uuid === uuid ? { ...i, dismissed: true } : i)))
  const restore = async (uuid: string) => {
    try {
      await setObligationDismissed(uuid, false)
      setItems(current => (current ?? []).map(i => (i.uuid === uuid ? { ...i, dismissed: false } : i)))
    } catch {
      setError('That item could not be restored. Try again.')
    }
  }
  const hideInbox = async () => {
    try {
      await setInboxHidden(true)
      setHidden(true)
    } catch {
      setError('The inbox could not be hidden. Try again.')
    }
  }

  return (
    <section aria-label="RA inbox" style={{
      padding: 'var(--workspace-space-12) var(--workspace-space-8)', borderRadius: 'var(--ui-radius, 12px)',
      backgroundColor: '#fff', border: '1px solid var(--workspace-border)', marginTop: 'var(--workspace-space-12)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', padding: '0 var(--workspace-space-12)' }}>
        <Inbox size={14} aria-hidden style={{ color: '#6b7280' }} />
        <h2 style={{ margin: 0, fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: '#4b5563', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Due and needed
        </h2>
        <span style={{ flex: 1 }} />
        {(dismissedCount > 0 || showDismissed) && (
          <button type="button" style={{ ...BUTTON, border: 'none' }} onClick={() => setShowDismissed(v => !v)}>
            {showDismissed ? 'Hide dismissed' : `Show dismissed (${dismissedCount})`}
          </button>
        )}
        <button type="button" style={{ ...BUTTON, border: 'none' }} onClick={hideInbox}
          aria-label="Hide this inbox from your Home. You can turn it back on in Account settings.">
          Hide inbox
        </button>
      </div>
      {error && <p role="alert" style={{ margin: 'var(--workspace-space-4) var(--workspace-space-12)', fontSize: 'var(--workspace-font-meta)', color: '#b91c1c' }}>{error}</p>}
      <ul style={{ margin: 'var(--workspace-space-4) 0 0', padding: 0 }}>
        {visible.map(item => item.dismissed ? (
          <li key={item.uuid} style={{ listStyle: 'none', display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', padding: 'var(--workspace-space-6) var(--workspace-space-12)', color: '#6b7280', fontSize: 'var(--workspace-font-meta)' }}>
            <span style={{ flex: 1 }}>{item.title} · {item.project_title}</span>
            <button type="button" style={BUTTON} onClick={() => restore(item.uuid)}>Restore</button>
          </li>
        ) : (
          <InboxRow key={item.uuid} item={item} onChanged={changed} onError={setError} />
        ))}
      </ul>
    </section>
  )
}
