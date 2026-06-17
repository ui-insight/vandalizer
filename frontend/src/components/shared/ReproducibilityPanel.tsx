import { useState } from 'react'
import { ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react'

export interface ReproducibilityRun {
  judge_model: string | null
  judge_prompt_version?: string | null
  judge_temperature?: number | null
  rng_seed?: number | null
  judge_variance: number | null
  judge_variance_meta?: { n?: number; sampled_query_uuids?: string[] } | null
  test_query_snapshot?: {
    total: number
    auto_generated_count: number
    user_authored_count: number
  } | null
  lift_ci?: {
    lower: number
    upper: number
    n_queries: number
    n_iterations: number
    p_value: number
  } | null
  started_at: string | null
}

interface Props {
  run: ReproducibilityRun
}

/**
 * Reproducibility panel: judge model, prompt version, seed, variance n+queries,
 * lift-CI provenance. Collapsed by default so it doesn't dominate the layout,
 * but expanded answers "could I rerun this and get the same answer?".
 *
 * Fields not provided by the caller render as "—" with explanatory tooltips.
 */
export function ReproducibilityPanel({ run }: Props) {
  const [open, setOpen] = useState(false)

  const variance = run.judge_variance
  const meta = run.judge_variance_meta
  const ci = run.lift_ci
  const snapshot = run.test_query_snapshot

  const rows: { label: string; value: string; title?: string }[] = [
    { label: 'Judge model', value: run.judge_model || 'unknown' },
    {
      label: 'Judge prompt',
      value: run.judge_prompt_version || 'unversioned',
      title: 'SHA-256 prefix of the judge system prompt. Changes any time the rubric text changes.',
    },
    {
      label: 'Judge temperature',
      value: run.judge_temperature == null ? '—' : run.judge_temperature.toFixed(2),
    },
    {
      label: 'RNG seed',
      value: run.rng_seed != null ? String(run.rng_seed) : '—',
      title: 'Persisted so re-runs are deterministic given the same eval set + config space.',
    },
    {
      label: 'Judge variance',
      value: variance != null
        ? `σ=${(variance * 100).toFixed(1)}pts` + (meta?.n ? ` (n=${meta.n})` : '')
        : '—',
      title: meta?.sampled_query_uuids?.length
        ? `Sampled on queries: ${meta.sampled_query_uuids.slice(0, 5).join(', ')}${meta.sampled_query_uuids.length > 5 ? '…' : ''}`
        : undefined,
    },
    {
      label: 'Lift CI',
      value: ci
        ? `${fmtSignedPts(ci.lower * 100)} to ${fmtSignedPts(ci.upper * 100)} (n=${ci.n_queries}, p=${ci.p_value < 0.001 ? '<0.001' : ci.p_value.toFixed(3)})`
        : '—',
      title: ci
        ? `Paired-bootstrap CI, ${ci.n_iterations.toLocaleString()} resamples.`
        : 'Per-query CI unavailable for older runs.',
    },
    {
      label: 'Eval set',
      value: snapshot
        ? `${snapshot.total} queries · ${snapshot.auto_generated_count} auto / ${snapshot.user_authored_count} user`
        : '—',
      title: snapshot
        ? 'Snapshot taken at run start. Future runs comparing against this one will check expected-answer hashes for drift.'
        : undefined,
    },
  ]

  return (
    <div style={{
      backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, width: '100%',
          padding: '10px 14px', background: 'transparent', border: 'none',
          fontFamily: 'inherit', cursor: 'pointer', color: '#e5e5e5',
          textAlign: 'left',
        }}
      >
        {open ? <ChevronDown size={14} style={{ color: '#888' }} /> : <ChevronRight size={14} style={{ color: '#888' }} />}
        <ShieldCheck size={14} style={{ color: '#888' }} />
        <span style={{ fontSize: 13, fontWeight: 600 }}>Reproducibility</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#666' }}>
          {run.judge_model || 'unknown judge'}{run.rng_seed != null ? ` · seed ${run.rng_seed}` : ''}
        </span>
      </button>

      {open && (
        <div style={{
          padding: '4px 14px 14px 14px',
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 8,
        }}>
          {rows.map(r => (
            <div
              key={r.label}
              title={r.title}
              style={{
                padding: '6px 10px', backgroundColor: '#262626', borderRadius: 4,
              }}
            >
              <div style={{ fontSize: 9, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>{r.label}</div>
              <div style={{ fontSize: 11, color: '#e5e5e5', marginTop: 2, wordBreak: 'break-word' }}>{r.value}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function fmtSignedPts(p: number): string {
  return `${p >= 0 ? '+' : ''}${p.toFixed(1)}pts`
}
