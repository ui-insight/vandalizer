import { useEffect, useState } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import {
  formatBudgetEstimate,
  generateKBTestQueriesAndWait,
  getKBBaselineProbe,
  getKBValidationGrader,
  type KBValidationGrader,
  listKBTestQueries,
  updateKBTestQuery,
  deleteKBTestQuery,
  type KBTestQuery,
  type StartOptimizationOptions,
  type OptimizationCoverage,
  type TestSetBuildMode,
} from '../../api/knowledge'
import {
  QueryFormFields,
  queryToDraft,
  draftToUpdatePayload,
  EMPTY_DRAFT,
  type DraftShape,
} from './KBTestQueriesTab'
import { getUserConfig } from '../../api/config'
import type { ModelInfo } from '../../types/workflow'
import { Toggle, Radio } from '../shared/Toggle'
import { BudgetTierPicker } from '../shared/BudgetTierPicker'
import { KB_BUDGET_TIERS } from '../shared/budgetTiers'
import { AutovalidateWizard, type WizardStep } from '../shared/AutovalidateWizard'
import { WizardLoadingStep } from '../shared/WizardLoadingStep'
import { recommendLevel, recommendationReason } from '../shared/baselineRecommendation'
import { TermDef } from '../shared/TermDef'
import { QuestionExpectations } from './QuestionExpectations'
import { useConfirm } from '../shared/useConfirm'

interface Props {
  kbUuid: string
  onConfirm: (opts: StartOptimizationOptions) => void
  onClose: () => void
  /** Routes the user to the Test Queries tab when they want to write/edit
   * their own questions instead of using the auto-generated set. */
  onSwitchToQueries?: () => void
}

type Tier = typeof KB_BUDGET_TIERS[number]['id'] | 'custom'

interface KBWizardOptions {
  tier: Tier
  customTokens: number
  coverage: OptimizationCoverage
  /** How the eval set is built: reuse saved questions, generate fresh, or both. */
  testSetMode: TestSetBuildMode
  applyOnFinish: boolean
  /** Persisted from PreviewStep — feeds BaselineStep so the probe runs on the
   * same questions the user just reviewed. */
  sampleQueryIds: string[]
  /** Populated by BaselineStep — drives the Budget step's recommended tier. */
  noKbScore: number | null
  /** Computed in BaselineStep from ``noKbScore``. Null until the probe completes. */
  recommendedTier: Tier | null
}

const INITIAL_OPTIONS: KBWizardOptions = {
  tier: 'standard',
  customTokens: 1_000_000,
  coverage: 'standard',
  // Default to reusing saved questions; the Test-set step flips this to
  // 'generate' automatically when the KB has none yet.
  testSetMode: 'existing',
  applyOnFinish: false,
  sampleQueryIds: [],
  noKbScore: null,
  recommendedTier: null,
}

export function AutovalidateModal({ kbUuid, onConfirm, onClose, onSwitchToQueries }: Props) {
  // The user's resolved model (incl. cost_per_1m_*) — drives the dollar-cost
  // display when admins have populated those fields. Tokens-only fallback.
  const [grader, setGrader] = useState<KBValidationGrader | null>(null)
  const [userModel, setUserModel] = useState<ModelInfo | null>(null)

  useEffect(() => {
    void getKBValidationGrader(kbUuid).then(setGrader).catch(() => {})
    getUserConfig().then(cfg => {
      const target = cfg.model
      const match = cfg.available_models.find(m => m.tag === target || m.name === target)
        || cfg.available_models[0]
        || null
      setUserModel(match)
    }).catch(() => { /* silent fallback to tokens-only */ })
  }, [kbUuid])

  const tokensFor = (opts: KBWizardOptions): number =>
    opts.tier === 'custom'
      ? opts.customTokens
      : (KB_BUDGET_TIERS.find(t => t.id === opts.tier)?.tokens ?? 0)

  const steps: WizardStep<KBWizardOptions>[] = [
    {
      id: 'testset',
      label: 'Questions',
      render: (opts, set) => (
        <TestSetStep
          kbUuid={kbUuid}
          mode={opts.testSetMode}
          coverage={opts.coverage}
          // Changing how the set is built invalidates the previously reviewed
          // set and the baseline measured on it — clear both so Preview and
          // Baseline rebuild for the new selection.
          onModeChange={(m) => set(o => ({ ...o, testSetMode: m, sampleQueryIds: [], noKbScore: null }))}
          onCoverageChange={(c) => set(o => ({ ...o, coverage: c, sampleQueryIds: [], noKbScore: null }))}
          onSwitchToQueries={onSwitchToQueries}
          onClose={onClose}
        />
      ),
    },
    {
      id: 'preview',
      label: 'Review questions',
      render: (opts, set) => (
        <PreviewStep
          kbUuid={kbUuid}
          buildMode={opts.testSetMode}
          coverage={opts.coverage}
          sampleQueryIds={opts.sampleQueryIds}
          onReady={(ids) => set(o => ({ ...o, sampleQueryIds: ids }))}
          onSwitchToQueries={onSwitchToQueries}
          onClose={onClose}
        />
      ),
      canAdvance: (o) => o.sampleQueryIds.length > 0,
    },
    {
      id: 'baseline',
      label: 'Compare without KB',
      render: (opts, set) => (
        <BaselineStep
          kbUuid={kbUuid}
          sampleQueryIds={opts.sampleQueryIds}
          noKbScore={opts.noKbScore}
          recommendedTier={opts.recommendedTier}
          onReady={(score, tier) => set(o => ({
            ...o,
            noKbScore: score,
            recommendedTier: tier,
            tier: o.tier === 'standard' && tier ? tier : o.tier,
          }))}
        />
      ),
      canAdvance: (o) => o.noKbScore != null || o.recommendedTier != null,
    },
    {
      id: 'budget',
      label: 'Budget & review',
      render: (opts, set) => {
        const tokens = tokensFor(opts)
        const { tokens_label, cost_label } = formatBudgetEstimate(tokens, userModel)
        return (
          <>
          <BudgetTierPicker
            tiers={KB_BUDGET_TIERS}
            selected={opts.tier}
            onSelect={(id) => set(o => ({ ...o, tier: id as Tier }))}
            customTokens={opts.customTokens}
            onCustomTokens={(n) => set(o => ({ ...o, customTokens: n }))}
            tokensLabel={tokens_label}
            costLabel={cost_label}
            formatTierRow={(t) => {
              const { tokens_label, cost_label } = formatBudgetEstimate(t.tokens, userModel)
              return { tokensLabel: tokens_label, costLabel: cost_label }
            }}
            recommendedTierId={opts.recommendedTier ?? undefined}
            recommendationReason={recommendationReason(opts.noKbScore, { withoutLabel: 'without the KB' })}
            description="Each candidate uses model tokens. Choose a spending limit for this experiment. More trials may help, but results depend on your test questions and are not guaranteed."
          />
          <p style={{ fontSize: 'var(--workspace-font-control)', lineHeight: 1.6, color: 'var(--workspace-text)', marginTop: 16 }}>{opts.sampleQueryIds.length} reviewed questions · {tokens_label}{cost_label ? ` · ${cost_label}` : ' · Dollar estimate unavailable for this model'}. You review the results before applying changes unless you enable automatic application below.</p>
          <p style={{ fontSize: 'var(--workspace-font-control)', lineHeight: 1.6, color: 'var(--workspace-text)' }}>Grader: {grader?.model || 'details unavailable'}. Time: {KB_BUDGET_TIERS.find(t => t.id === opts.tier)?.timeEstimate || 'no estimate for a custom budget'}{opts.tier !== 'custom' && ' (approximate)'}. Queue, models and question length affect duration. Results cover this reviewed test set; more trials do not guarantee improvement.</p>
          <details style={{ marginTop: 16, color: 'var(--workspace-text)', fontSize: 'var(--workspace-font-control)' }}><summary style={{ cursor: 'pointer' }}>Optional settings</summary><AdvancedStep applyOnFinish={opts.applyOnFinish} onApplyOnFinish={b => set(o => ({ ...o, applyOnFinish: b }))} tokensLabel={tokens_label} costLabel={cost_label} /></details>
          </>
        )
      },
    },
  ]

  const handleConfirm = (opts: KBWizardOptions) => {
    onConfirm({
      token_budget: tokensFor(opts),
      apply_on_finish: opts.applyOnFinish,
      autogen_coverage: opts.coverage,
      include_indexing_track: false,
      test_set_build_mode: opts.testSetMode,
      // The exact set the user reviewed in Preview — makes the run grade against
      // precisely these questions regardless of what else is saved on the KB.
      test_query_uuids: opts.sampleQueryIds,
    })
  }

  const confirmLabel = (opts: KBWizardOptions): string => {
    const tokens = tokensFor(opts)
    const { cost_label } = formatBudgetEstimate(tokens, userModel)
    const tier = KB_BUDGET_TIERS.find(t => t.id === opts.tier)
    const time = tier?.timeEstimate
    const parts: string[] = []
    if (cost_label) parts.push(cost_label)
    if (time) parts.push(`~${time}`)
    return parts.length > 0 ? `Validate & improve: ${parts.join(', ')}` : 'Validate & improve'
  }

  return (
    <AutovalidateWizard<KBWizardOptions>
      steps={steps}
      initialOptions={INITIAL_OPTIONS}
      onConfirm={handleConfirm}
      onClose={onClose}
      title="Improve retrieval"
      confirmLabel={confirmLabel}
    />
  )
}

const COVERAGE_COUNTS: Record<OptimizationCoverage, number> = { quick: 5, standard: 10, exhaustive: 25 }

function TestSetStep({
  kbUuid, mode, coverage, onModeChange, onCoverageChange, onSwitchToQueries, onClose,
}: {
  kbUuid: string
  mode: TestSetBuildMode
  coverage: OptimizationCoverage
  onModeChange: (m: TestSetBuildMode) => void
  onCoverageChange: (c: OptimizationCoverage) => void
  onSwitchToQueries?: () => void
  onClose: () => void
}) {
  const [showExample, setShowExample] = useState(false)
  // Live count of saved questions — decides which modes are available and
  // drives the "9 saved + 25 new = 34" math. Null while still loading.
  const [existingCount, setExistingCount] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    listKBTestQueries(kbUuid)
      .then(out => {
        if (cancelled) return
        const n = out.test_queries.length
        setExistingCount(n)
        // With no saved questions, "use saved" and "combine" aren't possible —
        // fall back to generating a fresh set.
        if (n === 0 && mode !== 'generate') onModeChange('generate')
      })
      .catch(() => { if (!cancelled) setExistingCount(0) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbUuid])

  const hasExisting = (existingCount ?? 0) > 0
  const genCount = COVERAGE_COUNTS[coverage]
  const showCoverage = mode === 'generate' || mode === 'combined'

  const MODES: { id: TestSetBuildMode; title: string; sub: string; disabled: boolean }[] = [
    {
      id: 'existing',
      title: 'Use my saved questions',
      sub: existingCount == null
        ? 'Reuse the test questions already on this KB.'
        : `Grade against your ${existingCount} saved question${existingCount === 1 ? '' : 's'}.`,
      disabled: !hasExisting,
    },
    {
      id: 'generate',
      title: 'Generate new questions',
      sub: `Write a fresh set from your documents (up to ${genCount}).`,
      disabled: false,
    },
    {
      id: 'combined',
      title: 'Combine saved + generated',
      sub: hasExisting && existingCount != null
        ? `${existingCount} saved + up to ${genCount} new = up to ${existingCount + genCount} questions.`
        : 'Keep your saved questions and add freshly generated ones.',
      disabled: !hasExisting,
    },
  ]

  return (
    <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>How should we build the test set?</h4>
      <p style={{ margin: '0 0 12px 0', color: 'var(--workspace-muted)' }}>
        Test questions represent what people should be able to ask. Expected answers give the grader a reference; expected sources identify the supporting information. Tuning compares settings against this test set. <b>Review generated questions and their expectations before continuing</b>.
      </p>
      <button
        type="button"
        onClick={() => setShowExample(v => !v)}
        style={{
          marginBottom: 10, padding: 0, background: 'transparent', border: 'none',
          color: 'var(--workspace-accent-ink)', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
          cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4,
        }}
        aria-expanded={showExample}
      >
        {showExample ? '▾' : '▸'} See an example test question
      </button>
      {showExample && (
        <div style={{
          padding: '8px 10px', marginBottom: 10,
          background: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)', borderRadius: 6,
          fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-text)', lineHeight: 1.6,
        }}>
          <div><span style={{ color: 'var(--workspace-muted)' }}>Question:</span> Who is the principal investigator on the Reed grant?</div>
          <div style={{ marginTop: 4 }}><span style={{ color: 'var(--workspace-muted)' }}>Expected answer:</span> Dr. Maria Reed</div>
          <div style={{ marginTop: 6, fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
            The grader compares the AI's answer with this reference. Check that the expected answer is correct and supported by a source.
          </div>
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {MODES.map(m => {
          const active = mode === m.id
          return (
            <button
              key={m.id}
              onClick={() => !m.disabled && onModeChange(m.id)}
              disabled={m.disabled}
              title={m.disabled ? 'No saved questions on this KB yet.' : undefined}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 12px', textAlign: 'left',
                backgroundColor: active ? 'color-mix(in srgb, var(--highlight-color, #eab308) 12%, transparent)' : 'var(--workspace-surface)',
                border: '1px solid ' + (active ? 'var(--highlight-color, #eab308)' : 'var(--workspace-border)'),
                borderRadius: 6, cursor: m.disabled ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit', color: m.disabled ? 'var(--workspace-muted)' : 'var(--workspace-text)',
                opacity: m.disabled ? 0.6 : 1,
              }}
            >
              <Radio active={active} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 'var(--workspace-font-meta)', fontWeight: 600 }}>{m.title}</div>
                <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>{m.sub}</div>
              </div>
            </button>
          )
        })}
      </div>

      {showCoverage && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', marginBottom: 6 }}>How many new questions to generate:</div>
          <div style={{ display: 'flex', gap: 6 }}>
            {(['quick', 'standard', 'exhaustive'] as const).map(c => {
              const active = coverage === c
              return (
                <button
                  key={c}
                  onClick={() => onCoverageChange(c)}
                  style={{
                    flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
                    padding: '6px 8px', textAlign: 'center',
                    backgroundColor: active ? 'color-mix(in srgb, var(--highlight-color, #eab308) 12%, transparent)' : 'var(--workspace-surface)',
                    border: '1px solid ' + (active ? 'var(--highlight-color, #eab308)' : 'var(--workspace-border)'),
                    borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', color: 'var(--workspace-text)',
                  }}
                >
                  <span style={{ fontSize: 'var(--workspace-font-meta)', fontWeight: 600, textTransform: 'capitalize' }}>{c}</span>
                  <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>up to {COVERAGE_COUNTS[c]}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {showCoverage && (
        <p style={{ marginTop: 10, fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
          Generated queries are saved to this KB, so future re-runs can reuse them.
        </p>
      )}
      {onSwitchToQueries && (
        <button
          onClick={() => { onClose(); onSwitchToQueries() }}
          style={{
            marginTop: 8, fontSize: 'var(--workspace-font-meta)', fontFamily: 'inherit',
            background: 'transparent', border: 'none', padding: 0,
            color: 'var(--workspace-accent-ink)', cursor: 'pointer',
            textDecoration: 'underline dotted', textUnderlineOffset: 2,
          }}
        >
          I'd rather write my own first →
        </button>
      )}
    </div>
  )
}

function PreviewStep({
  kbUuid, buildMode, coverage, sampleQueryIds, onReady, onSwitchToQueries, onClose,
}: {
  kbUuid: string
  buildMode: TestSetBuildMode
  coverage: OptimizationCoverage
  sampleQueryIds: string[]
  onReady: (ids: string[]) => void
  onSwitchToQueries?: () => void
  onClose: () => void
}) {
  // States: 'loading' (fetching existing and/or generating), 'preview' (have
  // queries), or 'error'. ``composition`` records how many of the reviewed
  // questions were saved vs freshly generated, for the heading + combine math.
  const [queries, setQueries] = useState<KBTestQuery[]>([])
  const [composition, setComposition] = useState<{ existing: number; generated: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  // Inline edit state for fixing a generated/saved question without leaving the
  // wizard. `editingUuid` selects which card shows the edit form.
  const [editingUuid, setEditingUuid] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<DraftShape>(EMPTY_DRAFT)
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const confirm = useConfirm()

  const startEdit = (q: KBTestQuery) => {
    setActionError(null)
    setEditingUuid(q.uuid)
    setEditDraft(queryToDraft(q))
  }

  const handleUpdate = async () => {
    if (!editingUuid || !editDraft.query.trim()) return
    setSaving(true)
    setActionError(null)
    try {
      const updated = await updateKBTestQuery(kbUuid, editingUuid, draftToUpdatePayload(editDraft))
      setQueries(qs => qs.map(q => (q.uuid === updated.uuid ? updated : q)))
      setEditingUuid(null)
    } catch (e) {
      setActionError((e as Error).message || 'Failed to save changes.')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (q: KBTestQuery) => {
    if (!(await confirm({
      title: 'Remove test question?',
      message: (
        <>
          Remove this test question?
          <br /><br />
          "{q.query}"
        </>
      ),
      confirmLabel: 'Remove',
      destructive: true,
    }))) return
    setActionError(null)
    try {
      await deleteKBTestQuery(kbUuid, q.uuid)
      const next = queries.filter(x => x.uuid !== q.uuid)
      setQueries(next)
      if (editingUuid === q.uuid) setEditingUuid(null)
      // Keep downstream steps (baseline probe, tuning) scoped to the surviving set.
      onReady(next.map(x => x.uuid))
    } catch (e) {
      setActionError((e as Error).message || 'Failed to remove question.')
    }
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        // Revisiting the step (mode/coverage unchanged) — reuse the exact set we
        // already built and reviewed instead of generating a second batch. The
        // wizard clears ``sampleQueryIds`` whenever mode or coverage changes, so
        // a non-empty list here means "same selection as before".
        if (sampleQueryIds.length > 0) {
          const all = await listKBTestQueries(kbUuid)
          if (cancelled) return
          const chosen = all.test_queries.filter(q => sampleQueryIds.includes(q.uuid))
          if (chosen.length > 0) {
            setQueries(chosen)
            onReady(chosen.map(q => q.uuid))
            setLoading(false)
            return
          }
        }

        let existingQs: KBTestQuery[] = []
        if (buildMode === 'existing' || buildMode === 'combined') {
          const existing = await listKBTestQueries(kbUuid)
          if (cancelled) return
          existingQs = existing.test_queries
        }

        let generatedQs: KBTestQuery[] = []
        if (buildMode === 'generate' || buildMode === 'combined') {
          // Runs on a background worker and polls for completion, so the wizard
          // doesn't 502 when the inline LLM call would outlast the gateway.
          const generated = await generateKBTestQueriesAndWait(kbUuid, { coverage })
          if (cancelled) return
          generatedQs = generated.test_queries
        }

        // De-dupe in case generation echoed back an already-saved question.
        const seen = new Set(existingQs.map(q => q.uuid))
        const merged = [...existingQs, ...generatedQs.filter(q => !seen.has(q.uuid))]
        setQueries(merged)
        setComposition({ existing: existingQs.length, generated: merged.length - existingQs.length })
        onReady(merged.map(q => q.uuid))
      } catch (e) {
        if (!cancelled) setError((e as Error).message || 'Failed to load test questions.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbUuid, buildMode, coverage, attempt])

  const willGenerate = sampleQueryIds.length === 0 && (buildMode === 'generate' || buildMode === 'combined')
  if (loading) {
    return (
      <WizardLoadingStep
        message={willGenerate ? 'Writing test questions from your documents…' : 'Loading your test questions…'}
        sub="This usually takes 15–45 seconds."
      />
    )
  }
  if (error) {
    return (
      <WizardLoadingStep
        message="Couldn't load test questions"
        error={error}
        onRetry={() => setAttempt(a => a + 1)}
      />
    )
  }

  const heading = buildMode === 'existing'
    ? 'Your saved test questions'
    : buildMode === 'combined'
      ? 'Your test set'
      : 'Generated test questions'

  return (
    <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>{heading}</h4>
      <p style={{ margin: '0 0 10px 0', color: 'var(--workspace-muted)' }}>
        {buildMode === 'existing' ? (
          <>We'll grade each tuning trial against these <b>{queries.length}</b> questions using a <TermDef term="judge">judge</TermDef>.</>
        ) : (
          <>Tuning quality depends on these. Scan them and fix anything that looks off: edit or remove a question right here before continuing.</>
        )}
      </p>
      {buildMode === 'combined' && composition && composition.generated > 0 && (
        <div style={{ margin: '0 0 10px 0', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-accent-ink)' }}>
          {composition.existing} saved + {composition.generated} generated = <b>{queries.length}</b> total
        </div>
      )}
      {actionError && (
        <div style={{ margin: '0 0 8px 0', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-danger)' }}>{actionError}</div>
      )}
      <div role="region" aria-label="Questions and expectations" tabIndex={0} style={{
        display: 'flex', flexDirection: 'column', gap: 6,
        maxHeight: 260, overflowY: 'auto',
        padding: 8, backgroundColor: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)', borderRadius: 6,
      }}>
        {queries.map((q, i) => (
          <div key={q.uuid} style={{
            padding: '6px 8px', backgroundColor: 'var(--workspace-surface)', borderRadius: 4,
            fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-text)',
          }}>
            {editingUuid === q.uuid ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <QueryFormFields draft={editDraft} onChange={setEditDraft} />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={handleUpdate}
                    disabled={saving || !editDraft.query.trim()}
                    style={{
                      fontSize: 'var(--workspace-font-meta)', fontFamily: 'inherit', padding: '4px 10px', borderRadius: 5,
                      border: '1px solid #15803d55', backgroundColor: '#15803d1a',
                      color: saving || !editDraft.query.trim() ? 'var(--workspace-muted)' : 'var(--workspace-text)',
                      cursor: saving || !editDraft.query.trim() ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                  <button
                    onClick={() => setEditingUuid(null)}
                    style={{
                      fontSize: 'var(--workspace-font-meta)', fontFamily: 'inherit', padding: '4px 10px', borderRadius: 5,
                      border: '1px solid var(--workspace-border)', backgroundColor: 'var(--workspace-surface)', color: 'var(--workspace-text)', cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <span style={{ color: 'var(--workspace-muted)', fontSize: 'var(--workspace-font-meta)', marginTop: 1 }}>{i + 1}.</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <QuestionExpectations question={q} />
                </div>
                <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
                  <button
                    type="button"
                    aria-label="Edit question"
                    onClick={() => startEdit(q)}
                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: 'var(--workspace-muted)' }}
                    title="Edit question"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    type="button"
                    aria-label="Remove question"
                    onClick={() => handleDelete(q)}
                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: 'var(--workspace-muted)' }}
                    title="Remove question"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
        {queries.length === 0 && (
          <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', padding: '4px 8px' }}>
            No test questions left. Add some on the Test Queries tab before tuning.
          </div>
        )}
      </div>
      {onSwitchToQueries && (
        <button
          onClick={() => { onClose(); onSwitchToQueries() }}
          style={{
            marginTop: 10, fontSize: 'var(--workspace-font-meta)', fontFamily: 'inherit',
            background: 'transparent', border: 'none', padding: 0,
            color: 'var(--workspace-accent-ink)', cursor: 'pointer',
            textDecoration: 'underline dotted', textUnderlineOffset: 2,
          }}
        >
          Open the full Test Queries tab →
        </button>
      )}
    </div>
  )
}

function BaselineStep({
  kbUuid, sampleQueryIds, noKbScore, recommendedTier, onReady,
}: {
  kbUuid: string
  sampleQueryIds: string[]
  noKbScore: number | null
  recommendedTier: Tier | null
  onReady: (score: number | null, tier: Tier | null) => void
}) {
  const [loading, setLoading] = useState(noKbScore == null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [whyOpen, setWhyOpen] = useState(false)

  useEffect(() => {
    if (noKbScore != null) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const sample = sampleQueryIds.slice(0, 5)
        const result = await getKBBaselineProbe(kbUuid, {
          query_uuids: sample.length > 0 ? sample : undefined,
          sample_size: 5,
        })
        if (cancelled) return
        const score = result.no_kb_score
        const tier = recommendTier(score)
        onReady(score, tier)
      } catch (e) {
        if (!cancelled) setError((e as Error).message || 'Failed to measure the no-KB baseline.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbUuid, attempt])

  if (loading) {
    return (
      <WizardLoadingStep
        message="Measuring the no-KB baseline…"
        sub="Asking up to five reviewed questions without KB retrieval. This uses model tokens and may take a few minutes."
      />
    )
  }
  if (error) {
    return (
      <WizardLoadingStep
        message="Couldn't measure the baseline"
        error={error}
        onRetry={() => setAttempt(a => a + 1)}
        // Seed a benign tier on skip so the wizard's canAdvance gate passes;
        // user keeps the standard default and the run measures baselines itself.
        onSkip={() => onReady(null, 'standard')}
        skipLabel="Skip and continue"
      />
    )
  }

  // No score (no queries with expected_answer) — give the user a path forward.
  if (noKbScore == null) {
    return (
      <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)', lineHeight: 1.5 }}>
        <h4 style={{ margin: '0 0 8px 0', fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>Baseline skipped</h4>
        <p style={{ margin: '0 0 10px 0', color: 'var(--workspace-muted)' }}>
          We couldn't measure a no-KB <TermDef term="baseline">baseline</TermDef> because none of your test questions have an expected answer yet. Tuning will still measure baselines during the run.
        </p>
      </div>
    )
  }

  const scorePct = Math.round(noKbScore * 100)
  return (
    <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>How well the model does without your KB</h4>
      <div style={{
        padding: '14px 16px', marginBottom: 10,
        backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, transparent)',
        border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, transparent)', borderRadius: 6,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ fontSize: 28, fontWeight: 700, color: 'var(--workspace-text)' }}>{scorePct}%</span>
          <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
            average answer grade on a sample of up to five questions <i>without</i> the knowledge base
          </span>
        </div>
        <div style={{ marginTop: 8, fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-text)' }}>
          {scorePct >= 85
            ? <>The model scored well on this small sample without the KB. There may be limited room to improve these questions; other questions can behave differently.</>
            : scorePct >= 60
              ? <>Some sampled answers need improvement. The full comparison will test whether this KB helps.</>
              : <>The model scored poorly on this sample without the KB. The comparison will test whether KB retrieval improves those answers; improvement is not guaranteed.</>}
        </div>
      </div>
      <button
        onClick={() => setWhyOpen(v => !v)}
        style={{
          background: 'transparent', border: 'none', padding: 0,
          fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', fontFamily: 'inherit', cursor: 'pointer',
          textDecoration: 'underline dotted', textUnderlineOffset: 2,
        }}
      >
        {whyOpen ? '▴' : '▾'} Why does this matter?
      </button>
      {whyOpen && (
        <div style={{
          marginTop: 8, padding: '8px 10px', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.5,
          backgroundColor: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)', borderRadius: 6,
        }}>
          This asks the same questions without retrieving KB sources, then grades the answers against your expectations. Comparing those grades with KB-assisted answers helps measure the KB's contribution. Retrieval checks measure which sources were found; answer grades measure what the model said. This small sample guides a budget suggestion and does not establish performance on all your questions.
        </div>
      )}
      {recommendedTier && (
        <div style={{ marginTop: 10, fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-accent-ink)' }}>
          Suggested budget: <b style={{ textTransform: 'capitalize' }}>{recommendedTier}</b>{' '}
          (you can change this on the next step).
        </div>
      )}
    </div>
  )
}

function recommendTier(noKbScore: number | null): Tier {
  // Map the abstract level to KB's tier IDs.
  return recommendLevel(noKbScore) === 'small' ? 'conservative' : 'standard'
}

function AdvancedStep({
  applyOnFinish, onApplyOnFinish, tokensLabel, costLabel,
}: {
  applyOnFinish: boolean
  onApplyOnFinish: (b: boolean) => void
  tokensLabel: string
  costLabel: string | null
}) {
  return (
    <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>Advanced options</h4>
      <Toggle
        label="Apply optimized settings automatically when finished"
        description="If unchecked, we'll show you the results and you can apply them manually."
        checked={applyOnFinish}
        onChange={onApplyOnFinish}
      />
      <div style={{
        marginTop: 16, padding: '10px 12px',
        backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, transparent)',
        border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, transparent)', borderRadius: 6,
      }}>
        <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-accent-ink)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
          Ready to start
        </div>
        <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>
          Budget: <b>{tokensLabel}</b>{costLabel && <> · <b>{costLabel}</b></>}
        </div>
      </div>
    </div>
  )
}
