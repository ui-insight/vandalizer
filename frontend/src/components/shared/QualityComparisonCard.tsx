import { useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { BarRow } from './BarRow'
import { InfoHint } from './InfoHint'

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

// Minimum paired-bootstrap sample size below which the CI is too wobbly to
// trust — surfaced as "n too small" / "not enough queries" rather than a
// green/amber call. n=5 is the usual lower bound for paired-bootstrap
// stability on 0..1 score deltas.
const MIN_N_FOR_SIGNIFICANCE = 5

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
  /** Optional one-liner under the bars saying which eval slice each bar was
   * measured on (e.g. held-out vs training queries). Keeps the bars honest
   * when different rows come from different slices. */
  measurementNote?: string
  /** The run's own verdict (``tied_with_baseline``): whether its result is
   * within noise of the current settings. When given, it decides the outcome
   * banner, so the card says what the Apply gate and chat say. The card's own
   * estimate below is only for callers without a run verdict. */
  tiedWithBaseline?: boolean
}

export function QualityComparisonCard({
  baselines, variance, liftCI,
  defaultBaselineId = 'default',
  optimizedBaselineId = 'optimized',
  secondaryBaselineId,
  title = 'Optimization complete',
  insignificantThreshold = 5,
  topSlot, bottomSlot, scoreFormulaHint, measurementNote, tiedWithBaseline,
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
  // The differences the text states are between the whole percents the bars
  // show: 94.6% vs 93.4% reads "95%" and "93%", so the text says +2, never +1.
  // The unrounded lift above still drives the significance calls.
  const shownLiftVsDefault = shownDifference(optimizedBaseline?.score, defaultBaseline?.score)
  const shownLiftVsSecondary = shownDifference(optimizedBaseline?.score, secondaryBaseline?.score)

  // Preferred path: paired-bootstrap test. Significant when the CI excludes 0
  // AND the permutation p-value is below 0.05.
  // Fallback path: legacy 2σ noise floor (older runs).
  const ciSignificant = liftCI
    ? (liftCI.lower > 0 || liftCI.upper < 0) && liftCI.p_value < 0.05
    : false
  // The card once decided this itself, on a band about twice the optimizer's,
  // and said "No significant change" beside an enabled Apply button while chat
  // called the same result a gain. The run's verdict wins when there is one.
  const liftSignificant = tiedWithBaseline != null
    ? !tiedWithBaseline
    : liftCI
      ? ciSignificant
      : liftVsDefault != null && Math.abs(liftVsDefault / 100) > 2 * legacyCi
  const liftIsNoise = liftVsDefault != null && (tiedWithBaseline != null
    ? tiedWithBaseline
    : !liftSignificant && (liftCI != null || Math.abs(liftVsDefault) < insignificantThreshold))
  const ciSpansZero = liftCI != null && liftCI.lower <= 0 && liftCI.upper >= 0
  // Below the paired-bootstrap reliability floor we can't call it either way —
  // the banner must say "not enough data", never "equivalent to default".
  const nTooSmall = liftCI != null && liftCI.n_queries < MIN_N_FOR_SIGNIFICANCE
  // The paired test runs on per-query answer-quality scores, but the bars show
  // the blended score, which also folds in components measured once per
  // configuration (retrieval precision, source health, coverage). When the two
  // diverge, the banner must say which one the statistics cover — otherwise
  // "no significant change" flatly contradicts visibly different bars.
  const judgeLiftPts = liftCI != null ? liftCI.lift * 100 : null
  const statsCoverageGap = judgeLiftPts != null && liftVsDefault != null
    && Math.abs(judgeLiftPts - liftVsDefault) > 2

  return (
    <div style={{
      padding: 'var(--workspace-space-16)', backgroundColor: 'var(--workspace-surface)',
      border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-medium)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-12)' }}>
        <CheckCircle2 size={16} style={{ color: 'var(--workspace-success)' }} />
        <h3 style={{ margin: 0, fontSize: 'var(--workspace-font-body)', color: 'var(--workspace-text)' }}>{title}</h3>
        {scoreFormulaHint && (
          <InfoHint content={scoreFormulaHint} label="How this score is computed" />
        )}
        {liftCI ? (
          <button
            onClick={() => setCiExpanded(v => !v)}
            title={`Paired bootstrap on ${liftCI.n_queries} queries, ${liftCI.n_iterations} resamples`}
            style={{
              marginLeft: 'auto', fontSize: 'var(--workspace-font-meta)',
              color: ciSignificant ? 'var(--workspace-success)' : 'var(--workspace-warning)',
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
              marginLeft: 'auto', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', fontFamily: 'inherit',
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
          marginBottom: 'var(--workspace-space-12)', padding: "var(--workspace-space-8) var(--workspace-space-12)", fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.5,
          backgroundColor: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
        }}>
          {liftCI ? (
            <>
              <strong>Paired bootstrap:</strong> we computed this CI by resampling
              the per-query (default → optimized) answer-quality scores {liftCI.n_iterations.toLocaleString()} times.
              The {(liftCI.confidence_level ? liftCI.confidence_level * 100 : 95).toFixed(0)}% interval
              for the per-query lift is [{fmtSignedPts(liftCI.lower * 100)}, {fmtSignedPts(liftCI.upper * 100)}].
              A two-sided permutation p-value gives <strong>p={liftCI.p_value < 0.001 ? '<0.001' : liftCI.p_value.toFixed(3)}</strong>{' '}
              ({ciSignificant ? 'significant' : 'not significant'}).
              {' '}n={liftCI.n_queries} paired queries.
              {statsCoverageGap && (
                ' Bar heights are the blended quality score, which also includes components measured once per configuration — only the per-query answer-quality portion can be significance-tested.'
              )}
            </>
          ) : (
            <>
              The LLM judge has natural variance when scoring the same answer twice, typically
              ±{(legacyCi * 100).toFixed(1)}pts at 95% confidence. This is the legacy noise-floor
              estimate from 2 judge replays. New runs use a paired-bootstrap CI computed from
              per-query data, which is the honest comparison here.
            </>
          )}
        </div>
      )}

      {topSlot && (
        <div style={{ marginBottom: 'var(--workspace-space-12)' }}>{topSlot}</div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-12)' }}>
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

      {measurementNote && (
        <div style={{ marginTop: 'var(--workspace-space-8)', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.5 }}>
          {measurementNote}
        </div>
      )}

      {liftVsDefault != null && (
        <div style={{
          marginTop: 'var(--workspace-space-16)', padding: "var(--workspace-space-12) var(--workspace-space-12)",
          backgroundColor: liftIsNoise
            ? (nTooSmall ? 'rgba(120, 120, 120, 0.10)' : 'rgba(245, 158, 11, 0.08)')
            : liftVsDefault > 0 ? 'rgba(34, 197, 94, 0.08)' : 'rgba(239, 68, 68, 0.08)',
          border: '1px solid ' + (liftIsNoise
            ? (nTooSmall ? 'rgba(160, 160, 160, 0.30)' : 'rgba(245, 158, 11, 0.3)')
            : liftVsDefault > 0 ? 'rgba(34, 197, 94, 0.25)' : 'rgba(239, 68, 68, 0.25)'),
          borderRadius: 'var(--workspace-radius-small)',
        }}>
          {liftIsNoise ? (
            <>
              <div style={{
                fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: nTooSmall ? 'var(--workspace-muted)' : 'var(--workspace-warning)',
                display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
              }}>
                {nTooSmall ? 'Not enough queries for a significance call' : '⚠ No significant change'}
              </div>
              <div style={{ marginTop: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.5 }}>
                {liftCI && nTooSmall
                  ? `Only n=${liftCI.n_queries} paired ${liftCI.n_queries === 1 ? 'query was' : 'queries were'} available for the statistical test — at least ${MIN_N_FOR_SIGNIFICANCE} are needed for a reliable call. The bars are real measurements, but we can't yet tell how much of the difference would repeat on new questions. Add more test queries and re-run for a trustworthy verdict.`
                  : liftCI && ciSpansZero
                    ? `The 95% CI on the per-query lift spans zero (${fmtSignedPts(liftCI.lower * 100)} to ${fmtSignedPts(liftCI.upper * 100)}, n=${liftCI.n_queries}, p=${liftCI.p_value < 0.001 ? '<0.001' : liftCI.p_value.toFixed(3)}). On answer quality, treat the optimized run as equivalent to default.`
                    : `The ${fmtSignedWholePts(shownLiftVsDefault ?? 0)} difference is inside the judge's measurement noise${legacyCi > 0 ? ` (±${(legacyCi * 100).toFixed(1)}pts)` : ''} — treat the optimized run as equivalent to default.`}
                {liftCI && statsCoverageGap && judgeLiftPts != null && (
                  ` The test covers the per-query answer-quality scores (${fmtSignedPts(judgeLiftPts)} there); the rest of the bar difference comes from score components measured once per configuration, which can't be significance-tested.`
                )}
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--workspace-space-8)', flexWrap: 'wrap' }}>
              <span style={{
                fontSize: 'var(--workspace-font-section-title)', fontWeight: 700,
                color: liftVsDefault > 0 ? 'var(--workspace-success)' : 'var(--workspace-danger)',
              }}>
                {fmtSignedWholePts(shownLiftVsDefault ?? 0)}
              </span>
              <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>over {defaultBaseline?.label ?? 'default'}</span>
              {shownLiftVsSecondary != null && secondaryBaseline && (
                <>
                  <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>·</span>
                  <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
                    {fmtSignedWholePts(shownLiftVsSecondary)} vs {secondaryBaseline.label}
                  </span>
                </>
              )}
              <SignificanceBadge liftCI={liftCI ?? null} liftSignificant={liftSignificant} />
            </div>
          )}
        </div>
      )}

      {bottomSlot && (
        <div style={{ marginTop: 'var(--workspace-space-12)' }}>{bottomSlot}</div>
      )}
    </div>
  )
}

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
    color = 'var(--workspace-muted)'
    tip = `Paired-bootstrap CI needs at least ${MIN_N_FOR_SIGNIFICANCE} judged queries to be reliable. Add more test questions to get a trustworthy significance call.`
  } else if (liftSignificant) {
    const pTxt = liftCI.p_value < 0.001 ? 'p<0.001' : `p=${liftCI.p_value.toFixed(3)}`
    label = `✓ significant (${pTxt})`
    bg = 'rgba(34, 197, 94, 0.14)'
    border = 'rgba(34, 197, 94, 0.40)'
    color = 'var(--workspace-success)'
    tip = `95% CI excludes zero and permutation p-value < 0.05 across n=${liftCI.n_queries} paired queries.`
  } else {
    const pTxt = liftCI.p_value < 0.001 ? 'p<0.001' : `p=${liftCI.p_value.toFixed(3)}`
    label = `not significant (${pTxt})`
    bg = 'rgba(245, 158, 11, 0.12)'
    border = 'rgba(245, 158, 11, 0.35)'
    color = 'var(--workspace-warning)'
    tip = `95% CI on the per-query lift includes zero, so we can't tell the optimized config apart from default at this sample size (n=${liftCI.n_queries}).`
  }
  return (
    <span
      title={tip}
      style={{
        marginLeft: 'auto', fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
        padding: "var(--workspace-space-2) var(--workspace-space-8)", borderRadius: 999, cursor: 'help',
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


/** Difference in whole percentage points between two 0..1 scores as displayed. */
export function shownDifference(score: number | null | undefined, against: number | null | undefined): number | null {
  if (score == null || against == null) return null
  return Number((score * 100).toFixed(0)) - Number((against * 100).toFixed(0))
}

function fmtSignedWholePts(pts: number): string {
  return `${pts > 0 ? '+' : ''}${pts}pts`
}
