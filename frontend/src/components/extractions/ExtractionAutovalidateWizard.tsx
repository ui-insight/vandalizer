/**
 * 5-step wizard for extraction tuning: concept → test cases → budget → baseline → advanced.
 *
 * Built on the shared `AutovalidateWizard` shell. Each step is a `WizardStep`
 * whose `render` function returns the step body. The wizard owns the options
 * state; this component supplies the renders + the final start handler.
 *
 * Mirrors the KB Autovalidate flow:
 *   Concept       — explain what tuning changes and what it doesn't.
 *   Test cases    — load existing or generate from documents; show a preview.
 *   Budget        — pick Quick / Standard / Thorough → max_candidates.
 *   Advanced      — judge toggle, apply-on-finish, summary, Start.
 */
import { useEffect, useState } from 'react'
import { useToast } from '../../contexts/ToastContext'
import { getUserConfig } from '../../api/config'
import { formatBudgetEstimate } from '../../api/knowledge'
import type { ModelInfo } from '../../types/workflow'
import {
  getExtractionBaselineProbe,
  listTestCases,
  startExtractionOptimization,
  type StartExtractionOptimizationOptions,
  type TestCase,
} from '../../api/extractions'
import { AutovalidateWizard, type WizardStep } from '../shared/AutovalidateWizard'
import { BudgetTierPicker } from '../shared/BudgetTierPicker'
import {
  EXTRACTION_BUDGET_TIERS,
  type ExtractionBudgetTier,
} from '../shared/budgetTiers'
import {
  recommendLevel,
  recommendationReason,
} from '../shared/baselineRecommendation'
import { Toggle } from '../shared/Toggle'
import { TermDef } from '../shared/TermDef'
import { WizardLoadingStep } from '../shared/WizardLoadingStep'
import { GenerateTestCasesModal } from './GenerateTestCasesModal'

interface Props {
  searchSetUuid: string
  onClose: () => void
  /** Called after the tuning run is queued; parent typically begins polling. */
  onStarted: (runUuid: string) => void
}

type Tier = typeof EXTRACTION_BUDGET_TIERS[number]['id'] | 'custom'

interface ExtractionWizardOptions {
  tier: Tier
  customCandidates: number
  applyOnFinish: boolean
  includeJudge: boolean
  /** Populated by BaselineStep; drives the Budget step's recommended tier. */
  noSettingsScore: number | null
  /** Computed in BaselineStep from ``noSettingsScore``. Null until the probe completes. */
  recommendedTier: Tier | null
}

const INITIAL_OPTIONS: ExtractionWizardOptions = {
  tier: 'standard',
  customCandidates: 6,
  applyOnFinish: false,
  includeJudge: true,
  noSettingsScore: null,
  recommendedTier: null,
}

/** Map the abstract baseline-recommendation level to extraction's tier IDs.
 * 'small' → 'quick', 'medium' → 'standard'. Kept local to the call site so
 * the shared helper stays domain-agnostic. */
function recommendExtractionTier(noSettingsScore: number | null): Tier {
  return recommendLevel(noSettingsScore) === 'small' ? 'quick' : 'standard'
}

export function ExtractionAutovalidateWizard({ searchSetUuid, onClose, onStarted }: Props) {
  const { toast } = useToast()
  const [testCases, setTestCases] = useState<TestCase[] | null>(null)
  const [showGenerateModal, setShowGenerateModal] = useState(false)
  const [userModel, setUserModel] = useState<ModelInfo | null>(null)

  // Load test cases + user model once
  useEffect(() => {
    listTestCases(searchSetUuid)
      .then(cases => setTestCases(cases))
      .catch(() => setTestCases([]))
    getUserConfig()
      .then(cfg => {
        const target = cfg.model
        const match = cfg.available_models.find(m => m.tag === target || m.name === target)
          || cfg.available_models[0]
          || null
        setUserModel(match)
      })
      .catch(() => { /* tokens-only fallback */ })
  }, [searchSetUuid])

  const candidatesFor = (opts: ExtractionWizardOptions): number => {
    if (opts.tier === 'custom') return Math.max(1, opts.customCandidates)
    const tier = EXTRACTION_BUDGET_TIERS.find(t => t.id === opts.tier)
    return tier?.maxCandidates ?? 8
  }

  const handleConfirm = async (opts: ExtractionWizardOptions) => {
    // Token budget is meaningful only when the judge is on — the optimizer
    // only counts judge tokens server-side, and tracking the trials' raw
    // extraction tokens isn't implemented. With the judge off, send 0 and let
    // the progress card hide the bar.
    //
    // Estimate: ~50k judge tokens per trial (matches the backend's per-trial
    // ceiling used by BudgetEnforcer). This is a soft target; trials proceed
    // even past the estimate.
    const candidates = candidatesFor(opts)
    const tokenBudget = opts.includeJudge ? candidates * 50_000 : 0

    const payload: StartExtractionOptimizationOptions = {
      token_budget: tokenBudget,
      max_candidates: candidates,
      apply_on_finish: opts.applyOnFinish,
      include_judge: opts.includeJudge,
    }
    try {
      const { run_uuid } = await startExtractionOptimization(searchSetUuid, payload)
      onStarted(run_uuid)
      onClose()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to start tuning', 'error')
    }
  }

  const steps: WizardStep<ExtractionWizardOptions>[] = [
    {
      id: 'concept',
      label: 'Concept',
      render: () => <ConceptStep />,
    },
    {
      id: 'test-cases',
      label: 'Test cases',
      render: () => (
        <TestCasesStep
          cases={testCases}
          onGenerate={() => setShowGenerateModal(true)}
        />
      ),
      // Can't tune without test cases — gate Next on having at least one
      canAdvance: () => (testCases?.length ?? 0) > 0,
    },
    {
      id: 'baseline',
      label: 'Baseline',
      render: (opts, set) => (
        <BaselineStep
          searchSetUuid={searchSetUuid}
          noSettingsScore={opts.noSettingsScore}
          recommendedTier={opts.recommendedTier}
          onReady={(score, tier) => set(o => ({
            ...o,
            noSettingsScore: score,
            recommendedTier: tier,
            // Only auto-bump the tier from default if the user hasn't moved off
            // 'standard' yet — otherwise we'd silently overwrite their choice.
            tier: o.tier === 'standard' && tier ? tier : o.tier,
          }))}
        />
      ),
      canAdvance: (o) => o.noSettingsScore != null || o.recommendedTier != null,
    },
    {
      id: 'budget',
      label: 'Budget',
      render: (opts, set) => (
        <BudgetStepContent
          tier={opts.tier}
          onTier={(id) => set(o => ({ ...o, tier: id as Tier }))}
          customCandidates={opts.customCandidates}
          onCustomCandidates={(n) => set(o => ({ ...o, customCandidates: n }))}
          userModel={userModel}
          candidatesForOpts={candidatesFor}
          opts={opts}
          recommendedTierId={opts.recommendedTier ?? undefined}
          recommendationReason={recommendationReason(opts.noSettingsScore, {
            withoutLabel: 'without custom settings',
          })}
        />
      ),
    },
    {
      id: 'advanced',
      label: 'Advanced',
      render: (opts, set) => (
        <AdvancedStep
          candidates={candidatesFor(opts)}
          applyOnFinish={opts.applyOnFinish}
          onApplyOnFinish={(b) => set(o => ({ ...o, applyOnFinish: b }))}
          includeJudge={opts.includeJudge}
          onIncludeJudge={(b) => set(o => ({ ...o, includeJudge: b }))}
          testCaseCount={testCases?.length ?? 0}
        />
      ),
    },
  ]

  const confirmLabel = (opts: ExtractionWizardOptions): string => {
    const tier = EXTRACTION_BUDGET_TIERS.find(t => t.id === opts.tier)
    const tokens = opts.tier === 'custom'
      ? opts.customCandidates * 80_000
      : (tier?.tokens ?? 0)
    const { cost_label } = formatBudgetEstimate(tokens, userModel)
    const time = tier?.timeEstimate
    const parts: string[] = []
    if (cost_label) parts.push(cost_label)
    if (time) parts.push(`~${time}`)
    return parts.length > 0 ? `Start tuning — ${parts.join(', ')}` : 'Start tuning'
  }

  return (
    <>
      <AutovalidateWizard<ExtractionWizardOptions>
        steps={steps}
        initialOptions={INITIAL_OPTIONS}
        onConfirm={handleConfirm}
        onClose={onClose}
        title="Tune this extraction"
        confirmLabel={confirmLabel}
      />
      {showGenerateModal && (
        <GenerateTestCasesModal
          searchSetUuid={searchSetUuid}
          onClose={() => setShowGenerateModal(false)}
          onSaved={() => {
            setShowGenerateModal(false)
            // Refresh list so the preview + canAdvance unlocks
            listTestCases(searchSetUuid)
              .then(cases => setTestCases(cases))
              .catch(() => {})
          }}
        />
      )}
    </>
  )
}


// ---------------------------------------------------------------------------
// Step bodies
// ---------------------------------------------------------------------------


function ConceptStep() {
  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.6 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>What is tuning?</h4>
      <p style={{ margin: '0 0 10px 0' }}>
        We try many ways of running your extraction — each combination of model,
        strategy, and prompt shape is a <TermDef term="candidate">candidate</TermDef> — and keep whichever
        one scores best against your <TermDef term="test-set">test cases</TermDef>. Another AI — the{' '}
        <TermDef term="judge">judge</TermDef> — grades each answer, so different formats of the
        same value still count as a match.
      </p>
      <h4 style={{ margin: '0 0 6px 0', fontSize: 13, color: '#fff' }}>What it changes</h4>
      <ul style={{ margin: '0 0 10px 0', paddingLeft: 18, color: '#bbb' }}>
        <li>Which LLM does the extracting</li>
        <li>Strategy — one call vs. plan-then-extract (one-pass / two-pass)</li>
        <li>Whether the model takes extra "thinking" time before answering</li>
        <li>Whether documents are sent as images (useful for fillable PDFs and scans)</li>
        <li>How long documents get split into chunks</li>
      </ul>
      <h4 style={{ margin: '0 0 6px 0', fontSize: 13, color: '#fff' }}>What it doesn't change</h4>
      <ul style={{ margin: '0 0 10px 0', paddingLeft: 18, color: '#bbb' }}>
        <li>Your extraction fields or prompts</li>
        <li>Your test cases</li>
        <li>Your live config — until you click Apply</li>
      </ul>
      <h4 style={{ margin: '0 0 6px 0', fontSize: 13, color: '#fff' }}>Caveats</h4>
      <ul style={{ margin: 0, paddingLeft: 18, color: '#bbb' }}>
        <li>Costs LLM tokens (you'll set the budget shortly)</li>
        <li>Tuning quality depends on test-case quality</li>
      </ul>
    </div>
  )
}


function TestCasesStep({
  cases, onGenerate,
}: { cases: TestCase[] | null; onGenerate: () => void }) {
  if (cases === null) {
    return <div style={{ fontSize: 13, color: '#6b7280' }}>Loading test cases…</div>
  }
  if (cases.length === 0) {
    return (
      <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.6 }}>
        <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>You don't have any test cases yet</h4>
        <p style={{ margin: '0 0 12px 0', color: '#bbb' }}>
          We need at least one example to check the AI's work against. Pick a few documents
          and we'll suggest expected values for each one — you review them before they're saved.
        </p>
        <button
          onClick={onGenerate}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
            color: '#fff',
            background: 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
            border: '1px solid #7c3aed',
            borderRadius: 6, cursor: 'pointer',
          }}
        >
          Generate test cases from documents
        </button>
        <p style={{ marginTop: 12, fontSize: 11, color: '#888' }}>
          Once you save at least one test case, the Next button below will unlock.
        </p>
      </div>
    )
  }

  const visible = cases.slice(0, 8)
  const hidden = Math.max(0, cases.length - visible.length)

  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>
        {cases.length} test case{cases.length === 1 ? '' : 's'} ready
      </h4>
      <p style={{ margin: '0 0 10px 0', color: '#bbb' }}>
        We'll score each trial against {cases.length === 1 ? 'this case' : 'these cases'}.
        Take a moment to scan them — if any look off, edit them before tuning starts.
      </p>
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 6,
        maxHeight: 200, overflowY: 'auto',
        padding: 8, backgroundColor: '#181818', border: '1px solid #2a2a2a', borderRadius: 6,
      }}>
        {visible.map((c, i) => {
          const fieldCount = Object.keys(c.expected_values || {}).length
          return (
            <div key={c.uuid} style={{
              padding: '6px 8px', backgroundColor: '#262626', borderRadius: 4,
              fontSize: 12, color: '#e5e5e5',
            }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
                <span style={{ color: '#666', fontSize: 11 }}>{i + 1}.</span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.label}
                </span>
                <span style={{ fontSize: 10, color: '#888' }}>
                  {fieldCount} field{fieldCount === 1 ? '' : 's'}
                </span>
              </div>
            </div>
          )
        })}
        {hidden > 0 && (
          <div style={{ fontSize: 11, color: '#666', padding: '4px 8px' }}>
            …and {hidden} more
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <button
          onClick={onGenerate}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
            color: '#a78bfa', background: 'transparent',
            border: '1px solid rgba(124, 58, 237, 0.4)',
            borderRadius: 6, cursor: 'pointer',
          }}
        >
          + Generate more from documents
        </button>
      </div>
      <p style={{ marginTop: 12, fontSize: 11, color: '#888' }}>
        Tip: 3–5 carefully-checked cases work better than 20 rushed ones. The optimizer is
        only as good as the cases you give it.
      </p>
    </div>
  )
}


function BaselineStep({
  searchSetUuid, noSettingsScore, recommendedTier, onReady,
}: {
  searchSetUuid: string
  noSettingsScore: number | null
  recommendedTier: Tier | null
  onReady: (score: number | null, tier: Tier | null) => void
}) {
  const [loading, setLoading] = useState(noSettingsScore == null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [whyOpen, setWhyOpen] = useState(false)

  useEffect(() => {
    if (noSettingsScore != null) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const result = await getExtractionBaselineProbe(searchSetUuid, { sample_size: 5 })
        if (cancelled) return
        const score = result.no_settings_score
        const tier = recommendExtractionTier(score)
        onReady(score, tier)
      } catch (e) {
        if (!cancelled) setError((e as Error).message || 'Failed to measure the no-settings baseline.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchSetUuid, attempt])

  if (loading) {
    return (
      <WizardLoadingStep
        message="Measuring the no-settings baseline…"
        sub="Running extraction with no custom settings on a few test cases (~10 seconds)."
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

  // No score (no test cases with expected values judgeable) — give the user a
  // path forward without blocking the wizard.
  if (noSettingsScore == null) {
    return (
      <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.5 }}>
        <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>Baseline skipped</h4>
        <p style={{ margin: '0 0 10px 0', color: '#bbb' }}>
          We couldn't score a no-settings baseline because none of the test cases have
          expected values yet. Tuning will still measure baselines during the run.
        </p>
      </div>
    )
  }

  const scorePct = Math.round(noSettingsScore * 100)
  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>
        How well extraction does without your settings
      </h4>
      <div style={{
        padding: '14px 16px', marginBottom: 10,
        backgroundColor: 'rgba(124, 58, 237, 0.08)',
        border: '1px solid rgba(124, 58, 237, 0.3)', borderRadius: 6,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ fontSize: 28, fontWeight: 700, color: '#fff' }}>{scorePct}%</span>
          <span style={{ fontSize: 12, color: '#bbb' }}>
            of test cases extracted correctly <i>without</i> your custom settings
          </span>
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: '#ddd' }}>
          {scorePct >= 85
            ? <>The model already handles most of this — tuning will probably gain a few points at best.</>
            : scorePct >= 60
              ? <>Decent floor. Tuning has room to improve fields that need your specific config.</>
              : <>Low floor — your custom settings have a real job to do here. Tuning should help noticeably.</>}
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
          Tuning only matters where your settings beat what the model does on its own. If the
          model already handles most cases from defaults, even the best configuration can only
          add a few points. We use this floor to recommend a budget that matches the realistic
          ceiling.
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


function BudgetStepContent({
  tier, onTier, customCandidates, onCustomCandidates,
  userModel, candidatesForOpts, opts,
  recommendedTierId, recommendationReason,
}: {
  tier: Tier
  onTier: (id: string) => void
  customCandidates: number
  onCustomCandidates: (n: number) => void
  userModel: ModelInfo | null
  candidatesForOpts: (o: ExtractionWizardOptions) => number
  opts: ExtractionWizardOptions
  recommendedTierId?: string
  recommendationReason?: string
}) {
  // Compute display labels for the picker's summary line
  const selectedTier = EXTRACTION_BUDGET_TIERS.find(t => t.id === tier)
  const selectedTokens = tier === 'custom'
    ? customCandidates * 80_000   // rough estimate per trial
    : (selectedTier?.tokens ?? 0)
  const { tokens_label, cost_label } = formatBudgetEstimate(selectedTokens, userModel)

  return (
    <BudgetTierPicker
      tiers={EXTRACTION_BUDGET_TIERS as readonly ExtractionBudgetTier[]}
      selected={tier}
      onSelect={onTier}
      customTokens={customCandidates}
      onCustomTokens={onCustomCandidates}
      tokensLabel={`${candidatesForOpts(opts)} configurations tried`}
      costLabel={cost_label ?? tokens_label}
      formatTierRow={(t) => {
        const { tokens_label, cost_label } = formatBudgetEstimate(t.tokens, userModel)
        return { tokensLabel: tokens_label, costLabel: cost_label }
      }}
      recommendedTierId={recommendedTierId}
      recommendationReason={recommendationReason}
      title="How thorough?"
      description="More configurations tried = better chance of finding the best one. Each configuration is run against every test case."
    />
  )
}


function AdvancedStep({
  candidates, applyOnFinish, onApplyOnFinish,
  includeJudge, onIncludeJudge, testCaseCount,
}: {
  candidates: number
  applyOnFinish: boolean
  onApplyOnFinish: (b: boolean) => void
  includeJudge: boolean
  onIncludeJudge: (b: boolean) => void
  testCaseCount: number
}) {
  return (
    <div style={{ fontSize: 13, color: '#ccc' }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>Advanced options</h4>
      <Toggle
        label="Score by meaning, not exact text (recommended)"
        description="Treats 'Jan 5, 2026' and '2026-01-05' as the same answer. Uses a small amount of extra AI usage; turn off for strict character-by-character matching."
        checked={includeJudge}
        onChange={onIncludeJudge}
      />
      <Toggle
        label="Apply optimized settings automatically when finished"
        description="If unchecked, we'll show you the results and you can apply them manually."
        checked={applyOnFinish}
        onChange={onApplyOnFinish}
      />
      <div style={{
        marginTop: 16, padding: '10px 12px',
        backgroundColor: 'rgba(124, 58, 237, 0.08)',
        border: '1px solid rgba(124, 58, 237, 0.3)', borderRadius: 6,
      }}>
        <div style={{ fontSize: 11, color: '#a78bfa', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
          Ready to tune
        </div>
        <div style={{ fontSize: 12, color: '#e5e5e5', lineHeight: 1.6 }}>
          <b>{candidates}</b> configuration{candidates === 1 ? '' : 's'} against{' '}
          <b>{testCaseCount}</b> test case{testCaseCount === 1 ? '' : 's'}
          {includeJudge ? ' · meaning-based scoring' : ' · strict-text scoring'}
          {applyOnFinish ? ' · auto-apply' : ''}
        </div>
      </div>
    </div>
  )
}
