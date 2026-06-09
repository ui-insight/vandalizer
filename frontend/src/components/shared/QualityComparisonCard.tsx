import { useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { BarRow } from './BarRow'

export interface BaselinePoint {
  id: string
  label: string
  /** Score in [0, 1] or null if not measured. Null entries render as 0% bars. */
  score: number | null
  /** Bar color (hex). */
  color: string
  /** Visually emphasise (larger, bold) — typically the optimized row. */
  emphasised?: boolean
}

/** Paired-bootstrap CI on the optimized-vs-default lift, computed by the
 * backend from per-query data. Treats the two arms as paired observations on
 * the same eval set, which is the only honest CI shape for a per-query lift. */
export interface LiftCIInput {
  lift: number          // observed lift (e.g. 0.13 = +13pts)
  lower: number         // bootstrap lower bound (delta in [0,1] space)
  upper: number         // bootstrap upper bound
  p_value: number       // permutation p-value, two-sided
  n_queries: number
  n_iterations: number
  confidence_level?: number  // e.g. 0.95; falls back to 95% in the readout
}

interface QualityComparisonCardProps {
  /**
   * Ordered list of baselines to render top-to-bottom (typically 2–4 entries).
   * For KB Autovalidate this is no-KB / default / optimized; extraction will
   * have no-tool / default / optimized; workflow no-workflow / default / optimized.
   */
  baselines: BaselinePoint[]
  /** Judge variance (stddev of judge re-runs). Legacy noise-floor estimate;
   * used only as a fallback when ``liftCI`` is absent. */
  variance: number
  /** Paired-bootstrap CI on the lift (preferred). When provided, drives the
   * headline CI band and the "is this significant?" check. */
  liftCI?: LiftCIInput | null
  /**
   * Which baseline is the "default" the optimized result is compared against.
   * The lift readout shows "+N pts over default". Defaults to baseline id `default`.
   */
  defaultBaselineId?: string
  /**
   * Which baseline is the optimized result. Defaults to baseline id `optimized`.
   */
  optimizedBaselineId?: string
  /**
   * Optional secondary baseline to show as a tiny "+N pts over X" suffix
   * after the primary lift readout. Typical: the no-tool floor.
   */
  secondaryBaselineId?: string
  title?: string
  /** Lift smaller than this (pts) is flagged as inside judge noise. Default 5. */
  insignificantThreshold?: number
  /** Optional extra content rendered between the title and the bars — e.g. an
   * eval-set composition strip so the reader knows what kind of eval the
   * score was measured on. */
  topSlot?: React.ReactNode
  /** Optional content slot below the lift readout — used for the
   * improved/regressed counter and other per-query diagnostics. */
  bottomSlot?: React.ReactNode
  /** Optional tooltip text explaining how the score is computed (e.g. the
   * blended-quality weighting). Renders as a small ⓘ next to the title. */
  scoreFormulaHint?: string
}

export function QualityComparisonCard({
  baselines, variance, liftCI,
  defaultBaselineId = 'default',
  optimizedBaselineId = 'optimized',
  secondaryBaselineId,
  title = 'Optimization complete',
  insignificantThreshold = 5,
  topSlot, bottomSlot, scoreFormulaHint,
}: QualityComparisonCardProps) {
  const [ciExpanded, setCiExpanded] = useState(false)
  // Legacy noise-floor band. σ × 1.96 from two judge-replay deltas: this is
  // *not* the SE of the score estimate, but it's all we have for older runs
  // that lack per-query data. Real significance comes from liftCI.
  const legacyCi = variance * 1.96
  const defaultBaseline = baselines.find(b => b.id === defaultBaselineId)
  const optimizedBaseline = baselines.find(b => b.id === optimizedBaselineId)
  const secondaryBaseline = secondaryBaselineId
    ? baselines.find(b => b.id === secondaryBaselineId)
    : undefined

  const liftVsDefault = optimizedBaseline?.score != null && defaultBaseline?.score != null
    ? (optimizedBaseline.score - defaultBaseline.score) * 100
    : null
  const liftVsSecondary = optimizedBaseline?.score != null && secondaryBaseline?.score != null
    ? (optimizedBaseline.score - secondaryBaseline.score) * 100
    : null

  // Preferred path: paired-bootstrap test. Significant when the CI excludes 0
  // AND the permutation p-value is below 0.05.
  // Fallback path: legacy 2σ noise floor (older runs).
  const liftSignificant = liftCI
    ? (liftCI.lower > 0 || liftCI.upper < 0) && liftCI.p_value < 0.05
    : liftVsDefault != null && Math.abs(liftVsDefault / 100) > 2 * legacyCi
  const liftIsNoise = liftVsDefault != null && !liftSignificant
    && (liftCI != null || Math.abs(liftVsDefault) < insignificantThreshold)

  return (
    <div style={{
      padding: 16, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <CheckCircle2 size={16} style={{ color: '#22c55e' }} />
        <h3 style={{ margin: 0, fontSize: 14, color: '#fff' }}>{title}</h3>
        {scoreFormulaHint && (
          <span
            title={scoreFormulaHint}
            aria-label={scoreFormulaHint}
            style={{
              fontSize: 11, color: '#888', cursor: 'help', userSelect: 'none',
              border: '1px solid #444', borderRadius: '50%',
              width: 14, height: 14, lineHeight: '12px', textAlign: 'center',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}
          >ⓘ</span>
        )}
        {liftCI ? (
          <button
            onClick={() => setCiExpanded(v => !v)}
            title={`Paired bootstrap on ${liftCI.n_queries} queries, ${liftCI.n_iterations} resamples`}
            style={{
              marginLeft: 'auto', fontSize: 10,
              color: liftSignificant ? '#86efac' : '#fbbf24',
              fontFamily: 'inherit',
              background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
              textDecoration: 'underline dotted', textUnderlineOffset: 2,
            }}
          >
            95% CI: {fmtSignedPts(liftCI.lower * 100)} to {fmtSignedPts(liftCI.upper * 100)} {ciExpanded ? '▴' : '▾'}
          </button>
        ) : legacyCi > 0 ? (
          <button
            onClick={() => setCiExpanded(v => !v)}
            style={{
              marginLeft: 'auto', fontSize: 10, color: '#888', fontFamily: 'inherit',
              background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
              textDecoration: 'underline dotted', textUnderlineOffset: 2,
            }}
          >
            noise floor: ±{(legacyCi * 100).toFixed(1)}pts {ciExpanded ? '▴' : '▾'}
          </button>
        ) : null}
      </div>

      {ciExpanded && (
        <div style={{
          marginBottom: 12, padding: '8px 10px', fontSize: 11, color: '#aaa', lineHeight: 1.5,
          backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid #2a2a2a', borderRadius: 6,
        }}>
          {liftCI ? (
            <>
              <strong>Paired bootstrap:</strong> we computed this CI by resampling
              the per-query (default → optimized) scores {liftCI.n_iterations.toLocaleString()} times.
              The {(liftCI.confidence_level ? liftCI.confidence_level * 100 : 95).toFixed(0)}% interval
              for the per-query lift is [{fmtSignedPts(liftCI.lower * 100)}, {fmtSignedPts(liftCI.upper * 100)}].
              A two-sided permutation p-value gives <strong>p={liftCI.p_value < 0.001 ? '<0.001' : liftCI.p_value.toFixed(3)}</strong>{' '}
              ({liftSignificant ? 'significant' : 'not significant'}).
              {' '}n={liftCI.n_queries} queries.
            </>
          ) : (
            <>
              The LLM judge has natural variance when scoring the same answer twice — typically
              ±{(legacyCi * 100).toFixed(1)}pts at 95% confidence. This is the legacy noise-floor
              estimate from 2 judge replays. New runs use a paired-bootstrap CI computed from
              per-query data, which is the honest comparison here.
            </>
          )}
        </div>
      )}

      {topSlot && (
        <div style={{ marginBottom: 12 }}>{topSlot}</div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {baselines.map(b => (
          <BarRow
            key={b.id}
            label={b.label}
            pct={(b.score ?? 0) * 100}
            color={b.color}
            emphasised={b.emphasised}
          />
        ))}
      </div>

      {liftVsDefault != null && (
        <div style={{
          marginTop: 14, padding: '10px 12px',
          backgroundColor: liftIsNoise
            ? 'rgba(245, 158, 11, 0.08)'
            : liftVsDefault > 0 ? 'rgba(34, 197, 94, 0.08)' : 'rgba(239, 68, 68, 0.08)',
          border: '1px solid ' + (liftIsNoise
            ? 'rgba(245, 158, 11, 0.3)'
            : liftVsDefault > 0 ? 'rgba(34, 197, 94, 0.25)' : 'rgba(239, 68, 68, 0.25)'),
          borderRadius: 6,
        }}>
          {liftIsNoise ? (
            <>
              <div style={{
                fontSize: 14, fontWeight: 600, color: '#f59e0b',
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                ⚠ No significant change
              </div>
              <div style={{ marginTop: 4, fontSize: 11, color: '#888', lineHeight: 1.5 }}>
                {liftCI
                  ? `The 95% CI on the per-query lift spans zero (${fmtSignedPts(liftCI.lower * 100)} to ${fmtSignedPts(liftCI.upper * 100)}, n=${liftCI.n_queries}, p=${liftCI.p_value < 0.001 ? '<0.001' : liftCI.p_value.toFixed(3)}). Treat the optimized run as equivalent to default.`
                  : `The ${liftVsDefault > 0 ? '+' : ''}${liftVsDefault.toFixed(0)}pts difference is inside the judge's measurement noise (±${(legacyCi * 100).toFixed(1)}pts) — treat the optimized run as equivalent to default.`}
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
              <span style={{
                fontSize: 18, fontWeight: 700,
                color: liftVsDefault > 0 ? '#22c55e' : '#ef4444',
              }}>
                {liftVsDefault > 0 ? '+' : ''}{liftVsDefault.toFixed(0)}pts
              </span>
              <span style={{ fontSize: 12, color: '#aaa' }}>over {defaultBaseline?.label ?? 'default'}</span>
              {liftVsSecondary != null && secondaryBaseline && (
                <>
                  <span style={{ fontSize: 12, color: '#666' }}>·</span>
                  <span style={{ fontSize: 12, color: '#aaa' }}>
                    +{liftVsSecondary.toFixed(0)}pts over {secondaryBaseline.label}
                  </span>
                </>
              )}
              <SignificanceBadge liftCI={liftCI ?? null} liftSignificant={liftSignificant} />
            </div>
          )}
        </div>
      )}

      {bottomSlot && (
        <div style={{ marginTop: 12 }}>{bottomSlot}</div>
      )}
    </div>
  )
}

// Minimum paired-bootstrap sample size below which the CI is too wobbly to
// trust — surfaced as "n too small" rather than a green/amber call. n=5 is the
// usual lower bound for paired-bootstrap stability on 0..1 score deltas.
const MIN_N_FOR_SIGNIFICANCE = 5

function SignificanceBadge({
  liftCI, liftSignificant,
}: {
  liftCI: LiftCIInput | null
  liftSignificant: boolean
}) {
  if (!liftCI) return null
  let label: string
  let bg: string
  let border: string
  let color: string
  let tip: string
  if (liftCI.n_queries < MIN_N_FOR_SIGNIFICANCE) {
    label = `n too small (${liftCI.n_queries})`
    bg = 'rgba(120,120,120,0.18)'
    border = 'rgba(160,160,160,0.35)'
    color = '#bbb'
    tip = `Paired-bootstrap CI needs at least ${MIN_N_FOR_SIGNIFICANCE} judged queries to be reliable. Add more test questions to get a trustworthy significance call.`
  } else if (liftSignificant) {
    const pTxt = liftCI.p_value < 0.001 ? 'p<0.001' : `p=${liftCI.p_value.toFixed(3)}`
    label = `✓ significant (${pTxt})`
    bg = 'rgba(34, 197, 94, 0.14)'
    border = 'rgba(34, 197, 94, 0.40)'
    color = '#86efac'
    tip = `95% CI excludes zero and permutation p-value < 0.05 across n=${liftCI.n_queries} paired queries.`
  } else {
    const pTxt = liftCI.p_value < 0.001 ? 'p<0.001' : `p=${liftCI.p_value.toFixed(3)}`
    label = `not significant (${pTxt})`
    bg = 'rgba(245, 158, 11, 0.12)'
    border = 'rgba(245, 158, 11, 0.35)'
    color = '#fbbf24'
    tip = `95% CI on the per-query lift includes zero — we can't tell the optimized config apart from default at this sample size (n=${liftCI.n_queries}).`
  }
  return (
    <span
      title={tip}
      style={{
        marginLeft: 'auto', fontSize: 11, fontWeight: 600,
        padding: '2px 8px', borderRadius: 999, cursor: 'help',
        backgroundColor: bg, border: '1px solid ' + border, color,
      }}
    >
      {label}
    </span>
  )
}

function fmtSignedPts(p: number): string {
  return `${p >= 0 ? '+' : ''}${p.toFixed(1)}pts`
}
