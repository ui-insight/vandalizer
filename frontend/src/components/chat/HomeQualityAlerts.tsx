import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { getHomeAlertEvidence, reviewHomeAlert, type ActiveAlertItem, type HomeEvaluation } from '../../api/config'

const KINDS: Record<string, string> = { search_set: 'Extraction template', workflow: 'Workflow', knowledge_base: 'Knowledge base' }
export function noticeKey(alert: ActiveAlertItem): string {
  return alert.uuid || `${alert.item_kind}:${alert.item_id || alert.item_name}:${alert.message}`
}
function dateLabel(value?: string | null): string {
  if (!value) return 'Date not recorded'
  // Older API records store UTC without an explicit timezone suffix.
  const timestamp = /T\d{2}:\d{2}.*(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`
  if (Number.isNaN(Date.parse(timestamp))) return 'Date not recorded'
  return new Date(timestamp).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
export function noticeSummary(alert: ActiveAlertItem): string {
  const { previous_score: before, current_score: after } = alert
  if (typeof before === 'number' && typeof after === 'number') {
    return `Evaluation score ${after < before ? 'fell' : 'changed'} from ${Number(before.toFixed(1))} to ${Number(after.toFixed(1))}`
  }
  return alert.message
}
function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object' && !Array.isArray(item)) : []
}
function valueLabel(value: unknown): string {
  return value == null ? 'Not recorded' : typeof value === 'string' ? value : JSON.stringify(value)
}
function Evaluation({ run }: { run: HomeEvaluation }) {
  const cases = records(run.result_snapshot?.test_cases)
  const checks = records(run.result_snapshot?.checks)
  return <article className="home-evaluation">
    <strong>{dateLabel(run.created_at)}</strong>
    <p>{run.source === 'optimizer_apply' ? 'Settings applied — not a new evaluation' : 'Recorded evaluation'} · Score {run.score ?? 'not recorded'} / 100</p>
    {(run.accuracy != null || run.consistency != null) && <p>{run.accuracy != null ? `Field accuracy on tested examples: ${Math.round(run.accuracy * 100)}%. ` : ''}{run.consistency != null ? `Repeat-run consistency: ${Math.round(run.consistency * 100)}%.` : ''}</p>}
    <p>{run.num_test_cases} test cases · {run.num_runs} runs · Model: {run.model || 'not recorded'}</p>
    {run.num_checks > 0 && <p>{run.checks_failed} of {run.num_checks} checks failed</p>}
    {cases.slice(0, 3).map((example, i) => <details key={i}>
      <summary>Test case: {valueLabel(example.label)}</summary>
      <div className="home-evidence-table"><table><caption>Recorded field results</caption><thead><tr><th>Field</th><th>Expected</th><th>Most common result</th></tr></thead>
        <tbody>{records(example.fields).map((field, j) => <tr key={j}><th scope="row">{valueLabel(field.field_name)}</th><td>{valueLabel(field.expected)}</td><td>{valueLabel(field.most_common_value)}</td></tr>)}</tbody>
      </table></div>
    </details>)}
    {checks.length > 0 && <details><summary>Evaluation checks ({checks.length})</summary><ul>{checks.map((check, i) => <li key={i}><strong>{valueLabel(check.name || check.description || check.id)}</strong><p>{valueLabel(check.status ?? check.verdict ?? check.passed)}</p>{!!check.reasoning && <p>{valueLabel(check.reasoning)}</p>}</li>)}</ul></details>}
    <details><summary>Inspect all results and settings</summary>
      <pre>{JSON.stringify({ results: run.result_snapshot, settings: run.model_settings, extraction_config: run.extraction_config, score_breakdown: run.score_breakdown }, null, 2)}</pre>
    </details>
  </article>
}
function Notice({ alert, relatedActivity, onOpenActivity, onOpenTool, onSendMessage, onNoticeChanged, disabled }: {
  alert: ActiveAlertItem
  relatedActivity: { id: string; title: string }[]
  onOpenActivity: (id: string) => void
  onOpenTool?: (alert: ActiveAlertItem) => void
  onSendMessage: (message: string) => void
  disabled?: boolean
  onNoticeChanged?: () => void
}) {
  const [state, setState] = useState(alert.review_state || 'new')
  const [open, setOpen] = useState(false)
  const [runs, setRuns] = useState<HomeEvaluation[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const kind = KINDS[alert.item_kind || ''] || 'Saved tool'
  const load = async () => {
    if (!alert.uuid) return
    setLoading(true); setError(null)
    try { setRuns((await getHomeAlertEvidence(alert.uuid)).runs) }
    catch { setError('Evaluation history could not be loaded. Try again.') }
    finally { setLoading(false) }
  }
  const changeState = async (next: NonNullable<ActiveAlertItem['review_state']>) => {
    if (!alert.uuid) return
    setBusy(true); setError(null)
    try { setState((await reviewHomeAlert(alert.uuid, next)).review_state || next); onNoticeChanged?.() }
    catch { setError('The review status could not be saved. Try again.') }
    finally { setBusy(false) }
  }
  return <li className="home-quality-notice" data-severity={alert.severity}>
    <div className="home-notice-heading">
      <AlertTriangle size={16} aria-hidden="true" />
      <div><strong>{alert.item_name || 'Untitled tool'}</strong><p>{kind} · {alert.severity === 'critical' ? 'Critical warning' : alert.severity === 'warning' ? 'Warning' : 'Information'} · {state === 'in_review' ? 'Under review' : state === 'acknowledged' ? 'Acknowledged' : 'Not reviewed'}</p></div>
    </div>
    <p>{noticeSummary(alert)}</p>
    <p className="home-meta"><time dateTime={alert.created_at || undefined}>{dateLabel(alert.created_at)}</time></p>
    <p className="home-meta">{alert.alert_type === 'stale' ? 'The last evaluation is out of date. Check the tool before relying on new results.' : alert.alert_type === 'config_changed' ? 'The tool changed after evaluation. Review its settings and revalidate before relying on its score.' : 'Review the evaluation before relying on new results. A score change alone does not establish errors in your documents.'}</p>
    <button className="home-text-action" type="button" aria-expanded={open} onClick={() => { setOpen(!open); if (!open && runs === null) void load() }}>
      {open ? 'Hide evaluation details' : 'View evaluation details'}
    </button>
    {open && <div className="home-notice-details">
      <p>Recorded notice: {alert.message}</p>
      <p>{alert.item_kind === 'search_set' ? 'Extraction scores combine field accuracy and consistency, with cross-field checks when configured and an adjustment for sample size.' : alert.item_kind === 'workflow' ? 'Workflow scores summarize the configured evaluation checks and may be adjusted for sample size.' : alert.item_kind === 'knowledge_base' ? 'Knowledge-base scores summarize the recorded retrieval and answer evaluations. Inspect the score breakdown for this run.' : 'The scoring method is not recorded on this notice. Inspect the evaluation details before interpreting it.'}</p>
      <p>Evaluation scores describe the examples tested, not the probability that your next result is correct.</p>
      <p>Project and document impact has not been established for this notice. Inspect relevant results before deciding whether work needs to be repeated.</p>
      <p>History is shown for this tool. This notice has no recorded link to a specific evaluation; later runs are not evidence of what caused it.</p>
      {loading && <p role="status">Loading evaluation history…</p>}
      {runs?.length === 0 && <p>No evaluation history is available for this tool.</p>}
      {!alert.uuid && <p>This older notice has no evidence link. Open the tool or ask the assistant to help locate its evaluation.</p>}
      {runs?.map(run => <Evaluation key={run.uuid} run={run} />)}
      {relatedActivity.length > 0 && <div><p>Recent uses of this tool — not confirmed affected:</p>{relatedActivity.map(item => <button className="home-text-action" type="button" key={item.id} onClick={() => onOpenActivity(item.id)}>{item.title}</button>)}</div>}
      <div className="home-notice-actions">
        {onOpenTool && alert.item_id && <button className="home-text-action" type="button" onClick={() => onOpenTool(alert)}>Open {kind.toLowerCase()}</button>}
        <button className="home-text-action" type="button" disabled={disabled} onClick={() => onSendMessage(`Help me understand the quality notice for ${kind.toLowerCase()} "${alert.item_name}"${alert.item_id ? ` (ID: ${alert.item_id})` : ''}: ${noticeSummary(alert)}. Inspect available evaluation evidence, explain what it measures and what remains unknown. Do not run this tool on documents.`)}>Ask assistant about this warning</button>
        {alert.uuid && <>
          {state !== 'in_review' && <button className="home-text-action" type="button" disabled={busy} onClick={() => void changeState('in_review')}>Mark under review</button>}
          {state !== 'acknowledged' && <button className="home-text-action" type="button" disabled={busy} onClick={() => void changeState('acknowledged')}>Acknowledge notice</button>}
        </>}
      </div>
      <p className="home-meta">Acknowledging records that you have seen the notice and removes it from the active notices. It does not fix the tool or verify its results.</p>
      {error && <div role="alert"><p>{error}</p>{runs === null && alert.uuid && <button type="button" className="home-text-action" disabled={loading} onClick={() => void load()}>Retry evaluation history</button>}</div>}
    </div>}
  </li>
}
export function HomeQualityAlerts({ alerts, recentActivity, ...actions }: {
  alerts: ActiveAlertItem[]
  recentActivity: { id: string; title: string; item_id?: string | null; item_kind?: string | null }[]
  onOpenActivity: (id: string) => void
  onOpenTool?: (alert: ActiveAlertItem) => void
  onSendMessage: (message: string) => void
  disabled?: boolean
  onNoticeChanged?: () => void
}) {
  const seen = new Set<string>()
  const notices = alerts.filter(a => { const key = noticeKey(a); if (seen.has(key)) return false; seen.add(key); return true })
  if (!notices.length) return null
  return <section className="home-quality" aria-label="Tool quality notices">
    <h3>Tool quality notices <span>{notices.length}</span></h3>
    <p className="home-meta">These notices concern saved tools. They are separate from your project obligations.</p>
    <ul>{notices.map(alert => <Notice key={noticeKey(alert)} alert={alert} relatedActivity={recentActivity.filter(a => !!alert.item_id && a.item_id === alert.item_id && a.item_kind === alert.item_kind)} {...actions} />)}</ul>
  </section>
}
