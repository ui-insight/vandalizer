import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { AlertTriangle, ChevronDown, ChevronRight, FileText, RefreshCw, Share2 } from 'lucide-react'
import { buildAwardSnapshot, getAwardSnapshot, shareAwardSnapshot } from '../../api/awardSnapshot'
import type { AwardSnapshot, SnapshotDeadline, SnapshotFact } from '../../api/awardSnapshot'
import { quoteSearchTerms } from '../../api/obligations'
import { useWorkspace } from '../../contexts/WorkspaceContext'

// The award snapshot (support ticket): where a project's award stands, from the
// project's own data. Facts come from its documents with their pages; the
// deadlines, status and activity are read live, so marking a deadline Done
// shows here on the next refresh without rebuilding anything.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function day(iso: string | null | undefined): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return `${MONTHS[m - 1]} ${d}, ${y}`
}

const UNCONFIRMED: Record<string, string> = {
  unassessed: 'Passage found, value not checked',
  quote_unsupported: 'Not confirmed by the passage',
  unverified: 'Source not found',
}

function openKey(uuid: string) { return `award-snapshot:open:${uuid}` }
function readOpen(uuid: string): boolean {
  try { return localStorage.getItem(openKey(uuid)) === '1' } catch { return false }
}
function writeOpen(uuid: string, open: boolean) {
  try { localStorage.setItem(openKey(uuid), open ? '1' : '0') } catch { /* a convenience only */ }
}

function fact(snapshot: AwardSnapshot, label: string): SnapshotFact | undefined {
  return snapshot.facts.find(f => f.label === label)
}

/** The one-line summary shown while the panel is closed. */
export function snapshotSummary(snapshot: AwardSnapshot): string {
  const parts: string[] = []
  const total = fact(snapshot, 'Total amount')
  if (total) parts.push(total.value)
  const start = fact(snapshot, 'Period start'), end = fact(snapshot, 'Period end')
  if (start && end) parts.push(`${start.value} – ${end.value}`)
  const overdue = snapshot.deadlines.overdue.length
  if (overdue) parts.push(`${overdue} overdue`)
  const next = snapshot.deadlines.upcoming[0]
  if (next) parts.push(`next: ${next.title}, ${day(next.due_at)}`)
  if (!parts.length) parts.push(snapshot.status === 'not_built' ? 'Not built yet' : 'No facts or deadlines yet')
  return parts.join(' · ')
}

function SourceButton({ item }: { item: { document_uuid: string | null; document_title: string | null; page: number | null; page_approximate?: boolean; quote: string | null } }) {
  const { viewDocument } = useWorkspace()
  if (!item.document_uuid || !item.document_title) return null
  const where = `${item.document_title}${item.page ? `, p. ${item.page_approximate ? '~' : ''}${item.page}` : ''}`
  return <button type="button" className="award-snapshot__source" title={item.quote ?? undefined}
    aria-label={`Open ${where}`}
    onClick={() => viewDocument(item.document_uuid as string, item.document_title as string, {
      terms: item.quote ? [quoteSearchTerms(item.quote)] : [], page: item.page,
    })}>
    <FileText size={11} aria-hidden /> {where}
  </button>
}

function FactRow({ f }: { f: SnapshotFact }) {
  const note = UNCONFIRMED[f.support]
  return <div className="award-snapshot__fact">
    <dt>{f.label}</dt>
    <dd>
      <span>{f.value}</span>
      {note && <span className="award-snapshot__unconfirmed"><AlertTriangle size={11} aria-hidden /> {note}</span>}
      <SourceButton item={f} />
    </dd>
  </div>
}

function DeadlineList({ label, items, empty, kind }: { label: string; items: SnapshotDeadline[]; empty: string; kind: 'overdue' | 'upcoming' | 'done' }) {
  const navigate = useNavigate()
  return <div role="group" aria-label={label} className={`award-snapshot__deadlines award-snapshot__deadlines--${kind}`}>
    <h4>{label} <span>({items.length})</span></h4>
    {items.length === 0 ? <p>{empty}</p> : <ul>{items.map(d => {
      const days = d.days_until
      const when = kind === 'overdue' && days != null ? `${-days} day${days === -1 ? '' : 's'} past`
        : kind === 'upcoming' && days != null ? (days === 0 ? 'today' : `in ${days} day${days === 1 ? '' : 's'}`) : ''
      const source = d.sources[0]
      return <li key={d.uuid}>
        <button type="button" className="award-snapshot__deadline" onClick={() => navigate({ to: '/', search: { deadline: d.uuid } as never })}
          aria-label={`${d.title}, ${day(d.due_at)}. Open it in the RA inbox`}>
          <strong>{d.title}</strong> · {day(d.due_at)}{d.due_text ? `, ${d.due_text}` : ''}{when && <em> · {when}</em>}
        </button>
        {source && <SourceButton item={{ ...source, page_approximate: false }} />}
        {d.entered_by_hand && <span className="award-snapshot__unconfirmed">
          <AlertTriangle size={11} aria-hidden /> Added by hand · not checked against a document{d.source_note ? ` · Source: ${d.source_note}` : ''}
        </span>}
      </li>
    })}</ul>}
  </div>
}

/** The award snapshot panel at the top of the active project. */
export function AwardSnapshotPanel({ railWidth }: { railWidth?: number }) {
  const { activeProjectUuid, railDocked } = useWorkspace()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [openFor, setOpenFor] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState<'build' | 'share' | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const uuid = activeProjectUuid ?? ''
  const query = useQuery({
    queryKey: ['award-snapshot', uuid],
    enabled: !!uuid,
    queryFn: () => getAwardSnapshot(uuid),
    // Deadlines and status are live: refresh when the user comes back, every
    // minute, and every few seconds while the facts are being read.
    refetchOnWindowFocus: true,
    refetchInterval: (q) => (q.state.data?.status === 'building' ? 5_000 : 60_000),
    retry: false,
  })
  if (!uuid) return null
  const open = openFor[uuid] ?? readOpen(uuid)
  const toggle = () => { writeOpen(uuid, !open); setOpenFor(s => ({ ...s, [uuid]: !open })) }
  const snapshot = query.data
  const margin = railWidth ?? (railDocked ? 64 : 320)

  const build = async () => {
    setBusy('build'); setMessage(null)
    try {
      queryClient.setQueryData(['award-snapshot', uuid], await buildAwardSnapshot(uuid))
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'The snapshot could not be built.')
    } finally { setBusy(null) }
  }
  const share = async () => {
    setBusy('share'); setMessage(null)
    try {
      const page = await shareAwardSnapshot(uuid)
      void queryClient.invalidateQueries({ queryKey: ['award-snapshot', uuid] })
      navigate({ to: '/pages/$uuid', params: { uuid: page.uuid } })
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'The page could not be saved.')
    } finally { setBusy(null) }
  }

  return <section className="award-snapshot" aria-label="Award snapshot" style={{ marginRight: margin }}>
    <div className="award-snapshot__bar">
      <button type="button" className="award-snapshot__toggle" aria-expanded={open} aria-controls="award-snapshot-detail" onClick={toggle}>
        {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
        <span className="award-snapshot__title">Award snapshot</span>
        {snapshot && <span className="award-snapshot__summary">{snapshotSummary(snapshot)}</span>}
        {query.isPending && <span role="status" className="award-snapshot__summary">Loading…</span>}
      </button>
      {query.isError && <span role="alert" className="award-snapshot__summary">Snapshot unavailable. <button type="button" onClick={() => void query.refetch()}>Retry</button></span>}
      {snapshot?.can_manage && <span className="award-snapshot__actions">
        {snapshot.status === 'building'
          ? <span role="status"><RefreshCw size={12} aria-hidden className="animate-spin" /> Reading the documents…</span>
          : <button type="button" disabled={busy !== null || snapshot.document_count === 0} onClick={() => void build()}
              title={snapshot.document_count === 0 ? 'Add the award documents to this project first' : 'Read the key facts and budget from the project’s documents'}>
              <RefreshCw size={12} aria-hidden /> {snapshot.status === 'not_built' ? 'Build snapshot' : 'Refresh'}
            </button>}
        <button type="button" disabled={busy !== null} onClick={() => void share()}
          title={snapshot.page_uuid ? 'Save the current snapshot as a new revision of its Page' : 'Save the snapshot as a private Page you can share'}>
          <Share2 size={12} aria-hidden /> {snapshot.page_uuid ? 'Update Page' : 'Share as Page'}
        </button>
      </span>}
    </div>
    {message && <p role="alert" className="award-snapshot__message">{message}</p>}
    {open && snapshot && <div id="award-snapshot-detail" className="award-snapshot__detail">
      {snapshot.out_of_date && <p role="status" className="award-snapshot__note">The project’s documents changed after these facts were read.{snapshot.can_manage ? ' Refresh to read them again.' : ''}</p>}
      {snapshot.status === 'error' && <p role="alert" className="award-snapshot__note">{snapshot.error}</p>}
      <div className="award-snapshot__columns">
        <div>
          <h3>Key facts</h3>
          {snapshot.facts.length ? <dl>
            {snapshot.facts.map(f => <FactRow key={f.key} f={f} />)}
            {/* Support ticket: a fact the award doesn't state is said to be missing, never filled from a summary. */}
            {(snapshot.not_found ?? []).map(label => <div key={label} className="award-snapshot__fact award-snapshot__fact--missing">
              <dt>{label}</dt><dd><span className="award-snapshot__meta">Not stated in the documents read</span></dd>
            </div>)}
          </dl>
            : <p>{snapshot.status === 'not_built'
              ? (snapshot.can_manage ? 'Build the snapshot to read the sponsor, award numbers, PI(s), period, total and F&A rate from this project’s documents.' : 'Not built yet. A project owner or editor can build it.')
              : snapshot.status === 'building' ? 'Reading the documents…' : 'None of the key facts were found in this project’s documents.'}</p>}
          {snapshot.budget_years.length > 0 && <><h3>Budget by year</h3><dl>{snapshot.budget_years.map(f => <FactRow key={f.key} f={f} />)}</dl></>}
          {snapshot.built_at && <p className="award-snapshot__meta">Read from {snapshot.documents_read.map(d => d.title).join(', ') || 'the project’s documents'} on {day(snapshot.built_at)}.</p>}
          {snapshot.built_at && (snapshot.documents_skipped?.length ?? 0) > 0 && <p className="award-snapshot__meta">
            Not used as a source: {snapshot.documents_skipped!.map(d => d.title).join(', ')}. Files Vandalizer created aren’t read when the original documents are in the project.
          </p>}
          {snapshot.built_at && snapshot.documents_read.length > 0 && snapshot.documents_read.every(d => d.generated) && <p role="status" className="award-snapshot__note">
            These facts come from a file Vandalizer created, not an original award document. Add the award agreement to this project and Refresh to read it from the source.
          </p>}
        </div>
        <div>
          <h3>Deadlines <span className="award-snapshot__meta">from the RA inbox</span></h3>
          <DeadlineList label="Overdue" kind="overdue" items={snapshot.deadlines.overdue} empty="Nothing overdue." />
          <DeadlineList label="Upcoming" kind="upcoming" items={snapshot.deadlines.upcoming} empty="No upcoming deadlines in the inbox." />
          <DeadlineList label="Done" kind="done" items={snapshot.deadlines.done} empty="None marked done yet." />
          {snapshot.deadlines.needed.length > 0 && <p className="award-snapshot__meta">Also still needed: {snapshot.deadlines.needed.map(n => n.title).join('; ')}</p>}
        </div>
        <div>
          <h3>Status and activity</h3>
          <dl>
            <div className="award-snapshot__fact"><dt>Status</dt><dd>{snapshot.project.state.replaceAll('_', ' ')}</dd></div>
            <div className="award-snapshot__fact"><dt>Last run</dt><dd>{snapshot.last_run ? `${snapshot.last_run.title ?? snapshot.last_run.type.replaceAll('_', ' ')} · ${snapshot.last_run.status} · ${day(snapshot.last_run.at)}` : 'No runs recorded in this project.'}</dd></div>
            <div className="award-snapshot__fact"><dt>Saved pages</dt><dd>{snapshot.pages.length ? <ul>{snapshot.pages.map(p => <li key={p.uuid}><button type="button" className="award-snapshot__deadline" onClick={() => navigate({ to: '/pages/$uuid', params: { uuid: p.uuid } })}>{p.title}</button></li>)}</ul> : 'None yet.'}</dd></div>
          </dl>
        </div>
      </div>
    </div>}
  </section>
}
