import { useCallback, useEffect, useState } from 'react'
import { Download, History, Loader2, X } from 'lucide-react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { getChatActivity, type ChatActivityEntry, type ChatActivityLog } from '../../api/chat'
import type { CardDecision } from '../../types/chat'
import { OUTCOME_TEXT, activityLogToText, formatTime, repeatNote, whatYouDid } from './chatActivityLog'

const PAGE_TOOLS = ['create_html_artifact', 'revise_html_artifact']

/** The chat's "Activity" button: one timeline of what the user approved,
 * how many times, and what each approval did (support ticket: NIFA subaward
 * setup test). Cards still waiting can be approved or cancelled from here,
 * exactly as from the card itself. */
export function ChatActivityPanel({ conversationUuid, refreshKey, busy, onDecide }: {
  conversationUuid: string | null
  /** Changes whenever the transcript or waiting cards change, to reload an open panel. */
  refreshKey: unknown
  busy: boolean
  onDecide: (message: string, pageApproval: string | undefined, decision: CardDecision) => boolean | void
}) {
  const [open, setOpen] = useState(false)
  const [log, setLog] = useState<ChatActivityLog | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    if (!conversationUuid) return
    setLoading(true)
    setError('')
    getChatActivity(conversationUuid)
      .then(setLog)
      .catch(() => setError('Could not load this chat’s activity.'))
      .finally(() => setLoading(false))
  }, [conversationUuid])

  useEffect(() => { if (open && !busy) load() }, [open, busy, load, refreshKey])

  if (!conversationUuid) return null

  const decide = (entry: ChatActivityEntry, approve: boolean) => {
    const page = approve && PAGE_TOOLS.includes(entry.tool) && entry.preview_id ? entry.preview_id : undefined
    const accepted = onDecide(approve ? 'Yes, go ahead' : 'No, cancel that', page,
      approve ? { approve: entry.call_id } : { decline: entry.call_id })
    if (accepted === false) setError('Not sent yet. Wait for the current response to finish, then try again.')
    else setOpen(false)
  }

  const exportLog = () => {
    if (!log) return
    const blob = new Blob([activityLogToText(log)], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `chat-activity-${log.conversation_uuid.slice(0, 8)}.txt`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }

  const waiting = log?.entries.filter(e => e.outcome === 'waiting') ?? []
  const history = log?.entries.filter(e => e.outcome !== 'waiting') ?? []

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="What you approved in this chat, and what happened"
        aria-label="Activity: what you approved in this chat"
        className="chat-composer-tool"
      >
        <History className="h-4 w-4" aria-hidden="true" />
        <span className="chat-composer-tool-label">Activity</span>
      </button>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', zIndex: 1000 }} />
          <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="chat-activity-title"
              onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }}
              style={{
                position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
                background: 'white', borderRadius: 'var(--ui-radius, 12px)', boxShadow: 'var(--workspace-shadow-dialog)',
                width: 640, maxWidth: 'calc(100vw - 32px)', maxHeight: 'calc(100vh - 64px)', zIndex: 1001,
                display: 'flex', flexDirection: 'column', overflow: 'hidden',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: 'var(--workspace-space-16) var(--workspace-space-20)', borderBottom: '1px solid var(--workspace-border)' }}>
                <div>
                  <h3 id="chat-activity-title" style={{ margin: 0, fontSize: 'var(--workspace-font-card-title)', fontWeight: 600 }}>Activity in this chat</h3>
                  <p style={{ margin: 'var(--workspace-space-4) 0 0', fontSize: 'var(--workspace-font-control)', color: '#6b7280' }}>
                    What you approved, and what happened.
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button type="button" onClick={exportLog} disabled={!log}
                    className="flex items-center gap-1 rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-100 disabled:opacity-50">
                    <Download size={13} aria-hidden="true" /> Export log
                  </button>
                  <button type="button" onClick={() => setOpen(false)} aria-label="Close"
                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 'var(--workspace-space-4)', color: '#6b7280', display: 'flex' }}>
                    <X size={18} />
                  </button>
                </div>
              </div>

              <div style={{ padding: 'var(--workspace-space-12) var(--workspace-space-20) var(--workspace-space-20)', overflowY: 'auto' }}>
                {error && <p role="alert" style={{ color: '#b91c1c', fontSize: 'var(--workspace-font-control)' }}>{error}</p>}
                {loading && !log ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#9ca3af', fontSize: 'var(--workspace-font-control)' }}>
                    <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> Loading…
                  </div>
                ) : log && !log.entries.length ? (
                  <p style={{ color: '#6b7280', fontSize: 'var(--workspace-font-control)' }}>
                    Nothing to approve in this chat yet. When the Assistant prepares an action, like moving files, it shows here with what happened.
                  </p>
                ) : log ? (
                  <>
                    {waiting.length > 0 && (
                      <section aria-label="Waiting for you" style={{ marginBottom: 16 }}>
                        <h4 style={sectionHeading}>Waiting for you ({waiting.length})</h4>
                        <ul style={listStyle}>
                          {waiting.map(entry => (
                            <li key={entry.id} style={rowStyle}>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontWeight: 600 }}>{entry.action}</div>
                                {entry.summary && <div style={muted}>{entry.summary}</div>}
                                <div style={muted}>Prepared {formatTime(entry.time)}</div>
                              </div>
                              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                                <button type="button" disabled={busy} onClick={() => decide(entry, true)}
                                  className="rounded bg-gray-900 px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50">{entry.action}</button>
                                <button type="button" disabled={busy} onClick={() => decide(entry, false)}
                                  className="rounded border border-gray-300 px-2.5 py-1 text-xs text-gray-700 disabled:opacity-50">Cancel action</button>
                              </div>
                            </li>
                          ))}
                        </ul>
                      </section>
                    )}
                    {history.length > 0 && (
                      <section aria-label="History">
                        <h4 style={sectionHeading}>History</h4>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--workspace-font-control)' }}>
                          <thead>
                            <tr style={{ textAlign: 'left', color: '#6b7280' }}>
                              <th style={cell}>Time</th><th style={cell}>What you did</th><th style={cell}>What happened</th>
                            </tr>
                          </thead>
                          <tbody>
                            {history.map(entry => {
                              const o = OUTCOME_TEXT[entry.outcome]
                              const note = repeatNote(entry)
                              return (
                                <tr key={entry.id} style={{ borderTop: '1px solid #f3f4f6', verticalAlign: 'top' }}>
                                  <td style={{ ...cell, whiteSpace: 'nowrap', color: '#6b7280' }}>{formatTime(entry.time)}</td>
                                  <td style={cell}>
                                    <div>{whatYouDid(entry)}</div>
                                    {entry.summary && <div style={muted}>{entry.summary}</div>}
                                  </td>
                                  <td style={cell}>
                                    <div><span aria-hidden="true">{o.icon}</span> {o.text}</div>
                                    {entry.detail && <div style={muted}>{entry.detail}</div>}
                                    {note && <div style={{ ...muted, color: '#b45309', fontWeight: 600 }}>{note}</div>}
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </section>
                    )}
                  </>
                ) : null}
              </div>
            </div>
          </FocusTrap>
        </>
      )}
    </>
  )
}

const sectionHeading = { margin: '0 0 8px', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.4, color: '#6b7280' }
const listStyle = { listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column' as const, gap: 8 }
const rowStyle = { display: 'flex', alignItems: 'flex-start', gap: 12, padding: 10, border: '1px solid #fde68a', background: '#fffbeb', borderRadius: 8, fontSize: 'var(--workspace-font-control)' }
const muted = { color: '#6b7280', fontSize: 'var(--workspace-font-meta)', marginTop: 2, overflowWrap: 'anywhere' as const }
const cell = { padding: '8px 8px 8px 0' }
