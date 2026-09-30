import { useMemo, useState } from 'react'
import { Play, Loader2, ChevronDown, ChevronRight, Download } from 'lucide-react'
import {
  type KBValidationGrader,
  type KBTestQuery,
  type KBValidationExportFormat,
  type KBValidationMode,
  type KBValidationRunOptions,
  type KBValidationResult,
  type KBValidationDetail,
} from '../../api/knowledge'
import { explainKBScore } from './kbScoreFormula'
import {
  categoryCounts,
  importBatches,
  resolveRunSelection,
  scopeQueries,
  type QuestionScope,
} from './kbQuestionSet'
import type { ValidationProgress } from '../../hooks/useKBValidationRun'
import { QuestionExpectations } from './QuestionExpectations'
import { useIsAdmin } from '../../utils/truncationWarning'

interface Props {
  kbReady: boolean
  canManage: boolean
  queries: KBTestQuery[]
  /** Questions ticked on the Test Queries tab and handed here by "Run
   *  selected", so the run is reviewed (count, categories) before it starts. */
  selectedUuids?: string[] | null
  displayedRunLabel?: string
  latestRun: KBValidationResult | null
  // Run lifecycle is owned by the parent KBValidationPanel so an in-flight run
  // survives switching away from and back to this tab.
  running: boolean
  activeOptions?: KBValidationRunOptions
  progress?: ValidationProgress | null
  onRetryStatus?: () => void
  error: string | null
  /** ``queryUuids`` is set for a subset run and omitted for the full set. */
  onRun: (mode: KBValidationMode, queryUuids?: string[]) => void
  /** Downloads the displayed run's per-query results. Absent until the run's
   * persisted uuid is known (i.e. before any run has landed this session). */
  onExport?: (format: KBValidationExportFormat) => void | Promise<void>
  /** The system-wide grader the next run will use; null until loaded. */
  onChooseQuestions?: () => void
  grader?: KBValidationGrader | null
}

export function KBValidationRunTab({
  kbReady, canManage, queries, selectedUuids = null, latestRun, displayedRunLabel, running, progress, activeOptions, onRetryStatus, error, onRun, onExport, onChooseQuestions, grader = null,
}: Props) {
  const handed = !!selectedUuids?.length
  // A handed-over selection keeps "Run selected"'s old cost profile (judge
  // only); the full-set default stays the recommended baseline comparison.
  const [mode, setMode] = useState<KBValidationMode>(handed ? 'judge' : 'judge+baseline')
  const [scope, setScope] = useState<QuestionScope>(handed ? 'selected' : 'all')
  const [excluded, setExcluded] = useState<Set<string>>(new Set())
  const [showAllQuestions, setShowAllQuestions] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const batches = useMemo(() => importBatches(queries), [queries])
  const userCount = useMemo(() => queries.filter(q => !q.auto_generated).length, [queries])
  const scoped = useMemo(() => scopeQueries(queries, scope, selectedUuids), [queries, scope, selectedUuids])
  // Chips list every category in the scope, excluded ones included, so an
  // excluded category can be switched back on.
  const scopeCategories = useMemo(() => categoryCounts(scoped), [scoped])
  const selection = useMemo(
    () => resolveRunSelection(queries, scope, selectedUuids, excluded),
    [queries, scope, selectedUuids, excluded],
  )
  const isSubset = selection.queryUuids !== undefined

  const changeScope = (next: QuestionScope) => {
    setScope(next)
    setExcluded(new Set())
  }

  const toggleCategory = (cat: string) => {
    setExcluded(prev => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat); else next.add(cat)
      return next
    })
  }

  const handleRun = () => onRun(mode, selection.queryUuids)

  const toggle = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  const disabled = !kbReady || !canManage || running || !!selection.blockedReason || queries.length === 0
  const n = selection.questions.length
  const answerCount = selection.questions.filter(q => q.expected_answer).length

  return (
    <div>
      {!running && <p style={{ fontSize: 13, color: 'var(--workspace-muted)', lineHeight: 1.6, margin: '0 0 12px' }}>Test questions describe what people should be able to ask this KB. An expected answer gives the grader a reference; expected sources identify where supporting information should come from. Review both before measuring quality.</p>}
      {/* Question set — which questions this run covers */}
      {queries.length > 0 && !running && (
        <div style={{
          padding: '8px 10px', marginBottom: 10,
          backgroundColor: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 6,
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          <label style={{ fontSize: 12, color: 'var(--workspace-muted)', display: 'inline-flex', flexWrap: 'wrap', minWidth: 0, maxWidth: '100%', alignItems: 'center', gap: 6 }}>
            Questions:
            <select
              value={scope}
              onChange={e => changeScope(e.target.value as QuestionScope)}
              disabled={running}
              style={selectStyle}
            >
              <option value="all">All test queries ({queries.length})</option>
              {handed && (
                <option value="selected">Selected on Test Queries ({scopeQueries(queries, 'selected', selectedUuids).length})</option>
              )}
              {batches.map(b => (
                <option key={b.id} value={`batch:${b.id}`}>
                  Imported: {b.label}{b.at ? ` · ${new Date(b.at).toLocaleString()}` : ''} ({b.count})
                </option>
              ))}
              {/* Authorship slices only when the set actually mixes both */}
              {userCount > 0 && userCount < queries.length && (<>
                <option value="user">User-authored ({userCount})</option>
                <option value="auto">Auto-generated ({queries.length - userCount})</option>
              </>)}
            </select>
          </label>

          {scopeCategories.length > 0 && (
            <div role="group" aria-label="Categories to include" style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, color: 'var(--workspace-muted)', marginRight: 2 }}>Categories:</span>
              {scopeCategories.map(([cat, count]) => {
                const on = !excluded.has(cat)
                return (
                  <button
                    key={cat}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleCategory(cat)}
                    disabled={running}
                    title={on ? `Exclude ${cat} questions from this run` : `Include ${cat} questions in this run`}
                    style={{
                      fontFamily: 'inherit', fontSize: 12, fontWeight: 600,
                      padding: '2px 8px', borderRadius: 8, cursor: 'pointer',
                      color: on ? 'var(--workspace-text)' : 'var(--workspace-muted)',
                      backgroundColor: on ? 'var(--workspace-info-surface)' : 'transparent',
                      border: `1px solid ${on ? '#3b82f6' : 'var(--workspace-border)'}`,
                      textDecoration: on ? 'none' : 'line-through',
                    }}
                  >
                    {cat} {count}
                  </button>
                )
              })}
            </div>
          )}

          {/* The final count and distribution, stated before anything runs */}
          <div role="status" style={{ fontSize: 12, color: 'var(--workspace-muted)', lineHeight: 1.5 }}>
            {selection.blockedReason ? (
              <span style={{ color: 'var(--workspace-warning)' }}>{selection.blockedReason}</span>
            ) : (
              <>
                <b style={{ color: 'var(--workspace-text)' }}>{n} {n === 1 ? 'question' : 'questions'}</b> will run
                {n > 0 && (
                  <> — {categoryCounts(selection.questions).map(([c, k]) => `${c} ${k}`).join(' · ')}</>
                )}
                <div style={{ color: isSubset ? 'var(--workspace-warning)' : 'var(--workspace-muted)' }}>
                  {isSubset
                    ? `Subset run (${n} of ${queries.length}): recorded in History as a smoke test and does not change the KB's quality score.`
                    : "Full run: updates the KB's quality score."}
                </div>
              </>
            )}
          </div>
          <details>
            <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--workspace-text)' }}>Preview selected questions ({n})</summary>
            <div role="region" aria-label="Selected question preview" tabIndex={0} style={{ maxHeight: 280, overflowY: 'auto', marginTop: 8, padding: 4 }}>
              <ol style={{ margin: 0, paddingLeft: 22 }}>
                {selection.questions.slice(0, showAllQuestions ? undefined : 20).map(question => <li key={question.uuid} style={{ padding: '8px 0', borderBottom: '1px solid var(--workspace-border)' }}><QuestionExpectations question={question} /></li>)}
              </ol>
              {n > 20 && !showAllQuestions && <button type="button" onClick={() => setShowAllQuestions(true)} style={{ color: 'var(--workspace-text)', background: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', padding: '8px 12px', marginTop: 8, borderRadius: 5 }}>Show all {n} questions</button>}
            </div>
          </details>
          <div style={{ fontSize: 12, color: 'var(--workspace-muted)', lineHeight: 1.6 }}>
            {answerCount} of {n} questions have expected answers for grading.
            {answerCount < n && <div style={{ color: 'var(--workspace-warning)' }}>{n - answerCount} without expected answers will receive retrieval checks but no answer grade. Add expected answers in Test questions to include them.</div>}
            <div>Results describe this test set. A small or narrow sample can miss failures in other questions.</div>
          </div>
        </div>
      )}

      {!running && queries.length > 0 && <div style={{ fontSize: 12, color: 'var(--workspace-muted)', lineHeight: 1.6, marginBottom: 12 }}>
        <p style={{ margin: '0 0 6px' }}>{mode === 'judge+baseline' ? 'The same questions are answered with the KB and with the model alone. Their answer grades show whether the KB adds useful information. This comparison makes additional model calls.' : 'Grades answers produced with this KB against the expected answers. It does not measure how well the model answers without the KB.'}</p>
        <p style={{ margin: '0 0 6px' }}>Retrieval checks compare the sources found with your expected sources; they are separate from grading the answer itself.</p>
        <p style={{ margin: 0 }}>Time depends on the question count, model and queue; a check may take several minutes. It uses model tokens. A cost estimate and per-check spending limit are not available here.</p>
      </div>}

      {/* Run controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={handleRun}
          disabled={disabled}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            color: disabled ? 'var(--workspace-muted)' : 'var(--highlight-text-color, #000)',
            backgroundColor: disabled ? 'var(--workspace-surface)' : 'var(--highlight-color, #eab308)',
            border: '1px solid ' + (disabled ? 'var(--workspace-border)' : 'transparent'),
            borderRadius: 6, cursor: disabled ? 'not-allowed' : 'pointer',
          }}
        >
          {running ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" /> : <Play size={13} aria-hidden="true" />}
          {running ? 'Running…' : queries.length > 0 ? `Run ${n} ${n === 1 ? 'question' : 'questions'}` : 'Run Validation'}
        </button>
        <label style={{ fontSize: 12, color: 'var(--workspace-muted)', display: 'inline-flex', flexWrap: 'wrap', minWidth: 0, maxWidth: '100%', alignItems: 'center', gap: 6 }}>
          Mode:
          <select
            value={running && activeOptions ? activeOptions.skip_judge ? 'retrieval' : activeOptions.mode || mode : mode}
            disabled={running}
            onChange={e => setMode(e.target.value as KBValidationMode)}
            style={selectStyle}
          >
            <option value="judge+baseline">Score vs. no-KB (recommended)</option>
            <option value="judge">Score only</option>
            {running && activeOptions?.skip_judge && <option value="retrieval">Retrieval only</option>}
          </select>
        </label>
        {grader?.model && (
          <span
            data-testid="validation-grader"
            title={
              'Every validation run is graded by one model, set by your administrator in System Config, '
              + 'whoever starts the run. Scores graded by different models are not directly comparable.'
            }
            style={{ fontSize: 12, color: grader.fallback ? 'var(--workspace-warning)' : 'var(--workspace-muted)' }}
          >
            Next check · Graded by {grader.model}
            {grader.fallback
              ? ` — the chosen grader ${grader.fallback.configured} is no longer configured`
              : grader.configured ? '' : ' (default model)'}
          </span>
        )}
      </div>

      {error && (
        <div role="alert" style={{ fontSize: 12, color: 'var(--workspace-danger)', marginBottom: 10 }}>{error}</div>
      )}

      {progress ? (
        <div role={progress.phase === 'failed' ? 'alert' : 'status'} aria-live="polite" style={{ fontSize: 13, lineHeight: 1.6, color: progress.phase === 'failed' ? 'var(--workspace-danger)' : 'var(--workspace-muted)', padding: '12px 0' }}>
          <strong>{progress.phase === 'restoring' ? 'Restoring check' : progress.phase === 'starting' ? 'Submitting check' : progress.phase === 'queued' ? 'Check queued' : progress.phase === 'running' ? 'Checking answers' : progress.phase === 'retrying' ? 'Worker retrying' : progress.phase === 'completed' ? 'Check complete' : progress.phase === 'failed' ? 'Check failed' : 'Connection needs attention'}</strong>
          <div>{progress.message}</div>
          {running && activeOptions && <div>Active check: {activeOptions.skip_judge ? 'retrieval only (no answer grading)' : activeOptions.mode === 'judge+baseline' ? 'answers compared with and without the KB' : 'answer quality'} · {activeOptions.query_uuids ? `${activeOptions.query_uuids.length} selected questions` : 'all test questions'}.</div>}
          {progress.delayed && <div>This is taking longer than usual. You can switch tabs; the same check remains active.</div>}
          {running && <div>Starting another check is disabled until this task has a confirmed outcome.</div>}
          {running && onRetryStatus && <button type="button" onClick={onRetryStatus} style={{ marginTop: 8, padding: '7px 12px', background: 'var(--workspace-surface)', color: 'var(--workspace-text)', border: '1px solid var(--workspace-border)', borderRadius: 5, cursor: 'pointer' }}>Check status / reconnect</button>}
        </div>
      ) : running && (
        <div role="status" style={{ color: 'var(--workspace-muted)', fontSize: 13, padding: '12px 0' }}>Validation running… You can switch tabs; results appear here and in History when finished.</div>
      )}
      {!latestRun ? (!running && (
        <div role="status" style={{ fontSize: 12, color: 'var(--workspace-muted)', padding: '20px 0', textAlign: 'center' }}>
          {queries.length === 0 ? <><strong>No test questions yet</strong><p>Add or generate representative questions and expected answers before measuring quality.</p>{onChooseQuestions && <button type="button" onClick={onChooseQuestions} style={{ padding: '8px 14px', borderRadius: 6, background: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', color: 'var(--workspace-text)', cursor: 'pointer' }}>Set up test questions</button>}</> : <>No validation run yet. Review the selected questions, then run the check.</>}
        </div>
      )) : (
        <div>
          <p style={{ fontSize: 12, color: 'var(--workspace-muted)', overflowWrap: 'anywhere' }}>{displayedRunLabel || 'Saved validation result'}{running && ' · Previous result shown while the new check runs.'}</p>
          <p style={{ fontSize: 12, color: 'var(--workspace-muted)', overflowWrap: 'anywhere', lineHeight: 1.6 }}>Recorded grader: {latestRun.judge_model || 'not recorded'} · Mode: {latestRun.mode || 'not recorded'}{latestRun.answer_model && <> · Answer model: {latestRun.answer_model}</>}</p>
          {/* Export the displayed run for outside-Vandalizer analysis */}
          {onExport && (
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Download size={11} style={{ color: 'var(--workspace-muted)' }} aria-hidden="true" />
              <span style={{ fontSize: 12, color: 'var(--workspace-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Export results
              </span>
              {(['csv', 'xlsx', 'json'] as const).map(f => (
                <ExportButton key={f} format={f} onExport={onExport} />
              ))}
            </div>
          )}

          {latestRun.query_selection && (
            <div
              role="note"
              style={{
                fontSize: 12, color: 'var(--workspace-warning)', padding: '6px 10px', marginBottom: 10,
                backgroundColor: '#f59e0b14', border: '1px solid #f59e0b44', borderRadius: 6,
              }}
            >
              Smoke test over {latestRun.query_selection.selected} of {latestRun.query_selection.total} test
              queries. This score is for those questions only and does not change the KB's quality score.
              The History export for this run holds just these questions.
            </div>
          )}

          {latestRun.judge_model_fallback && (
            <div
              role="note"
              style={{
                fontSize: 12, color: 'var(--workspace-warning)', padding: '6px 10px', marginBottom: 10,
                backgroundColor: '#f59e0b14', border: '1px solid #f59e0b44', borderRadius: 6,
              }}
            >
              Graded by {latestRun.judge_model_fallback.used}, not the chosen grader{' '}
              {latestRun.judge_model_fallback.configured} (no longer in System Config). Compare this
              score only with runs graded by the same model.
            </div>
          )}
          {latestRun.question_set && (
            <div
              style={{ fontSize: 12, color: 'var(--workspace-muted)', marginBottom: 10 }}
              title="Fingerprint of the exact questions, expected answers, categories and source labels this run used. Runs with different fingerprints measured different question sets."
            >
              Question set <code style={{ color: 'var(--workspace-info)' }}>{latestRun.question_set.fingerprint}</code>
              {' · '}{latestRun.question_set.count} {latestRun.question_set.count === 1 ? 'question' : 'questions'}
              {Object.keys(latestRun.question_set.category_counts).length > 0 && (
                <> · {Object.entries(latestRun.question_set.category_counts).map(([c, k]) => `${c} ${k}`).join(' · ')}</>
              )}
            </div>
          )}

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
                    fontSize: 12, fontWeight: 600, padding: '2px 8px', borderRadius: 8,
                    color: discColor(k), backgroundColor: `color-mix(in srgb, ${discColor(k)} 10.2%, transparent)`,
                    border: `1px solid color-mix(in srgb, ${discColor(k)} 33.33%, transparent)`,
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

function ExportButton({ format, onExport }: {
  format: KBValidationExportFormat
  onExport: (format: KBValidationExportFormat) => void | Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const label = format === 'csv' ? 'CSV' : format === 'xlsx' ? 'Excel' : 'JSON'
  const click = async () => {
    setBusy(true)
    try {
      await onExport(format)
    } finally {
      setBusy(false)
    }
  }
  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => void click()}
      style={{
        fontFamily: 'inherit', fontSize: 12, fontWeight: 600,
        padding: '2px 8px', borderRadius: 4,
        color: busy ? 'var(--workspace-muted)' : 'var(--workspace-info)', background: 'transparent',
        border: '1px solid #2e3a52', cursor: busy ? 'wait' : 'pointer',
      }}
    >
      {busy ? '…' : label}
    </button>
  )
}

function CertifiedQualityCard({ run }: { run: KBValidationResult }) {
  if (run.score == null) return null
  const tierColors: Record<string, { border: string; text: string }> = {
    excellent: { border: '#22c55e55', text: 'var(--workspace-success)' },
    good: { border: '#3b82f655', text: 'var(--workspace-info)' },
    fair: { border: '#f59e0b55', text: 'var(--workspace-warning)' },
  }
  const tier = run.quality_tier || null
  const c = (tier && tierColors[tier]) || { border: '#2e3a52', text: 'var(--workspace-muted)' }
  const tierLabel = tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : 'Unrated'
  const bd = run.score_breakdown
  const penalized = !!bd && bd.sample_size_penalty > 0
  const needed = bd?.test_cases_needed ?? 0
  const { components } = explainKBScore(run)
  return (
    <div style={{
      padding: 12, marginBottom: 10, backgroundColor: 'var(--workspace-info-surface)',
      border: `1px solid ${c.border}`, borderRadius: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--workspace-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>Overall quality</span>
        <span style={{ fontSize: 22, fontWeight: 700, color: c.text }}>
          {tierLabel} - {Math.round(run.score)}%
        </span>
      </div>
      {/* The formula is printed, not tucked in a tooltip: this number is a
          composite and was being read as the judge's answer accuracy. */}
      <div style={{ fontSize: 12, color: 'var(--workspace-muted)', lineHeight: 1.6, marginTop: 4 }}>
        A weighted composite, not answer accuracy on its own:{' '}
        {components.map((comp, i) => (
          <span key={comp.key} style={{ whiteSpace: 'nowrap' }}>
            {i > 0 && <span style={{ color: 'var(--workspace-muted)' }}> + </span>}
            <span style={{ color: 'var(--workspace-muted)' }}>{Math.round(comp.weight * 100)}% ×</span>{' '}
            <span style={{ color: comp.key === 'judge' ? 'var(--workspace-success)' : 'var(--workspace-text)' }}>{comp.label}</span>{' '}
            <span style={{ color: 'var(--workspace-text)', fontWeight: 600 }}>{Math.round(comp.value)}%</span>
          </span>
        ))}
      </div>
      {penalized && bd && (
        <div style={{ fontSize: 12, color: 'var(--workspace-warning)', lineHeight: 1.5, marginTop: 4 }}>
          Discounted from a raw {Math.round(bd.raw_score)}% by a sample-size confidence penalty
          ({`-${Math.round(bd.sample_size_penalty)} pts`}).{needed > 0
            ? ` Add at least ${needed} representative test quer${needed > 1 ? 'ies' : 'y'} and rerun to reduce the small-sample penalty. New results may be higher or lower.`
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
  const n = run.retrieval_precision.num_queries_judged

  return (
    <div style={{
      padding: 12, backgroundColor: 'var(--workspace-info-surface)',
      border: '1px solid #2e3a52', borderRadius: 6,
    }}>
      {/* This is the number to use for "how accurate are the answers" — the
          judge's mean score, before it is blended into the overall composite. */}
      <div style={{ fontSize: 12, color: 'var(--workspace-muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
        Answer accuracy — judge score averaged over {n ?? '?'} question{n === 1 ? '' : 's'}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
        {b != null && (
          <Stat label="Without KB" value={b * 100} color="var(--workspace-muted)" />
        )}
        <Stat label="With KB" value={j * 100} color="var(--workspace-success)" />
        {lift != null && (
          <Stat label="Lift" value={lift * 100} color={lift > 0 ? 'var(--workspace-success)' : 'var(--workspace-danger)'} sign />
        )}
        {b != null && (
          <div style={{ flex: 1, minWidth: 200 }}>
            <BarComparison baseline={b} withKb={j} />
          </div>
        )}
      </div>
      {run.retrieval_precision.judge_variance != null && (
        <div style={{ fontSize: 12, color: 'var(--workspace-muted)', marginTop: 6 }}>
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
      <div style={{ fontSize: 12, color: 'var(--workspace-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{display}</div>
    </div>
  )
}

function BarComparison({ baseline, withKb }: { baseline: number; withKb: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <BarRow label="No KB" value={baseline} color="var(--workspace-muted)" />
      <BarRow label="With KB" value={withKb} color="var(--workspace-success)" />
    </div>
  )
}

function BarRow({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--workspace-muted)' }}>
      <div style={{ width: 50 }}>{label}</div>
      <div style={{ flex: 1, height: 6, backgroundColor: 'var(--workspace-surface)', borderRadius: 3, overflow: 'hidden' }}>
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
      backgroundColor: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 6, overflow: 'hidden',
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
        {expanded ? <ChevronDown size={12} style={{ color: 'var(--workspace-muted)' }} aria-hidden="true" /> : <ChevronRight size={12} style={{ color: 'var(--workspace-muted)' }} aria-hidden="true" />}
        <VerdictDot verdict={j?.verdict ?? null} />
        <div style={{ flex: 1, minWidth: 0, fontSize: 13, color: 'var(--workspace-text)', overflowWrap: 'anywhere' }}>
          {detail.query}
        </div>
        {detail.discrimination && detail.discrimination !== 'other' && (
          <span style={{
            fontSize: 9, fontWeight: 600, padding: '1px 6px', borderRadius: 6,
            color: discColor(detail.discrimination),
            backgroundColor: `color-mix(in srgb, ${discColor(detail.discrimination)} 10.2%, transparent)`,
          }}>
            {detail.discrimination}
          </span>
        )}
        {j && (
          <span style={{ fontSize: 12, color: 'var(--workspace-muted)', minWidth: 40, textAlign: 'right' }}>
            {(j.score * 100).toFixed(0)}%
          </span>
        )}
        {hasBaseline && b && (
          <span style={{ fontSize: 12, color: 'var(--workspace-muted)', minWidth: 70, textAlign: 'right' }}>
            (no-KB: {(b.score * 100).toFixed(0)}%)
          </span>
        )}
      </button>
      {expanded && (
        <div style={{ padding: '8px 12px 12px 32px', borderTop: '1px solid var(--workspace-border)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {detail.generation_truncated && (
            <TruncationNote what="The with-KB answer" />
          )}
          <Block label="Expected answer" body={detail.expected_answer || 'No expected answer was saved with this run.'} />
          {detail.expected_sources && detail.expected_sources.length > 0 && (
            <Block label="Expected sources" body={detail.expected_sources.join(', ')} />
          )}
          {detail.actual_answer && (
            <Block
              label={detail.actual_answer_truncated ? 'With-KB answer (stored text cut; judge saw the full answer)' : 'With-KB answer'}
              body={detail.actual_answer}
            />
          )}
          {hasBaseline && detail.baseline_generation_truncated && (
            <TruncationNote what="The baseline answer" />
          )}
          {hasBaseline && detail.baseline_answer && (
            <Block
              label={detail.baseline_answer_truncated ? 'Baseline answer (no KB; stored text cut)' : 'Baseline answer (no KB)'}
              body={detail.baseline_answer}
            />
          )}
          {j?.reasoning && (
            <Block label="Judge reasoning" body={j.reasoning} muted />
          )}
          {(j?.missing_facts.length ?? 0) > 0 && (
            <div style={{ fontSize: 12, color: 'var(--workspace-warning)' }}>
              <b>Missing:</b> {j!.missing_facts.join(' · ')}
            </div>
          )}
          {(j?.hallucinated_facts.length ?? 0) > 0 && (
            <div style={{ fontSize: 12, color: 'var(--workspace-danger)' }}>
              <b>Hallucinated:</b> {j!.hallucinated_facts.join(' · ')}
            </div>
          )}
          {detail.retrieved_sources && detail.retrieved_sources.length > 0 && (
            <div style={{ fontSize: 12, color: 'var(--workspace-muted)' }}>
              Retrieved: {detail.retrieved_sources.join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TruncationNote({ what }: { what: string }) {
  // Regular users cannot open Admin → System Config, so the remedy that lives
  // there is shown to admins only; everyone else gets the fix they can make.
  const isAdmin = useIsAdmin()
  return (
    <div style={{ fontSize: 12, color: 'var(--workspace-warning)' }} role="note">
      {what} stopped at the model&apos;s output limit, so the judge scored an incomplete answer.
      {' '}Shorter or more focused test queries fit within the limit.
      {isAdmin && ' As an admin, you can also raise “Response reserve (output tokens)” for this model under Admin → System Config → Models.'}
    </div>
  )
}

function Block({ label, body, muted = false }: { label: string; body: string; muted?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--workspace-muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 12, color: muted ? 'var(--workspace-muted)' : 'var(--workspace-text)', whiteSpace: 'pre-wrap' as const, lineHeight: 1.5 }}>
        {body}
      </div>
    </div>
  )
}

function VerdictDot({ verdict }: { verdict: string | null }) {
  const c = verdict === 'PASS' ? 'var(--workspace-success)' : verdict === 'WARN' ? 'var(--workspace-warning)' : verdict === 'FAIL' ? 'var(--workspace-danger)' : 'var(--workspace-muted)'
  return (
    <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: c, flexShrink: 0 }} />
  )
}

function discColor(d: string) {
  if (d === 'useful') return 'var(--workspace-success)'
  if (d === 'redundant') return 'var(--workspace-muted)'
  if (d === 'failing') return 'var(--workspace-danger)'
  return 'var(--workspace-muted)'
}

const selectStyle: React.CSSProperties = {
  background: 'var(--workspace-canvas)', color: 'var(--workspace-text)', border: '1px solid var(--workspace-border)',
  borderRadius: 4, padding: '3px 6px', fontSize: 12, fontFamily: 'inherit',
  maxWidth: '100%', minWidth: 0,
}
