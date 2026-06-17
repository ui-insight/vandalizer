import { useMemo, useState } from 'react'
import { RotateCcw, Sparkles } from 'lucide-react'
import type { KBOptimizationRun, OptimizationSuggestion, OptimizationTrial, PerQueryResult } from '../../api/knowledge'
import { OptimizationHistoryPanel } from './OptimizationHistoryPanel'
import { FailedBanner, CancelledBanner } from '../shared/RunBanners'
import { ApplyBackButton } from '../shared/ApplyBackButton'
import { SuggestionsList, type Suggestion } from '../shared/SuggestionsList'
import { QualityComparisonCard, type BaselinePoint } from '../shared/QualityComparisonCard'
import { TrialsTable, TrialRow, makeStandardSortOptions } from '../shared/TrialsTable'
import { TrialExplainerModal } from './TrialExplainerModal'
import { EvalSetCompositionStrip } from '../shared/EvalSetCompositionStrip'
import { TriCounter } from '../shared/TriCounter'
import { TrialQueryDeltas } from '../shared/TrialQueryDeltas'
import { ReproducibilityPanel } from '../shared/ReproducibilityPanel'
import { CrossJudgeNote } from '../shared/CrossJudgeNote'
import { DOMAIN_LABELS } from '../shared/labels'

interface Props {
  run: KBOptimizationRun
  canManage: boolean
  onApply: () => void
  applying: boolean
  onRunAgain: () => void
  /** Revert a previously-applied run to its prior override. Optional so
   * read-only past-run views can omit it. */
  onRevert?: () => void
  reverting?: boolean
  /** Optional click-through to view a different past run from the history list. */
  onSelectPastRun?: (runUuid: string) => void
}

export function OptimizationResults({
  run, canManage, onApply, applying, onRunAgain, onRevert, reverting, onSelectPastRun,
}: Props) {
  // Winning trial's per-query results. Hooks must run unconditionally — pre-
  // computing here keeps the rules-of-hooks order stable across failed /
  // cancelled / completed branches below.
  const winningTrial: OptimizationTrial | undefined = useMemo(() => {
    if (!run.trials || run.trials.length === 0) return undefined
    if (run.best_config) {
      const exact = run.trials.find(t =>
        t.config && JSON.stringify(t.config) === JSON.stringify(run.best_config),
      )
      if (exact) return exact
    }
    return [...run.trials].sort((a, b) => b.score - a.score)[0]
  }, [run.trials, run.best_config])

  // Trial tapped open in the plain-English explainer modal. Declared before the
  // early returns below so hook order stays stable across run states.
  const [selectedTrial, setSelectedTrial] = useState<OptimizationTrial | null>(null)

  if (run.status === 'failed') {
    return (
      <FailedBanner
        message={run.error_message || 'Optimization failed.'}
        errorCode={run.error_code ?? null}
        onRunAgain={onRunAgain}
      />
    )
  }
  if (run.status === 'cancelled') {
    return (
      <CancelledBanner
        completedTrials={run.trials.length}
        onRunAgain={onRunAgain}
      />
    )
  }

  const kbLabels = DOMAIN_LABELS.kb.baselineTile
  const baselines: BaselinePoint[] = [
    { id: 'no-kb', label: kbLabels.noBaseline, score: run.baseline_no_kb_score, color: '#888' },
    { id: 'default', label: kbLabels.yourSettings, score: run.baseline_default_score, color: '#3b82f6' },
    { id: 'optimized', label: kbLabels.tuned, score: run.optimized_score, color: '#22c55e', emphasised: true },
  ]

  const winningPerQuery: PerQueryResult[] | undefined = winningTrial?.per_query_results
  const defaultPerQuery: PerQueryResult[] | undefined = run.default_per_query_results
  const noKbPerQuery: PerQueryResult[] | undefined = run.no_kb_per_query_results

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Comparison card — now with eval-set composition strip and the
          improved/regressed counter rendered inline so users get the credibility
          context before they read the headline number. */}
      <QualityComparisonCard
        baselines={baselines}
        variance={run.judge_variance ?? 0}
        liftCI={run.lift_ci ?? null}
        secondaryBaselineId="no-kb"
        scoreFormulaHint={
          'Quality score = 40% LLM judge + 25% retrieval precision + 20% source health + 15% chunk coverage. '
          + 'Matches the score the validation header reports.'
        }
        topSlot={
          <EvalSetCompositionStrip
            snapshot={run.test_query_snapshot}
            fallbackQueryCount={
              run.test_query_snapshot?.total
              ?? winningPerQuery?.length
              ?? defaultPerQuery?.length
              ?? null
            }
          />
        }
        bottomSlot={
          (winningPerQuery?.length ?? 0) > 0 && (defaultPerQuery?.length ?? 0) > 0
            ? <TriCounter optimized={winningPerQuery} baseline={defaultPerQuery} />
            : null
        }
      />

      {/* Cross-judge sanity check — only shown when a second judge actually
          ran (gated by token budget in the backend). */}
      {run.cross_judge && (
        <CrossJudgeNote
          crossJudge={run.cross_judge}
          primaryScore={run.optimized_score ?? 0}
          primaryJudge={run.judge_model ?? null}
        />
      )}

      {/* Best config + Apply / Revert. ``isAlreadyApplied`` is true if this
          run is the one currently live on the KB. We trust applied_at /
          reverted_at when present (post-Phase-1) and fall back to the legacy
          ``apply_on_finish`` flag for runs that pre-date the snapshot. */}
      {run.best_config && (
        <BestConfigCard
          config={run.best_config}
          defaultConfig={run.default_config ?? null}
          isAlreadyApplied={
            !!(run.applied_at && !run.reverted_at)
            || (!run.applied_at && !!run.options?.apply_on_finish)
          }
          canRevert={!!(run.applied_at && !run.reverted_at && onRevert)}
          canManage={canManage}
          onApply={onApply}
          applying={applying}
          onRevert={onRevert}
          reverting={!!reverting}
        />
      )}

      {/* Per-query delta table — the biggest trust unlock. Click any row to
          see the trace. */}
      {(winningPerQuery?.length ?? 0) > 0 && (
        <TrialQueryDeltas
          optimized={winningPerQuery}
          baseline={defaultPerQuery}
          noKb={noKbPerQuery}
        />
      )}

      {/* Suggestions */}
      {run.data_source_suggestions.length > 0 && (
        <SuggestionsList
          title="Data-source suggestions"
          suggestions={run.data_source_suggestions.map(toGenericSuggestion)}
        />
      )}

      {/* Trials table — rows are tappable to open the plain-English explainer. */}
      {run.trials.length > 0 && (
        <TrialsTable
          trials={run.trials}
          sortOptions={KB_TRIAL_SORT_OPTIONS}
          renderRow={(t) => <TrialRow trial={t} summariseConfig={summariseConfig} />}
          getRowKey={(t) => t.trial_id}
          onRowClick={setSelectedTrial}
          title="Trials — tap any for a plain-English breakdown"
        />
      )}

      {/* Plain-English explainer for a tapped trial. */}
      <TrialExplainerModal trial={selectedTrial} onClose={() => setSelectedTrial(null)} />

      {/* Reproducibility — judge model, prompt version, seed, variance n */}
      <ReproducibilityPanel run={run} />


      {/* Past runs (with compare-this-vs-that affordance) */}
      <OptimizationHistoryPanel
        kbUuid={run.kb_uuid}
        excludeRunUuid={run.uuid}
        onSelect={onSelectPastRun}
        compareAgainstRunUuid={run.uuid}
      />

      {/* Re-run */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={onRunAgain}
          disabled={!canManage}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            color: canManage ? '#a78bfa' : '#555',
            background: 'transparent',
            border: '1px solid ' + (canManage ? 'rgba(124, 58, 237, 0.3)' : '#333'),
            borderRadius: 6, cursor: canManage ? 'pointer' : 'not-allowed',
          }}
        >
          <RotateCcw size={12} />
          Re-run
        </button>
      </div>
    </div>
  )
}

/** Renders the winning config as a default→winner diff. Rows whose value
 * matches the default config are collapsed into an "unchanged" expander so
 * users can see at a glance what the optimizer actually changed. */
function BestConfigCard({
  config, defaultConfig, isAlreadyApplied, canRevert, canManage, onApply, applying, onRevert, reverting,
}: {
  config: OptimizationTrial['config']
  defaultConfig: OptimizationTrial['config'] | null
  isAlreadyApplied: boolean
  canRevert: boolean
  canManage: boolean
  onApply: () => void
  applying: boolean
  onRevert?: () => void
  reverting: boolean
}) {
  const [showUnchanged, setShowUnchanged] = useState(false)
  const fmt = (key: keyof OptimizationTrial['config'], v: unknown): string => {
    if (key === 'model') return (v as string | null) || 'default'
    if (key === 'query_rewriting') return v ? 'on' : 'off'
    if (key === 'source_label_visibility') return v ? 'visible' : 'hidden'
    return String(v)
  }
  const fields: { key: keyof OptimizationTrial['config']; label: string; hint: string }[] = [
    { key: 'k', label: 'Top-k chunks', hint: 'How many document excerpts to feed the model when answering.' },
    { key: 'model', label: 'Model', hint: 'Which LLM answers the question.' },
    { key: 'prompt_variant', label: 'Prompt variant', hint: 'How strictly the model should stick to your sources (strict = refuse when unsure; concise = shorter answers).' },
    { key: 'query_rewriting', label: 'Query rewriting', hint: "Whether to expand the user's question into multiple phrasings before searching." },
    { key: 'source_label_visibility', label: 'Source labels in context', hint: 'Whether the model sees document titles when answering.' },
  ]
  const rows = fields.map(f => {
    const winner = fmt(f.key, (config as Record<string, unknown>)[f.key])
    const def = defaultConfig
      ? fmt(f.key, (defaultConfig as Record<string, unknown>)[f.key])
      : null
    return { ...f, winner, def, changed: def !== null && def !== winner }
  })
  const changed = rows.filter(r => r.changed)
  const unchanged = rows.filter(r => !r.changed)
  const hasDefault = defaultConfig != null

  return (
    <div style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Sparkles size={14} style={{ color: '#a78bfa' }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>Best configuration</span>
        {hasDefault && (
          <span style={{ fontSize: 11, color: '#888', marginLeft: 8 }}>
            {changed.length === 0
              ? 'identical to default — no knobs changed'
              : `${changed.length} knob${changed.length === 1 ? '' : 's'} changed vs default`}
          </span>
        )}
      </div>

      {/* If we don't have a default snapshot (legacy run), fall back to the
          flat grid; otherwise show diff rows only. */}
      {!hasDefault ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          {rows.map(r => (
            <div key={r.key} title={r.hint} style={{
              padding: '6px 10px', backgroundColor: '#262626', borderRadius: 4, cursor: 'help',
            }}>
              <div style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>{r.label}</div>
              <div style={{ fontSize: 12, color: '#e5e5e5', marginTop: 2 }}>{r.winner}</div>
            </div>
          ))}
        </div>
      ) : changed.length === 0 ? (
        <div style={{
          padding: '8px 12px', fontSize: 12, color: '#bbb',
          backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid #2a2a2a',
          borderRadius: 6,
        }}>
          The optimizer didn't find a better setting than your current default. Your
          KB is already tuned for this test set.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {changed.map(r => (
            <div key={r.key} title={r.hint} style={{
              padding: '8px 10px', backgroundColor: '#262626', borderRadius: 4, cursor: 'help',
              display: 'grid', gridTemplateColumns: '1fr auto 1fr auto 1fr',
              alignItems: 'center', gap: 8,
            }}>
              <div>
                <div style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>{r.label}</div>
              </div>
              <div style={{ fontSize: 12, color: '#888', textDecoration: 'line-through' }}>{r.def}</div>
              <div style={{ fontSize: 12, color: '#666', textAlign: 'center' }}>→</div>
              <div style={{ fontSize: 13, color: '#86efac', fontWeight: 600 }}>{r.winner}</div>
              <div />
            </div>
          ))}
          {unchanged.length > 0 && (
            <button
              onClick={() => setShowUnchanged(v => !v)}
              style={{
                marginTop: 4, padding: '4px 8px',
                fontSize: 11, fontFamily: 'inherit', color: '#888',
                background: 'transparent', border: 'none', cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              {showUnchanged ? '▾' : '▸'} {unchanged.length} unchanged knob{unchanged.length === 1 ? '' : 's'}
            </button>
          )}
          {showUnchanged && unchanged.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {unchanged.map(r => (
                <div key={r.key} title={r.hint} style={{
                  padding: '6px 10px', backgroundColor: '#202020', borderRadius: 4, cursor: 'help',
                }}>
                  <div style={{ fontSize: 10, color: '#666', textTransform: 'uppercase', letterSpacing: 0.5 }}>{r.label}</div>
                  <div style={{ fontSize: 12, color: '#999', marginTop: 2 }}>{r.winner}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
        <ApplyBackButton
          canApply={canManage}
          onApply={onApply}
          applying={applying}
          isAlreadyApplied={isAlreadyApplied}
        />
        {canRevert && onRevert && (
          <button
            onClick={onRevert}
            disabled={!canManage || reverting}
            style={{
              padding: '6px 12px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
              color: canManage && !reverting ? '#bbb' : '#555',
              background: 'transparent',
              border: '1px solid #3a3a3a',
              borderRadius: 6,
              cursor: canManage && !reverting ? 'pointer' : 'not-allowed',
            }}
            title="Restore your previous KB configuration"
          >
            {reverting ? 'Reverting…' : 'Revert'}
          </button>
        )}
      </div>
    </div>
  )
}

/** Convert KB-domain OptimizationSuggestion to the generic Suggestion shape. */
function toGenericSuggestion(s: OptimizationSuggestion): Suggestion {
  return { severity: s.severity, message: s.message }
}

const KB_TRIAL_SORT_OPTIONS = makeStandardSortOptions<OptimizationTrial>()

function summariseConfig(c: OptimizationTrial['config']) {
  const bits = [`k=${c.k}`]
  if (c.model) bits.push(c.model)
  if (c.prompt_variant && c.prompt_variant !== 'default') bits.push(c.prompt_variant)
  if (c.query_rewriting) bits.push('query-rewrite')
  if (c.source_label_visibility === false) bits.push('no-source-labels')
  return bits.join(' · ')
}

/** Verbose form for the running-state summary — translates each abbreviation
 * into a phrase, since the user may be seeing these terms for the first time
 * mid-run. Exported so OptimizationProgress can use it. */
export function summariseConfigVerbose(c: OptimizationTrial['config']) {
  const bits = [`${c.k} chunks`]
  if (c.model) bits.push(c.model)
  if (c.prompt_variant && c.prompt_variant !== 'default') bits.push(`${c.prompt_variant} prompt`)
  if (c.query_rewriting) bits.push('expands questions')
  if (c.source_label_visibility === false) bits.push('sources hidden')
  return bits.join(' · ')
}
