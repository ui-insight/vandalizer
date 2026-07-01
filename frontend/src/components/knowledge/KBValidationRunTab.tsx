import { useState } from 'react'
import { Play, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import {
  type KBValidationMode,
  type KBValidationResult,
  type KBValidationDetail,
} from '../../api/knowledge'

interface Props {
  kbReady: boolean
  canManage: boolean
  numQueries: number
  latestRun: KBValidationResult | null
  // Run lifecycle is owned by the parent KBValidationPanel so an in-flight run
  // survives switching away from and back to this tab.
  running: boolean
  error: string | null
  onRun: (mode: KBValidationMode) => void
}

export function KBValidationRunTab({ kbReady, canManage, numQueries, latestRun, running, error, onRun }: Props) {
  const [mode, setMode] = useState<KBValidationMode>('judge+baseline')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const handleRun = () => onRun(mode)

  const toggle = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  const disabled = !kbReady || !canManage || running

  return (
    <div>
      {/* Run controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={handleRun}
          disabled={disabled}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            color: disabled ? '#555' : '#fff',
            backgroundColor: disabled ? '#222' : '#2563eb',
            border: '1px solid ' + (disabled ? '#333' : '#3b82f6'),
            borderRadius: 6, cursor: disabled ? 'not-allowed' : 'pointer',
          }}
        >
          {running ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" /> : <Play size={13} aria-hidden="true" />}
          {running ? 'Running…' : 'Run Validation'}
        </button>
        <label style={{ fontSize: 11, color: '#aaa', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          Mode:
          <select
            value={mode}
            onChange={e => setMode(e.target.value as KBValidationMode)}
            style={{
              background: '#1a1a1a', color: '#e5e5e5', border: '1px solid #333',
              borderRadius: 4, padding: '3px 6px', fontSize: 11, fontFamily: 'inherit',
            }}
          >
            <option value="judge+baseline">Score vs. no-KB (recommended)</option>
            <option value="judge">Score only</option>
          </select>
        </label>
        <span style={{ fontSize: 11, color: '#666' }}>
          {numQueries} {numQueries === 1 ? 'query' : 'queries'} configured
        </span>
      </div>

      {error && (
        <div role="alert" style={{ fontSize: 12, color: '#ef4444', marginBottom: 10 }}>{error}</div>
      )}

      {running && !latestRun ? (
        <div role="status" aria-live="polite" style={{ fontSize: 12, color: '#888', padding: '20px 0', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
            Validation running…
          </span>
          <span style={{ fontSize: 11, color: '#666' }}>
            Large evaluation sets can take a few minutes. You can switch tabs — results appear here and in <b>History</b> when finished.
          </span>
        </div>
      ) : !latestRun ? (
        <div role="status" style={{ fontSize: 12, color: '#888', padding: '20px 0', textAlign: 'center' }}>
          No validation run yet. Click <b>Run Validation</b> to evaluate this KB.
        </div>
      ) : (
        <div>
          {/* Certified quality headline — same score as the KB quality tile */}
          <CertifiedQualityCard run={latestRun} />

          {/* Lift card (if baseline available) */}
          <LiftCard run={latestRun} />

          {/* Discrimination summary chips */}
          {latestRun.retrieval_precision.discrimination_summary && (
            <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
              {(['useful', 'redundant', 'failing', 'other'] as const).map(k => {
                const n = latestRun.retrieval_precision.discrimination_summary?.[k] ?? 0
                if (n === 0) return null
                return (
                  <span key={k} style={{
                    fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 8,
                    color: discColor(k), backgroundColor: `${discColor(k)}1a`,
                    border: `1px solid ${discColor(k)}55`,
                  }}>
                    {n} {k}
                  </span>
                )
              })}
            </div>
          )}

          {/* Per-query details */}
          <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {latestRun.retrieval_precision.details.map((d, i) => (
              <DetailRow
                key={d.query_uuid || i}
                detail={d}
                hasBaseline={latestRun.mode === 'judge+baseline'}
                expanded={expanded.has(d.query_uuid || String(i))}
                onToggle={() => toggle(d.query_uuid || String(i))}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function CertifiedQualityCard({ run }: { run: KBValidationResult }) {
  if (run.score == null) return null
  const tierColors: Record<string, { border: string; text: string }> = {
    excellent: { border: '#22c55e55', text: '#22c55e' },
    good: { border: '#3b82f655', text: '#60a5fa' },
    fair: { border: '#f59e0b55', text: '#fbbf24' },
  }
  const tier = run.quality_tier || null
  const c = (tier && tierColors[tier]) || { border: '#2e3a52', text: '#aaa' }
  const tierLabel = tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : 'Unrated'
  const bd = run.score_breakdown
  const penalized = !!bd && bd.sample_size_penalty > 0
  const needed = bd?.test_cases_needed ?? 0
  return (
    <div style={{
      padding: 12, marginBottom: 10, backgroundColor: '#1a1f2e',
      border: `1px solid ${c.border}`, borderRadius: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>Quality</span>
        <span style={{ fontSize: 22, fontWeight: 700, color: c.text }}>
          {tierLabel} — {Math.round(run.score)}%
        </span>
      </div>
      {penalized && bd && (
        <div style={{ fontSize: 11, color: '#fbbf24', lineHeight: 1.5, marginTop: 4 }}>
          Discounted from a raw {Math.round(bd.raw_score)}% by a sample-size confidence penalty
          ({`-${Math.round(bd.sample_size_penalty)} pts`}).{needed > 0
            ? ` Add ${needed} more test quer${needed > 1 ? 'ies' : 'y'} to certify the full ${Math.round(bd.raw_score)}%.`
            : ''}
        </div>
      )}
    </div>
  )
}

function LiftCard({ run }: { run: KBValidationResult }) {
  const j = run.retrieval_precision.avg_judge_score
  const b = run.retrieval_precision.avg_baseline_score
  const lift = run.retrieval_precision.avg_lift
  if (j == null) return null

  return (
    <div style={{
      padding: 12, backgroundColor: '#1a1f2e',
      border: '1px solid #2e3a52', borderRadius: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
        {b != null && (
          <Stat label="Without KB" value={b * 100} color="#888" />
        )}
        <Stat label="With KB" value={j * 100} color="#22c55e" />
        {lift != null && (
          <Stat label="Lift" value={lift * 100} color={lift > 0 ? '#22c55e' : '#ef4444'} sign />
        )}
        {b != null && (
          <div style={{ flex: 1, minWidth: 200 }}>
            <BarComparison baseline={b} withKb={j} />
          </div>
        )}
      </div>
      {run.retrieval_precision.judge_variance != null && (
        <div style={{ fontSize: 10, color: '#666', marginTop: 6 }}>
          Judge variance: ±{(run.retrieval_precision.judge_variance * 100).toFixed(1)} pts (sampled on first run)
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color, sign = false }: { label: string; value: number; color: string; sign?: boolean }) {
  const display = sign ? `${value >= 0 ? '+' : ''}${value.toFixed(0)}pts` : `${value.toFixed(0)}%`
  return (
    <div>
      <div style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{display}</div>
    </div>
  )
}

function BarComparison({ baseline, withKb }: { baseline: number; withKb: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <BarRow label="No KB" value={baseline} color="#888" />
      <BarRow label="With KB" value={withKb} color="#22c55e" />
    </div>
  )
}

function BarRow({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, color: '#aaa' }}>
      <div style={{ width: 50 }}>{label}</div>
      <div style={{ flex: 1, height: 6, backgroundColor: '#2a2a2a', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', backgroundColor: color }} />
      </div>
      <div style={{ width: 36, textAlign: 'right' }}>{pct.toFixed(0)}%</div>
    </div>
  )
}

function DetailRow({
  detail, hasBaseline, expanded, onToggle,
}: { detail: KBValidationDetail; hasBaseline: boolean; expanded: boolean; onToggle: () => void }) {
  const j = detail.judge
  const b = detail.baseline_judge
  return (
    <div style={{
      backgroundColor: '#222', border: '1px solid #2e2e2e', borderRadius: 6, overflow: 'hidden',
    }}>
      <button
        type="button"
        aria-expanded={expanded}
        onClick={onToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, width: '100%',
          padding: '8px 10px', background: 'transparent', border: 'none',
          cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
        }}
      >
        {expanded ? <ChevronDown size={12} style={{ color: '#888' }} aria-hidden="true" /> : <ChevronRight size={12} style={{ color: '#888' }} aria-hidden="true" />}
        <VerdictDot verdict={j?.verdict ?? null} />
        <div style={{ flex: 1, minWidth: 0, fontSize: 12, color: '#e5e5e5', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {detail.query}
        </div>
        {detail.discrimination && detail.discrimination !== 'other' && (
          <span style={{
            fontSize: 9, fontWeight: 600, padding: '1px 6px', borderRadius: 6,
            color: discColor(detail.discrimination),
            backgroundColor: `${discColor(detail.discrimination)}1a`,
          }}>
            {detail.discrimination}
          </span>
        )}
        {j && (
          <span style={{ fontSize: 11, color: '#aaa', minWidth: 40, textAlign: 'right' }}>
            {(j.score * 100).toFixed(0)}%
          </span>
        )}
        {hasBaseline && b && (
          <span style={{ fontSize: 11, color: '#666', minWidth: 70, textAlign: 'right' }}>
            (no-KB: {(b.score * 100).toFixed(0)}%)
          </span>
        )}
      </button>
      {expanded && (
        <div style={{ padding: '8px 12px 12px 32px', borderTop: '1px solid #2e2e2e', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {detail.actual_answer && (
            <Block label="With-KB answer" body={detail.actual_answer} />
          )}
          {hasBaseline && detail.baseline_answer && (
            <Block label="Baseline answer (no KB)" body={detail.baseline_answer} />
          )}
          {j?.reasoning && (
            <Block label="Judge reasoning" body={j.reasoning} muted />
          )}
          {(j?.missing_facts.length ?? 0) > 0 && (
            <div style={{ fontSize: 11, color: '#f59e0b' }}>
              <b>Missing:</b> {j!.missing_facts.join(' · ')}
            </div>
          )}
          {(j?.hallucinated_facts.length ?? 0) > 0 && (
            <div style={{ fontSize: 11, color: '#ef4444' }}>
              <b>Hallucinated:</b> {j!.hallucinated_facts.join(' · ')}
            </div>
          )}
          {detail.retrieved_sources && detail.retrieved_sources.length > 0 && (
            <div style={{ fontSize: 10, color: '#666' }}>
              Retrieved: {detail.retrieved_sources.join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Block({ label, body, muted = false }: { label: string; body: string; muted?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: '#666', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 12, color: muted ? '#999' : '#e5e5e5', whiteSpace: 'pre-wrap' as const, lineHeight: 1.5 }}>
        {body}
      </div>
    </div>
  )
}

function VerdictDot({ verdict }: { verdict: string | null }) {
  const c = verdict === 'PASS' ? '#22c55e' : verdict === 'WARN' ? '#f59e0b' : verdict === 'FAIL' ? '#ef4444' : '#666'
  return (
    <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: c, flexShrink: 0 }} />
  )
}

function discColor(d: string) {
  if (d === 'useful') return '#22c55e'
  if (d === 'redundant') return '#888'
  if (d === 'failing') return '#ef4444'
  return '#666'
}
