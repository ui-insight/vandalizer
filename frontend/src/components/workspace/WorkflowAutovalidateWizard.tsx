/**
 * 4-step wizard for workflow tuning: concept → test cases → budget → advanced.
 *
 * Mirrors ExtractionAutovalidateWizard, which mirrors the KB flow. Consumes
 * the shared AutovalidateWizard shell + BudgetTierPicker; the panel layer
 * (WorkflowAutovalidatePanel) handles run state, polling, and apply/revert.
 *
 * Test-case generation is wired through here: when no expected outputs are
 * saved, the wizard's test-case step lets the user run the proposer + accept
 * before the optimizer is allowed to start.
 */
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useToast } from '../../contexts/ToastContext'
import { getUserConfig } from '../../api/config'
import { formatBudgetEstimate } from '../../api/knowledge'
import type { ModelInfo } from '../../types/workflow'
import {
  acceptTestCases,
  getExpectedOutputs,
  getValidationInputs,
  proposeTestCases,
  startWorkflowOptimization,
  synthesizeTestCase,
  updateValidationInputs,
  type ExpectedOutput,
  type StartWorkflowOptimizationOptions,
  type TestCaseProposal,
} from '../../api/workflows'
import { AutovalidateWizard, type WizardStep } from '../shared/AutovalidateWizard'
import { BudgetTierPicker } from '../shared/BudgetTierPicker'
import {
  WORKFLOW_BUDGET_TIERS,
  type WorkflowBudgetTier,
} from '../shared/budgetTiers'
import { Toggle } from '../shared/Toggle'
import { TermDef } from '../shared/TermDef'

interface Props {
  workflowId: string
  onClose: () => void
  onStarted: (runUuid: string) => void
}

type Tier = typeof WORKFLOW_BUDGET_TIERS[number]['id'] | 'custom'

interface WorkflowWizardOptions {
  tier: Tier
  customCandidates: number
  applyOnFinish: boolean
  includeJudge: boolean
}

const INITIAL_OPTIONS: WorkflowWizardOptions = {
  tier: 'standard',
  customCandidates: 6,
  applyOnFinish: false,
  includeJudge: true,
}

export function WorkflowAutovalidateWizard({ workflowId, onClose, onStarted }: Props) {
  const { toast } = useToast()
  const [expectedOutputs, setExpectedOutputs] = useState<ExpectedOutput[] | null>(null)
  const [userModel, setUserModel] = useState<ModelInfo | null>(null)
  const [proposing, setProposing] = useState(false)
  const [synthesizing, setSynthesizing] = useState(false)
  const [proposals, setProposals] = useState<TestCaseProposal[] | null>(null)

  const refreshExpectedOutputs = async () => {
    try {
      const { expected_outputs } = await getExpectedOutputs(workflowId)
      setExpectedOutputs(expected_outputs)
    } catch {
      setExpectedOutputs([])
    }
  }

  useEffect(() => {
    void refreshExpectedOutputs()
    getUserConfig()
      .then(cfg => {
        const target = cfg.model
        const match = cfg.available_models.find(m => m.tag === target || m.name === target)
          || cfg.available_models[0]
          || null
        setUserModel(match)
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  const candidatesFor = (opts: WorkflowWizardOptions): number => {
    if (opts.tier === 'custom') return Math.max(1, opts.customCandidates)
    const tier = WORKFLOW_BUDGET_TIERS.find(t => t.id === opts.tier)
    return tier?.maxCandidates ?? 8
  }

  const tokenBudgetFor = (opts: WorkflowWizardOptions): number => {
    if (opts.tier === 'custom') {
      // Custom = N candidates × 600k tokens per trial (3 inputs × 200k ceiling).
      return Math.max(1, opts.customCandidates) * 600_000
    }
    const tier = WORKFLOW_BUDGET_TIERS.find(t => t.id === opts.tier)
    return tier?.tokens ?? 0
  }

  const handleConfirm = async (opts: WorkflowWizardOptions) => {
    const payload: StartWorkflowOptimizationOptions = {
      token_budget: opts.includeJudge ? tokenBudgetFor(opts) : 0,
      max_candidates: candidatesFor(opts),
      apply_on_finish: opts.applyOnFinish,
      include_judge: opts.includeJudge,
    }
    try {
      const { run_uuid } = await startWorkflowOptimization(workflowId, payload)
      onStarted(run_uuid)
      onClose()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to start optimization', 'error')
    }
  }

  const handleProposeFromHistory = async () => {
    setProposing(true)
    try {
      const res = await proposeTestCases(workflowId, 5)
      setProposals(res.proposals)
      if (res.note) toast(res.note, 'info')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to propose test cases', 'error')
    } finally {
      setProposing(false)
    }
  }

  const handleAcceptProposals = async (
    chosen: { session_id: string; label: string }[],
  ) => {
    if (chosen.length === 0) return
    setProposing(true)
    try {
      const labels: Record<string, string> = {}
      for (const c of chosen) labels[c.session_id] = c.label
      await acceptTestCases(workflowId, chosen.map(c => c.session_id), labels)
      setProposals(null)
      await refreshExpectedOutputs()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to save test cases', 'error')
    } finally {
      setProposing(false)
    }
  }

  const handleSynthesize = async () => {
    setSynthesizing(true)
    try {
      // synthesize only returns {label, text} — it doesn't persist. Save it as a
      // text input ourselves (mirrors ValidateTab) so it actually appears under
      // Validate tab → Test Inputs; otherwise we'd direct the user to find a
      // seed that was never saved.
      const seed = await synthesizeTestCase(workflowId)
      const { inputs } = await getValidationInputs(workflowId)
      await updateValidationInputs(workflowId, [
        ...inputs,
        { id: `synth-${Date.now()}`, type: 'text', label: seed.label, text: seed.text },
      ])
      toast(
        'Synthesized and saved a seed input. Open the Validate tab → Test Inputs to run it, then come back here to tune.',
        'success',
      )
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to synthesize seed input', 'error')
    } finally {
      setSynthesizing(false)
    }
  }

  const steps: WizardStep<WorkflowWizardOptions>[] = [
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
          expectedOutputs={expectedOutputs}
          proposals={proposals}
          proposing={proposing}
          synthesizing={synthesizing}
          onPropose={handleProposeFromHistory}
          onAccept={handleAcceptProposals}
          onSynthesize={handleSynthesize}
        />
      ),
      // Gate: optimizer hard-errors without at least one expected_output.
      canAdvance: () => (expectedOutputs?.length ?? 0) > 0,
    },
    {
      id: 'budget',
      label: 'Budget',
      render: (opts, set) => (
        <BudgetStep
          tier={opts.tier}
          onTier={id => set(o => ({ ...o, tier: id as Tier }))}
          customCandidates={opts.customCandidates}
          onCustomCandidates={n => set(o => ({ ...o, customCandidates: n }))}
          userModel={userModel}
          candidatesForOpts={candidatesFor}
          opts={opts}
        />
      ),
    },
    {
      id: 'advanced',
      label: 'Advanced',
      render: (opts, set) => (
        <AdvancedStep
          candidates={candidatesFor(opts)}
          testCaseCount={expectedOutputs?.length ?? 0}
          applyOnFinish={opts.applyOnFinish}
          onApplyOnFinish={b => set(o => ({ ...o, applyOnFinish: b }))}
          includeJudge={opts.includeJudge}
          onIncludeJudge={b => set(o => ({ ...o, includeJudge: b }))}
        />
      ),
    },
  ]

  const confirmLabel = (opts: WorkflowWizardOptions): string => {
    const tokens = tokenBudgetFor(opts)
    const { cost_label } = formatBudgetEstimate(tokens, userModel)
    const tier = WORKFLOW_BUDGET_TIERS.find(t => t.id === opts.tier)
    const time = tier?.timeEstimate
    const parts: string[] = []
    if (cost_label) parts.push(cost_label)
    if (time) parts.push(`~${time}`)
    return parts.length > 0 ? `Validate & improve — ${parts.join(', ')}` : 'Validate & improve'
  }

  return (
    <AutovalidateWizard<WorkflowWizardOptions>
      steps={steps}
      initialOptions={INITIAL_OPTIONS}
      onConfirm={handleConfirm}
      onClose={onClose}
      title="Validate & improve this workflow"
      confirmLabel={confirmLabel}
    />
  )
}


// ---------------------------------------------------------------------------
// Step bodies
// ---------------------------------------------------------------------------


function ConceptStep() {
  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.6 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>What happens when you run this?</h4>
      <p style={{ margin: '0 0 10px 0' }}>
        First we run your workflow as-is and score it against your{' '}
        <TermDef term="test-set">expected outputs</TermDef> — that's your validation score.
        Then we try other ways of running it — each per-step combination of model and
        prompt-style is a <TermDef term="candidate">candidate</TermDef> — and keep whichever
        scores best. Another AI — the <TermDef term="judge">judge</TermDef> — grades each
        result so wording differences don't unfairly penalize a good answer.
      </p>
      <h4 style={{ margin: '0 0 6px 0', fontSize: 13, color: '#fff' }}>What it changes</h4>
      <ul style={{ margin: '0 0 10px 0', paddingLeft: 18, color: '#bbb' }}>
        <li>Per-step LLM model</li>
        <li>Per-step prompt style (when the step is prompt-driven)</li>
      </ul>
      <h4 style={{ margin: '0 0 6px 0', fontSize: 13, color: '#fff' }}>What it doesn't change</h4>
      <ul style={{ margin: '0 0 10px 0', paddingLeft: 18, color: '#bbb' }}>
        <li>The workflow's structure (steps, order)</li>
        <li>Your expected outputs</li>
        <li>Your live config — until you click Apply</li>
      </ul>
      <h4 style={{ margin: '0 0 6px 0', fontSize: 13, color: '#fff' }}>Caveats</h4>
      <ul style={{ margin: 0, paddingLeft: 18, color: '#bbb' }}>
        <li>Costs LLM tokens (you'll set the budget shortly)</li>
        <li>Each trial runs the full workflow once per expected output</li>
      </ul>
    </div>
  )
}


function TestCasesStep({
  expectedOutputs, proposals, proposing, synthesizing,
  onPropose, onAccept, onSynthesize,
}: {
  expectedOutputs: ExpectedOutput[] | null
  proposals: TestCaseProposal[] | null
  proposing: boolean
  synthesizing: boolean
  onPropose: () => void
  onAccept: (chosen: { session_id: string; label: string }[]) => void
  onSynthesize: () => void
}) {
  // Local state for the per-proposal checkbox + label edits.
  const [selectedSessions, setSelectedSessions] = useState<Set<string>>(new Set())
  const [labelEdits, setLabelEdits] = useState<Record<string, string>>({})

  if (expectedOutputs === null) {
    return <div style={{ fontSize: 13, color: '#6b7280' }}>Loading test cases…</div>
  }

  // If proposals are showing, render the review view.
  if (proposals && proposals.length > 0) {
    return (
      <div style={{ fontSize: 13, color: '#ccc' }}>
        <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>
          {proposals.length} candidate{proposals.length === 1 ? '' : 's'} from past runs
        </h4>
        <p style={{ margin: '0 0 10px 0', color: '#bbb' }}>
          Pick which ones to keep as expected outputs. Higher confidence = better fit
          based on the workflow's purpose.
        </p>
        <div style={{
          display: 'flex', flexDirection: 'column', gap: 6,
          maxHeight: 280, overflowY: 'auto',
          padding: 8, backgroundColor: '#181818', border: '1px solid #2a2a2a', borderRadius: 6,
        }}>
          {proposals.map(p => {
            const checked = selectedSessions.has(p.session_id)
            const label = labelEdits[p.session_id] ?? p.suggested_label
            return (
              <label
                key={p.session_id}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  padding: '8px 10px', backgroundColor: checked ? '#22c55e22' : '#262626',
                  borderRadius: 4, fontSize: 12, color: '#e5e5e5',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={e => {
                    const next = new Set(selectedSessions)
                    if (e.target.checked) next.add(p.session_id)
                    else next.delete(p.session_id)
                    setSelectedSessions(next)
                  }}
                  style={{ marginTop: 3 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input
                      value={label}
                      onChange={e => setLabelEdits({ ...labelEdits, [p.session_id]: e.target.value })}
                      onClick={e => e.stopPropagation()}
                      style={{
                        flex: 1, background: '#1a1a1a', color: '#e5e5e5',
                        border: '1px solid #333', borderRadius: 4, padding: '3px 6px',
                        fontSize: 12, fontFamily: 'inherit',
                      }}
                    />
                    <span style={{
                      fontSize: 9, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase',
                      padding: '2px 6px', borderRadius: 4,
                      background: p.confidence >= 0.7 ? '#22c55e33' : p.confidence >= 0.4 ? '#f59e0b33' : '#ef444433',
                      color: p.confidence >= 0.7 ? '#86efac' : p.confidence >= 0.4 ? '#fcd34d' : '#fca5a5',
                    }}>
                      {Math.round(p.confidence * 100)}%
                    </span>
                  </div>
                  {p.why && (
                    <div style={{ fontSize: 11, color: '#888', fontStyle: 'italic', marginTop: 3 }}>
                      {p.why}
                    </div>
                  )}
                </div>
              </label>
            )
          })}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button
            onClick={() => onAccept(
              [...selectedSessions].map(sid => ({
                session_id: sid,
                label: labelEdits[sid] ?? (proposals.find(p => p.session_id === sid)?.suggested_label ?? ''),
              }))
            )}
            disabled={proposing || selectedSessions.size === 0}
            style={{
              padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
              border: 'none', borderRadius: 6, cursor: proposing || selectedSessions.size === 0 ? 'not-allowed' : 'pointer',
              background: '#22c55e', color: '#fff',
              opacity: proposing || selectedSessions.size === 0 ? 0.5 : 1,
            }}
          >
            {proposing
              ? 'Saving…'
              : `Save ${selectedSessions.size || ''} selected`}
          </button>
        </div>
      </div>
    )
  }

  // Default view — list existing + offer to propose or synthesize.
  if (expectedOutputs.length === 0) {
    return (
      <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.6 }}>
        <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>You don't have expected outputs yet</h4>
        <p style={{ margin: '0 0 12px 0', color: '#bbb' }}>
          The optimizer scores trial configurations against past results. We'll suggest
          candidates from your run history, or synthesize a seed input you can run first.
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={onPropose}
            disabled={proposing}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              color: '#fff',
              background: 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
              border: '1px solid #7c3aed',
              borderRadius: 6, cursor: proposing ? 'wait' : 'pointer',
              opacity: proposing ? 0.7 : 1,
            }}
          >
            {proposing && <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />}
            Suggest from history
          </button>
          <button
            onClick={onSynthesize}
            disabled={synthesizing}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              color: '#a78bfa', background: 'transparent',
              border: '1px solid rgba(124, 58, 237, 0.4)',
              borderRadius: 6, cursor: synthesizing ? 'wait' : 'pointer',
              opacity: synthesizing ? 0.7 : 1,
            }}
          >
            {synthesizing && <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />}
            Synthesize seed input
          </button>
        </div>
        <p style={{ marginTop: 12, fontSize: 11, color: '#888' }}>
          Once at least one expected output is saved, the Next button will unlock.
        </p>
      </div>
    )
  }

  const visible = expectedOutputs.slice(0, 8)
  const hidden = Math.max(0, expectedOutputs.length - visible.length)

  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>
        {expectedOutputs.length} expected output{expectedOutputs.length === 1 ? '' : 's'} ready
      </h4>
      <p style={{ margin: '0 0 10px 0', color: '#bbb' }}>
        Each trial runs the full workflow against the input that produced these outputs
        and scores the result.
      </p>
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 6,
        maxHeight: 200, overflowY: 'auto',
        padding: 8, backgroundColor: '#181818', border: '1px solid #2a2a2a', borderRadius: 6,
      }}>
        {visible.map((eo, i) => (
          <div key={eo.id} style={{
            padding: '6px 8px', backgroundColor: '#262626', borderRadius: 4,
            fontSize: 12, color: '#e5e5e5',
          }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
              <span style={{ color: '#666', fontSize: 11 }}>{i + 1}.</span>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {eo.label || `Test ${eo.id.slice(0, 8)}`}
              </span>
              {eo.source === 'test_case_generator' && (
                <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.05em', color: '#86efac' }}>AUTO</span>
              )}
            </div>
          </div>
        ))}
        {hidden > 0 && (
          <div style={{ fontSize: 11, color: '#666', padding: '4px 8px' }}>…and {hidden} more</div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <button
          onClick={onPropose}
          disabled={proposing}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
            color: '#a78bfa', background: 'transparent',
            border: '1px solid rgba(124, 58, 237, 0.4)',
            borderRadius: 6, cursor: proposing ? 'wait' : 'pointer',
          }}
        >
          + Suggest more from history
        </button>
      </div>
    </div>
  )
}


function BudgetStep({
  tier, onTier, customCandidates, onCustomCandidates,
  userModel, candidatesForOpts, opts,
}: {
  tier: Tier
  onTier: (id: string) => void
  customCandidates: number
  onCustomCandidates: (n: number) => void
  userModel: ModelInfo | null
  candidatesForOpts: (o: WorkflowWizardOptions) => number
  opts: WorkflowWizardOptions
}) {
  const selectedTier = WORKFLOW_BUDGET_TIERS.find(t => t.id === tier)
  const selectedTokens = tier === 'custom'
    ? Math.max(1, customCandidates) * 600_000
    : (selectedTier?.tokens ?? 0)
  const { tokens_label, cost_label } = formatBudgetEstimate(selectedTokens, userModel)

  return (
    <BudgetTierPicker
      tiers={WORKFLOW_BUDGET_TIERS as readonly WorkflowBudgetTier[]}
      selected={tier}
      onSelect={onTier}
      customTokens={customCandidates}
      onCustomTokens={onCustomCandidates}
      tokensLabel={`${candidatesForOpts(opts)} configurations tried`}
      costLabel={cost_label ?? tokens_label}
      formatTierRow={t => {
        const { tokens_label, cost_label } = formatBudgetEstimate(t.tokens, userModel)
        return { tokensLabel: tokens_label, costLabel: cost_label }
      }}
      title="How thorough?"
      description="Each trial runs the full workflow against every expected output. Larger budgets find a more confident winner; smaller ones confirm whether tuning helps at all."
    />
  )
}


function AdvancedStep({
  candidates, testCaseCount, applyOnFinish, onApplyOnFinish,
  includeJudge, onIncludeJudge,
}: {
  candidates: number
  testCaseCount: number
  applyOnFinish: boolean
  onApplyOnFinish: (b: boolean) => void
  includeJudge: boolean
  onIncludeJudge: (b: boolean) => void
}) {
  return (
    <div style={{ fontSize: 13, color: '#ccc' }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>Advanced options</h4>
      <Toggle
        label="Score by meaning, not exact text (recommended)"
        description="The judge LLM grades each output for content match instead of strict string equality. Costs extra tokens; turn off only for deterministic workflows where you want exact-match scoring."
        checked={includeJudge}
        onChange={onIncludeJudge}
      />
      <Toggle
        label="Apply optimized settings automatically when finished"
        description="If unchecked, we'll show you results and you can apply manually. Apply is also blocked when the winner is statistically tied with your current config."
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
          <b>{testCaseCount}</b> expected output{testCaseCount === 1 ? '' : 's'}
          {includeJudge ? ' · meaning-based scoring' : ' · strict-text scoring'}
          {applyOnFinish ? ' · auto-apply' : ''}
        </div>
      </div>
    </div>
  )
}
