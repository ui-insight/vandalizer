import { useEffect, useState } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import {
  formatBudgetEstimate,
  generateKBTestQueries,
  getKBBaselineProbe,
  listKBTestQueries,
  updateKBTestQuery,
  deleteKBTestQuery,
  type KBTestQuery,
  type StartOptimizationOptions,
  type OptimizationCoverage,
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
  applyOnFinish: false,
  sampleQueryIds: [],
  noKbScore: null,
  recommendedTier: null,
}

export function AutovalidateModal({ kbUuid, onConfirm, onClose, onSwitchToQueries }: Props) {
  // The user's resolved model (incl. cost_per_1m_*) — drives the dollar-cost
  // display when admins have populated those fields. Tokens-only fallback.
  const [userModel, setUserModel] = useState<ModelInfo | null>(null)

  useEffect(() => {
    getUserConfig().then(cfg => {
      const target = cfg.model
      const match = cfg.available_models.find(m => m.tag === target || m.name === target)
        || cfg.available_models[0]
        || null
      setUserModel(match)
    }).catch(() => { /* silent fallback to tokens-only */ })
  }, [])

  const tokensFor = (opts: KBWizardOptions): number =>
    opts.tier === 'custom'
      ? opts.customTokens
      : (KB_BUDGET_TIERS.find(t => t.id === opts.tier)?.tokens ?? 0)

  const steps: WizardStep<KBWizardOptions>[] = [
    {
      id: 'concept',
      label: 'Concept',
      render: () => <ConceptStep />,
    },
    {
      id: 'testset',
      label: 'Test set',
      render: (opts, set) => (
        <TestSetStep
          coverage={opts.coverage}
          onChange={(c) => set(o => ({ ...o, coverage: c }))}
          onSwitchToQueries={onSwitchToQueries}
          onClose={onClose}
        />
      ),
    },
    {
      id: 'preview',
      label: 'Preview',
      render: (opts, set) => (
        <PreviewStep
          kbUuid={kbUuid}
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
      label: 'Baseline',
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
      label: 'Budget',
      render: (opts, set) => {
        const tokens = tokensFor(opts)
        const { tokens_label, cost_label } = formatBudgetEstimate(tokens, userModel)
        return (
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
            description="Each setup costs LLM tokens to test. Conservative is enough to confirm whether tuning helps at all; Standard finds a confident winner for most KBs; Thorough is for KBs you'll rely on for months."
          />
        )
      },
    },
    {
      id: 'advanced',
      label: 'Advanced',
      render: (opts, set) => {
        const tokens = tokensFor(opts)
        const { tokens_label, cost_label } = formatBudgetEstimate(tokens, userModel)
        return (
          <AdvancedStep
            applyOnFinish={opts.applyOnFinish}
            onApplyOnFinish={(b) => set(o => ({ ...o, applyOnFinish: b }))}
            tokensLabel={tokens_label}
            costLabel={cost_label}
          />
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
    return parts.length > 0 ? `Start tuning — ${parts.join(', ')}` : 'Start tuning'
  }

  return (
    <AutovalidateWizard<KBWizardOptions>
      steps={steps}
      initialOptions={INITIAL_OPTIONS}
      onConfirm={handleConfirm}
      onClose={onClose}
      title="Tune your knowledge base"
      confirmLabel={confirmLabel}
    />
  )
}

function ConceptStep() {
  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.6 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>What is tuning?</h4>
      <p style={{ margin: '0 0 10px 0' }}>
        We try many ways of using your knowledge base — different retrieval
        settings, prompts, and models — and keep whichever combination answers
        your test questions best. Another AI — the{' '}
        <TermDef term="judge">judge</TermDef> — grades each answer against the{' '}
        <TermDef term="expected-answer">expected answer</TermDef> you provided.
      </p>
      <h4 style={{ margin: '0 0 6px 0', fontSize: 13, color: '#fff' }}>What it changes</h4>
      <ul style={{ margin: '0 0 10px 0', paddingLeft: 18, color: '#bbb' }}>
        <li>Retrieval depth (top-k chunks)</li>
        <li>LLM model used to answer</li>
        <li>Query rewriting on/off</li>
        <li>System prompt variant (default / strict / concise)</li>
        <li>Whether source labels are visible to the model</li>
      </ul>
      <h4 style={{ margin: '0 0 6px 0', fontSize: 13, color: '#fff' }}>What it doesn't change</h4>
      <ul style={{ margin: '0 0 10px 0', paddingLeft: 18, color: '#bbb' }}>
        <li>Sources (we suggest improvements but never add or remove)</li>
        <li>Test queries</li>
        <li>Settings — until you click Apply</li>
      </ul>
      <h4 style={{ margin: '0 0 6px 0', fontSize: 13, color: '#fff' }}>Caveats</h4>
      <ul style={{ margin: 0, paddingLeft: 18, color: '#bbb' }}>
        <li>Costs LLM tokens (you'll set the budget next)</li>
        <li>Tuning quality depends on test-question quality</li>
      </ul>
    </div>
  )
}

function TestSetStep({
  coverage, onChange, onSwitchToQueries, onClose,
}: {
  coverage: OptimizationCoverage
  onChange: (c: OptimizationCoverage) => void
  onSwitchToQueries?: () => void
  onClose: () => void
}) {
  const [showExample, setShowExample] = useState(false)
  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>Test set source</h4>
      <p style={{ margin: '0 0 12px 0', color: '#bbb' }}>
        If you've already written test questions, we'll use those. Otherwise
        we'll generate them from your documents — <b>and you'll review them
        before tuning starts</b>. Pick how thorough that generation should be:
      </p>
      <button
        type="button"
        onClick={() => setShowExample(v => !v)}
        style={{
          marginBottom: 10, padding: 0, background: 'transparent', border: 'none',
          color: '#a78bfa', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
          cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4,
        }}
        aria-expanded={showExample}
      >
        {showExample ? '▾' : '▸'} See an example test question
      </button>
      {showExample && (
        <div style={{
          padding: '8px 10px', marginBottom: 10,
          background: '#181818', border: '1px solid #2a2a2a', borderRadius: 6,
          fontSize: 12, color: '#ccc', lineHeight: 1.6,
        }}>
          <div><span style={{ color: '#888' }}>Question:</span> Who is the principal investigator on the Reed grant?</div>
          <div style={{ marginTop: 4 }}><span style={{ color: '#888' }}>Expected answer:</span> Dr. Maria Reed</div>
          <div style={{ marginTop: 6, fontSize: 11, color: '#888' }}>
            The judge passes the AI's answer if it matches the expected answer — typo-tolerant and synonym-aware.
          </div>
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {(['quick', 'standard', 'exhaustive'] as const).map(c => {
          const active = coverage === c
          const counts: Record<typeof c, number> = { quick: 5, standard: 10, exhaustive: 25 } as Record<OptimizationCoverage, number>
          return (
            <button
              key={c}
              onClick={() => onChange(c)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 12px', textAlign: 'left',
                backgroundColor: active ? 'rgba(124, 58, 237, 0.12)' : '#262626',
                border: '1px solid ' + (active ? '#7c3aed' : '#333'),
                borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', color: '#e5e5e5',
              }}
            >
              <Radio active={active} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'capitalize' }}>{c}</div>
                <div style={{ fontSize: 11, color: '#888' }}>up to {counts[c]} questions</div>
              </div>
            </button>
          )
        })}
      </div>
      <p style={{ marginTop: 10, fontSize: 11, color: '#888' }}>
        Generated queries persist after the run, so future re-runs reuse them.
      </p>
      {onSwitchToQueries && (
        <button
          onClick={() => { onClose(); onSwitchToQueries() }}
          style={{
            marginTop: 8, fontSize: 11, fontFamily: 'inherit',
            background: 'transparent', border: 'none', padding: 0,
            color: '#a78bfa', cursor: 'pointer',
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
  kbUuid, coverage, sampleQueryIds, onReady, onSwitchToQueries, onClose,
}: {
  kbUuid: string
  coverage: OptimizationCoverage
  sampleQueryIds: string[]
  onReady: (ids: string[]) => void
  onSwitchToQueries?: () => void
  onClose: () => void
}) {
  // States: 'loading' (fetching existing OR generating), 'preview' (have queries),
  // or 'error'. ``mode`` distinguishes whether queries pre-existed or got generated.
  const [queries, setQueries] = useState<KBTestQuery[]>([])
  const [mode, setMode] = useState<'existing' | 'generated' | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  // Inline edit state for fixing a generated/saved question without leaving the
  // wizard. `editingUuid` selects which card shows the edit form.
  const [editingUuid, setEditingUuid] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<DraftShape>(EMPTY_DRAFT)
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

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
    if (!window.confirm(`Remove this test question?\n\n"${q.query}"`)) return
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
        const existing = await listKBTestQueries(kbUuid)
        if (cancelled) return
        if (existing.test_queries.length > 0) {
          if (cancelled) return
          setQueries(existing.test_queries)
          setMode('existing')
          onReady(existing.test_queries.map(q => q.uuid))
          setLoading(false)
          return
        }
        const generated = await generateKBTestQueries(kbUuid, { coverage, async: false })
        if (cancelled) return
        if ('test_queries' in generated) {
          setQueries(generated.test_queries)
          setMode('generated')
          onReady(generated.test_queries.map(q => q.uuid))
        } else {
          setError('Generation was queued instead of returning inline — try again.')
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message || 'Failed to load test questions.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbUuid, coverage, attempt])

  if (loading) {
    return (
      <WizardLoadingStep
        message={sampleQueryIds.length > 0 ? 'Loading your test questions…' : 'Writing test questions from your documents…'}
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

  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>
        {mode === 'existing' ? 'Your saved test questions' : 'Generated test questions'}
      </h4>
      <p style={{ margin: '0 0 10px 0', color: '#bbb' }}>
        {mode === 'existing' ? (
          <>We'll grade each tuning trial against these <b>{queries.length}</b> questions using a <TermDef term="judge">judge</TermDef>.</>
        ) : (
          <>Tuning quality depends on these. Scan them and fix anything that looks off — edit or remove a question right here before continuing.</>
        )}
      </p>
      {actionError && (
        <div style={{ margin: '0 0 8px 0', fontSize: 11, color: '#f87171' }}>{actionError}</div>
      )}
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 6,
        maxHeight: 260, overflowY: 'auto',
        padding: 8, backgroundColor: '#181818', border: '1px solid #2a2a2a', borderRadius: 6,
      }}>
        {queries.map((q, i) => (
          <div key={q.uuid} style={{
            padding: '6px 8px', backgroundColor: '#262626', borderRadius: 4,
            fontSize: 12, color: '#e5e5e5',
          }}>
            {editingUuid === q.uuid ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <QueryFormFields draft={editDraft} onChange={setEditDraft} />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={handleUpdate}
                    disabled={saving || !editDraft.query.trim()}
                    style={{
                      fontSize: 11, fontFamily: 'inherit', padding: '4px 10px', borderRadius: 5,
                      border: '1px solid #15803d55', backgroundColor: '#15803d1a',
                      color: saving || !editDraft.query.trim() ? '#555' : '#e5e5e5',
                      cursor: saving || !editDraft.query.trim() ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                  <button
                    onClick={() => setEditingUuid(null)}
                    style={{
                      fontSize: 11, fontFamily: 'inherit', padding: '4px 10px', borderRadius: 5,
                      border: '1px solid #3a3a3a', backgroundColor: '#2a2a2a', color: '#e5e5e5', cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <span style={{ color: '#666', fontSize: 11, marginTop: 1 }}>{i + 1}.</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div>{q.query}</div>
                  {q.expected_answer && (
                    <div style={{
                      marginTop: 3, fontSize: 11, color: '#888',
                      overflow: 'hidden', textOverflow: 'ellipsis',
                      display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                    }}>
                      expected: {q.expected_answer}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
                  <button
                    onClick={() => startEdit(q)}
                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: '#888' }}
                    title="Edit question"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    onClick={() => handleDelete(q)}
                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: '#888' }}
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
          <div style={{ fontSize: 11, color: '#666', padding: '4px 8px' }}>
            No test questions left. Add some on the Test Queries tab before tuning.
          </div>
        )}
      </div>
      {onSwitchToQueries && (
        <button
          onClick={() => { onClose(); onSwitchToQueries() }}
          style={{
            marginTop: 10, fontSize: 11, fontFamily: 'inherit',
            background: 'transparent', border: 'none', padding: 0,
            color: '#a78bfa', cursor: 'pointer',
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
        sub="Asking the model your test questions without retrieval (~10 seconds)."
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
      <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.5 }}>
        <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>Baseline skipped</h4>
        <p style={{ margin: '0 0 10px 0', color: '#bbb' }}>
          We couldn't measure a no-KB <TermDef term="baseline">baseline</TermDef> because none of your test questions have an expected answer yet. Tuning will still measure baselines during the run.
        </p>
      </div>
    )
  }

  const scorePct = Math.round(noKbScore * 100)
  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>How well the model does without your KB</h4>
      <div style={{
        padding: '14px 16px', marginBottom: 10,
        backgroundColor: 'rgba(124, 58, 237, 0.08)',
        border: '1px solid rgba(124, 58, 237, 0.3)', borderRadius: 6,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ fontSize: 28, fontWeight: 700, color: '#fff' }}>{scorePct}%</span>
          <span style={{ fontSize: 12, color: '#bbb' }}>
            of test questions answered correctly <i>without</i> the knowledge base
          </span>
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: '#ddd' }}>
          {scorePct >= 85
            ? <>The model already knows most of this material — tuning will probably gain a few points at best.</>
            : scorePct >= 60
              ? <>Decent floor. Tuning has room to improve answers that need your specific documents.</>
              : <>Low floor — your knowledge base has a real job to do here. Tuning should help noticeably.</>}
        </div>
      </div>
      <button
        onClick={() => setWhyOpen(v => !v)}
        style={{
          background: 'transparent', border: 'none', padding: 0,
          fontSize: 11, color: '#888', fontFamily: 'inherit', cursor: 'pointer',
          textDecoration: 'underline dotted', textUnderlineOffset: 2,
        }}
      >
        {whyOpen ? '▴' : '▾'} Why does this matter?
      </button>
      {whyOpen && (
        <div style={{
          marginTop: 8, padding: '8px 10px', fontSize: 11, color: '#aaa', lineHeight: 1.5,
          backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid #2a2a2a', borderRadius: 6,
        }}>
          Tuning only matters where your KB beats the model's own knowledge. If the model
          already answers most questions correctly from training data, even the best retrieval
          settings can only add a few points. We use this floor to recommend a budget that
          matches the realistic ceiling.
        </div>
      )}
      {recommendedTier && (
        <div style={{ marginTop: 10, fontSize: 11, color: '#a78bfa' }}>
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
    <div style={{ fontSize: 13, color: '#ccc' }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>Advanced options</h4>
      <Toggle
        label="Apply optimized settings automatically when finished"
        description="If unchecked, we'll show you the results and you can apply them manually."
        checked={applyOnFinish}
        onChange={onApplyOnFinish}
      />
      <Toggle
        label="Try re-chunking documents (advanced)"
        description="Coming in v2 — disabled. Re-chunks + re-embeds for each chunking trial. Slower."
        checked={false}
        disabled
      />
      <Toggle
        label="Try alternate embedding models (advanced)"
        description="Coming in v2 — disabled. Re-embeds the entire KB for each embedding-model trial."
        checked={false}
        disabled
      />
      <div style={{
        marginTop: 16, padding: '10px 12px',
        backgroundColor: 'rgba(124, 58, 237, 0.08)',
        border: '1px solid rgba(124, 58, 237, 0.3)', borderRadius: 6,
      }}>
        <div style={{ fontSize: 11, color: '#a78bfa', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
          Ready to start
        </div>
        <div style={{ fontSize: 13, color: '#e5e5e5' }}>
          Budget: <b>{tokensLabel}</b>{costLabel && <> · <b>{costLabel}</b></>}
        </div>
      </div>
    </div>
  )
}
