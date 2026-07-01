import { useEffect, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { X, Loader2, ArrowLeftRight } from 'lucide-react'
import {
  getKBOptimization,
  type KBOptimizationRun,
  type PerQueryResult,
} from '../../api/knowledge'

interface Props {
  open: boolean
  kbUuid: string
  /** "current" side of the diff — typically the run the user is viewing. */
  currentRunUuid: string | null
  /** "other" side — the past run picked from the history panel. */
  otherRunUuid: string | null
  onClose: () => void
}

/**
 * Side-by-side diff between two optimization runs:
 *  - eval-set drift (which queries differ between the snapshots),
 *  - config diff (winning config knob changes),
 *  - judge metadata (model, prompt version, seed),
 *  - per-query score deltas for queries present in both runs' winners.
 *
 * Without this, the only way to compare runs is mental-arithmetic over a
 * history list — exactly the gap that drove the audit's #10.
 */
export function CompareRunsView({
  open, kbUuid, currentRunUuid, otherRunUuid, onClose,
}: Props) {
  const [current, setCurrent] = useState<KBOptimizationRun | null>(null)
  const [other, setOther] = useState<KBOptimizationRun | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !currentRunUuid || !otherRunUuid) return
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      getKBOptimization(kbUuid, currentRunUuid),
      getKBOptimization(kbUuid, otherRunUuid),
    ]).then(([a, b]) => {
      if (cancelled) return
      setCurrent(a)
      setOther(b)
    }).catch(e => {
      if (!cancelled) setError((e as Error).message)
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [open, kbUuid, currentRunUuid, otherRunUuid])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 70,
        display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
        backgroundColor: 'rgba(0,0,0,0.55)', padding: 24, overflowY: 'auto',
      }}
      onClick={onClose}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Compare optimization runs"
        onClick={e => e.stopPropagation()}
        style={{
          width: 'min(1100px, 100%)',
          backgroundColor: '#161616', border: '1px solid #2e2e2e',
          borderRadius: 10, padding: 20,
          display: 'flex', flexDirection: 'column', gap: 14,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <ArrowLeftRight size={16} style={{ color: '#a78bfa' }} aria-hidden="true" />
          <h3 style={{ margin: 0, fontSize: 14, color: '#fff' }}>
            Compare optimization runs
          </h3>
          <button
            type="button"
            onClick={onClose}
            style={{
              marginLeft: 'auto', background: 'transparent', border: 'none',
              color: '#888', cursor: 'pointer', padding: 4, fontFamily: 'inherit',
            }}
            aria-label="Close"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {loading ? (
          <div role="status" aria-live="polite" style={{ textAlign: 'center', padding: 36, color: '#888' }}>
            <Loader2 size={20} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
            <span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Loading runs…</span>
          </div>
        ) : error ? (
          <div role="alert" style={{ color: '#fca5a5', fontSize: 12 }}>{error}</div>
        ) : current && other ? (
          <DiffBody left={other} right={current} />
        ) : null}
      </div>
      </FocusTrap>
    </div>
  )
}

function DiffBody({ left, right }: { left: KBOptimizationRun; right: KBOptimizationRun }) {
  const leftLabel = formatRunLabel(left)
  const rightLabel = formatRunLabel(right)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12,
      }}>
        <RunHeader label="Earlier run" run={left} subtitle={leftLabel} />
        <RunHeader label="This run" run={right} subtitle={rightLabel} />
      </div>

      <Section title="Eval set drift">
        <EvalSetDrift left={left} right={right} />
      </Section>

      <Section title="Judge & reproducibility">
        <JudgeDiff left={left} right={right} />
      </Section>

      <Section title="Winning config diff">
        <ConfigDiff left={left.best_config || {}} right={right.best_config || {}} />
      </Section>

      <Section title="Per-query deltas (common queries)">
        <PerQueryDiff left={left} right={right} />
      </Section>
    </div>
  )
}

function RunHeader({ label, run, subtitle }: { label: string; run: KBOptimizationRun; subtitle: string }) {
  const score = run.optimized_score
  const baseline = run.baseline_default_score
  const lift = score != null && baseline != null ? (score - baseline) * 100 : null
  return (
    <div style={{
      padding: 12, backgroundColor: '#1a1a1a',
      border: '1px solid #2e2e2e', borderRadius: 6,
    }}>
      <div style={{ fontSize: 9, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 11, color: '#aaa', marginTop: 2 }}>{subtitle}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
        <span style={{ fontSize: 22, fontWeight: 700, color: scoreColor((score ?? 0) * 100) }}>
          {score != null ? `${(score * 100).toFixed(0)}%` : '—'}
        </span>
        {lift != null && (
          <span style={{ fontSize: 11, color: lift > 0 ? '#22c55e' : lift < 0 ? '#ef4444' : '#888' }}>
            {lift > 0 ? '+' : ''}{lift.toFixed(0)}pts vs default
          </span>
        )}
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{
        fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6,
      }}>{title}</div>
      {children}
    </div>
  )
}

function EvalSetDrift({ left, right }: { left: KBOptimizationRun; right: KBOptimizationRun }) {
  const ls = left.test_query_snapshot
  const rs = right.test_query_snapshot
  if (!ls || !rs) {
    return <Note>One or both runs predate eval-set snapshots — drift cannot be computed.</Note>
  }
  const leftIds = new Set(ls.query_uuids)
  const rightIds = new Set(rs.query_uuids)
  const added = rs.query_uuids.filter(id => !leftIds.has(id))
  const removed = ls.query_uuids.filter(id => !rightIds.has(id))
  // Hashes for queries present in both runs — if hashes differ, the
  // expected-answer text was revised, which silently changes the score.
  const expectedAnswerRevised: string[] = []
  for (const id of rs.query_uuids) {
    if (!leftIds.has(id)) continue
    const lh = ls.expected_answer_hashes[id]
    const rh = rs.expected_answer_hashes[id]
    if (lh && rh && lh !== rh) expectedAnswerRevised.push(id)
  }
  const drifted = added.length > 0 || removed.length > 0 || expectedAnswerRevised.length > 0
  return (
    <div style={{
      padding: 10, backgroundColor: drifted ? 'rgba(245, 158, 11, 0.06)' : '#1a1a1a',
      border: `1px solid ${drifted ? 'rgba(245, 158, 11, 0.3)' : '#2e2e2e'}`,
      borderRadius: 6, fontSize: 11, color: '#aaa', lineHeight: 1.6,
    }}>
      <div>
        <strong>Common:</strong> {ls.query_uuids.length - removed.length} ·{' '}
        <strong>Added:</strong> {added.length} ·{' '}
        <strong>Removed:</strong> {removed.length} ·{' '}
        <strong>Expected-answer revised:</strong> {expectedAnswerRevised.length}
      </div>
      {drifted && (
        <div style={{ marginTop: 6, color: '#fbbf24' }}>
          ⚠ Eval set changed between runs — the score comparison isn't strictly apples-to-apples.
        </div>
      )}
    </div>
  )
}

function JudgeDiff({ left, right }: { left: KBOptimizationRun; right: KBOptimizationRun }) {
  const rows = [
    ['Judge model', left.judge_model || '—', right.judge_model || '—'],
    ['Judge prompt', left.judge_prompt_version || '—', right.judge_prompt_version || '—'],
    ['Judge temperature', fmtNum(left.judge_temperature), fmtNum(right.judge_temperature)],
    ['RNG seed', left.rng_seed != null ? String(left.rng_seed) : '—', right.rng_seed != null ? String(right.rng_seed) : '—'],
    ['Judge variance', fmtPct(left.judge_variance), fmtPct(right.judge_variance)],
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {rows.map(([label, l, r]) => (
        <DiffRow key={label} label={label} left={l} right={r} />
      ))}
    </div>
  )
}

function ConfigDiff({ left, right }: { left: Record<string, unknown>; right: Record<string, unknown> }) {
  const keys = new Set([...Object.keys(left), ...Object.keys(right)])
  if (keys.size === 0) {
    return <Note>No best_config recorded on at least one run.</Note>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {Array.from(keys).sort().map(k => (
        <DiffRow
          key={k}
          label={k}
          left={String(left[k] ?? '—')}
          right={String(right[k] ?? '—')}
        />
      ))}
    </div>
  )
}

function PerQueryDiff({ left, right }: { left: KBOptimizationRun; right: KBOptimizationRun }) {
  const winnerLeft = pickWinner(left)
  const winnerRight = pickWinner(right)
  const lq = winnerLeft?.per_query_results || []
  const rq = winnerRight?.per_query_results || []
  if (lq.length === 0 || rq.length === 0) {
    return <Note>At least one run lacks per-query data (older run pre-dating this feature).</Note>
  }
  const byUuidLeft = new Map(lq.map(r => [r.query_uuid, r]))
  const rows: { q: PerQueryResult; left: PerQueryResult }[] = []
  for (const r of rq) {
    const l = byUuidLeft.get(r.query_uuid)
    if (l) rows.push({ q: r, left: l })
  }
  if (rows.length === 0) {
    return <Note>No queries are shared between the two runs' winners.</Note>
  }
  rows.sort((a, b) => (b.q.score - b.left.score) - (a.q.score - a.left.score))
  // Show top-5 biggest swings up and bottom-5 biggest swings down for brevity.
  const topGains = rows.slice(0, 5).filter(r => r.q.score - r.left.score > 0.001)
  const topRegressions = rows.slice(-5).reverse().filter(r => r.q.score - r.left.score < -0.001)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {topGains.length > 0 && (
        <DeltaGroup label="Biggest gains" tone="good" rows={topGains} />
      )}
      {topRegressions.length > 0 && (
        <DeltaGroup label="Biggest regressions" tone="bad" rows={topRegressions} />
      )}
      {topGains.length === 0 && topRegressions.length === 0 && (
        <Note>No meaningful per-query swings between the two runs.</Note>
      )}
    </div>
  )
}

function DeltaGroup({
  label, rows, tone,
}: {
  label: string
  tone: 'good' | 'bad'
  rows: { q: PerQueryResult; left: PerQueryResult }[]
}) {
  const fg = tone === 'good' ? '#86efac' : '#fca5a5'
  return (
    <div>
      <div style={{ fontSize: 10, fontWeight: 600, color: fg, marginBottom: 4 }}>{label}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {rows.map(({ q, left }) => {
          const delta = (q.score - left.score) * 100
          return (
            <div
              key={q.query_uuid}
              title={q.query}
              style={{
                display: 'grid', gridTemplateColumns: '1fr 60px 60px 50px',
                gap: 6, padding: '4px 8px',
                fontSize: 11, color: '#ddd',
                backgroundColor: '#1a1a1a', border: '1px solid #262626',
                borderRadius: 4,
              }}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {q.query}
              </span>
              <span style={{ textAlign: 'right', color: scoreColor(left.score * 100) }}>
                {(left.score * 100).toFixed(0)}%
              </span>
              <span style={{ textAlign: 'right', color: scoreColor(q.score * 100), fontWeight: 600 }}>
                {(q.score * 100).toFixed(0)}%
              </span>
              <span style={{ textAlign: 'right', color: fg, fontWeight: 600 }}>
                {delta > 0 ? '+' : ''}{delta.toFixed(0)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function DiffRow({ label, left, right }: { label: string; left: string; right: string }) {
  const changed = left !== right
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '160px 1fr 1fr',
      gap: 8, padding: '4px 8px',
      fontSize: 11, color: '#ddd',
      backgroundColor: changed ? 'rgba(245, 158, 11, 0.06)' : '#1a1a1a',
      border: `1px solid ${changed ? 'rgba(245, 158, 11, 0.25)' : '#262626'}`,
      borderRadius: 4,
    }}>
      <span style={{ color: '#888' }}>{label}</span>
      <span style={{ color: changed ? '#fbbf24' : '#aaa', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={left}>{left}</span>
      <span style={{ color: changed ? '#fbbf24' : '#aaa', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={right}>{right}</span>
    </div>
  )
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      padding: 8, fontSize: 11, color: '#888',
      backgroundColor: '#1a1a1a', border: '1px solid #262626',
      borderRadius: 4,
    }}>{children}</div>
  )
}

function pickWinner(run: KBOptimizationRun) {
  if (!run.trials || run.trials.length === 0) return undefined
  if (run.best_config) {
    const exact = run.trials.find(t =>
      t.config && JSON.stringify(t.config) === JSON.stringify(run.best_config),
    )
    if (exact) return exact
  }
  return [...run.trials].sort((a, b) => b.score - a.score)[0]
}

function formatRunLabel(run: KBOptimizationRun): string {
  const parts: string[] = []
  if (run.started_at) parts.push(new Date(run.started_at).toLocaleString())
  if (run.judge_model) parts.push(run.judge_model)
  const n = run.test_query_snapshot?.total ?? run.trials?.[0]?.num_queries_judged
  if (n != null) parts.push(`n=${n}`)
  return parts.join(' · ')
}

function fmtNum(n: number | null | undefined): string {
  if (n == null) return '—'
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

function fmtPct(p: number | null | undefined): string {
  if (p == null) return '—'
  return `${(p * 100).toFixed(1)}%`
}

function scoreColor(pct: number) {
  if (pct >= 70) return '#22c55e'
  if (pct >= 40) return '#f59e0b'
  return '#ef4444'
}
