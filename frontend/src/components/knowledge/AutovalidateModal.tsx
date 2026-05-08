import { useEffect, useState } from 'react'
import { Sparkles, X, ChevronRight, ChevronLeft } from 'lucide-react'
import {
  formatBudgetEstimate,
  type StartOptimizationOptions,
  type OptimizationCoverage,
} from '../../api/knowledge'
import { getUserConfig } from '../../api/config'
import type { ModelInfo } from '../../types/workflow'

interface Props {
  kbUuid: string
  onConfirm: (opts: StartOptimizationOptions) => void
  onClose: () => void
}

type Step = 'concept' | 'testset' | 'budget' | 'advanced'

const TIERS = [
  { id: 'conservative', label: 'Conservative', tokens: 500_000, trials: '~5 trials', time: '2–5 min' },
  { id: 'standard', label: 'Standard', tokens: 2_500_000, trials: '~25 trials', time: '10–20 min' },
  { id: 'thorough', label: 'Thorough', tokens: 10_000_000, trials: '~100 trials', time: '45–90 min' },
] as const

type Tier = typeof TIERS[number]['id'] | 'custom'

export function AutovalidateModal({ onConfirm, onClose }: Props) {
  const [step, setStep] = useState<Step>('concept')
  const [tier, setTier] = useState<Tier>('standard')
  const [customTokens, setCustomTokens] = useState(1_000_000)
  const [coverage, setCoverage] = useState<OptimizationCoverage>('standard')
  const [applyOnFinish, setApplyOnFinish] = useState(false)
  // The user's resolved model (incl. cost_per_1m_*) — populated from
  // /config/user. Drives the dollar-cost display when admins have populated
  // those fields. Falls back to tokens-only when null.
  const [userModel, setUserModel] = useState<ModelInfo | null>(null)

  useEffect(() => {
    getUserConfig().then(cfg => {
      // The route returns the user's model as a tag (or name). Match against
      // available_models — falling back to the first entry if the tag doesn't
      // resolve.
      const target = cfg.model
      const match = cfg.available_models.find(m => m.tag === target || m.name === target)
        || cfg.available_models[0]
        || null
      setUserModel(match)
    }).catch(() => {
      // Silent fallback — modal still works in tokens-only mode.
    })
  }, [])

  const tokens = tier === 'custom' ? customTokens : (TIERS.find(t => t.id === tier)?.tokens ?? 0)
  const { tokens_label, cost_label } = formatBudgetEstimate(tokens, userModel)

  const handleConfirm = () => {
    onConfirm({
      token_budget: tokens,
      apply_on_finish: applyOnFinish,
      autogen_coverage: coverage,
      include_indexing_track: false,
    })
  }

  const next = () => setStep(s => (
    s === 'concept' ? 'testset' :
    s === 'testset' ? 'budget' :
    s === 'budget' ? 'advanced' : s
  ))
  const prev = () => setStep(s => (
    s === 'advanced' ? 'budget' :
    s === 'budget' ? 'testset' :
    s === 'testset' ? 'concept' : s
  ))

  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        width: 520, maxHeight: '90vh', overflowY: 'auto',
        padding: 22, backgroundColor: '#1f1f1f',
        border: '1px solid #2e2e2e', borderRadius: 10,
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Sparkles size={18} style={{ color: '#a78bfa' }} />
          <h3 style={{ margin: 0, fontSize: 16, color: '#fff' }}>Autovalidate</h3>
          <button
            onClick={onClose}
            style={{ marginLeft: 'auto', background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: '#888' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Step indicator */}
        <Steps current={step} />

        {/* Body */}
        <div style={{ minHeight: 240, marginTop: 14 }}>
          {step === 'concept' && <ConceptStep />}
          {step === 'testset' && (
            <TestSetStep coverage={coverage} onChange={setCoverage} />
          )}
          {step === 'budget' && (
            <BudgetStep
              tier={tier} onTier={setTier}
              customTokens={customTokens} onCustomTokens={setCustomTokens}
              tokensLabel={tokens_label} costLabel={cost_label}
              userModel={userModel}
            />
          )}
          {step === 'advanced' && (
            <AdvancedStep
              applyOnFinish={applyOnFinish}
              onApplyOnFinish={setApplyOnFinish}
              tokensLabel={tokens_label} costLabel={cost_label}
            />
          )}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
          <button
            onClick={step === 'concept' ? onClose : prev}
            style={btn(true)}
          >
            {step === 'concept' ? 'Cancel' : (<><ChevronLeft size={12} />Back</>)}
          </button>
          {step !== 'advanced' ? (
            <button onClick={next} style={btn(true, '#7c3aed')}>
              Next<ChevronRight size={12} />
            </button>
          ) : (
            <button onClick={handleConfirm} style={btn(true, '#7c3aed')}>
              <Sparkles size={12} />
              Start optimization
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function Steps({ current }: { current: Step }) {
  const steps: Step[] = ['concept', 'testset', 'budget', 'advanced']
  const labels: Record<Step, string> = {
    concept: 'Concept', testset: 'Test set', budget: 'Budget', advanced: 'Advanced',
  }
  return (
    <div style={{ display: 'flex', gap: 4, marginTop: 12 }}>
      {steps.map((s, i) => {
        const active = s === current
        const done = steps.indexOf(current) > i
        return (
          <div key={s} style={{
            flex: 1, padding: '4px 6px', textAlign: 'center',
            fontSize: 10, fontWeight: 600,
            color: active ? '#fff' : done ? '#a78bfa' : '#666',
            borderBottom: '2px solid ' + (active ? '#a78bfa' : done ? '#7c3aed55' : '#333'),
          }}>
            {labels[s]}
          </div>
        )
      })}
    </div>
  )
}

function ConceptStep() {
  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.6 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>What is Autovalidate?</h4>
      <p style={{ margin: '0 0 10px 0' }}>
        We try many ways of using your knowledge base — different retrieval
        settings, prompts, and models — and keep whichever combination answers
        your test questions best. The LLM acts as a judge, comparing each
        answer to a canonical expected answer.
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
        <li>Optimization quality depends on test-question quality</li>
        <li>Judge scores have ~3-5pt noise; we report the confidence interval</li>
      </ul>
    </div>
  )
}

function TestSetStep({
  coverage, onChange,
}: { coverage: OptimizationCoverage; onChange: (c: OptimizationCoverage) => void }) {
  return (
    <div style={{ fontSize: 13, color: '#ccc', lineHeight: 1.5 }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>Test set source</h4>
      <p style={{ margin: '0 0 12px 0', color: '#bbb' }}>
        If you've already created test queries (manually or auto-generated),
        we'll use those. If not, we'll generate them from your KB content
        before the trials begin. Pick how thorough that generation should be:
      </p>
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
    </div>
  )
}

function BudgetStep({
  tier, onTier, customTokens, onCustomTokens, tokensLabel, costLabel, userModel,
}: {
  tier: Tier
  onTier: (t: Tier) => void
  customTokens: number
  onCustomTokens: (n: number) => void
  tokensLabel: string
  costLabel: string | null
  userModel: ModelInfo | null
}) {
  return (
    <div style={{ fontSize: 13, color: '#ccc' }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>Token budget</h4>
      <p style={{ margin: '0 0 12px 0', color: '#bbb', lineHeight: 1.5 }}>
        Optimization stops once it would exceed this budget. More budget =
        more configurations tried = higher chance of finding the best.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {TIERS.map(t => {
          const active = tier === t.id
          const { tokens_label, cost_label } = formatBudgetEstimate(t.tokens, userModel)
          return (
            <button
              key={t.id}
              onClick={() => onTier(t.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px', textAlign: 'left',
                backgroundColor: active ? 'rgba(124, 58, 237, 0.12)' : '#262626',
                border: '1px solid ' + (active ? '#7c3aed' : '#333'),
                borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', color: '#e5e5e5',
              }}
            >
              <Radio active={active} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{t.label}</div>
                <div style={{ fontSize: 11, color: '#888' }}>
                  {tokens_label}
                  {cost_label && <> · {cost_label}</>}
                  {' · '}{t.trials} · {t.time}
                </div>
              </div>
            </button>
          )
        })}
        <button
          onClick={() => onTier('custom')}
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '10px 12px', textAlign: 'left',
            backgroundColor: tier === 'custom' ? 'rgba(124, 58, 237, 0.12)' : '#262626',
            border: '1px solid ' + (tier === 'custom' ? '#7c3aed' : '#333'),
            borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', color: '#e5e5e5',
          }}
        >
          <Radio active={tier === 'custom'} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Custom</div>
            {tier === 'custom' && (
              <input
                type="number"
                value={customTokens}
                onChange={e => onCustomTokens(Math.max(0, Number(e.target.value) || 0))}
                style={{
                  marginTop: 4, width: 120,
                  background: '#1a1a1a', color: '#e5e5e5', border: '1px solid #333',
                  borderRadius: 4, padding: '4px 6px', fontSize: 12,
                }}
              />
            )}
          </div>
        </button>
      </div>
      <div style={{
        marginTop: 12, padding: '8px 10px',
        backgroundColor: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 6,
        fontSize: 12, color: '#aaa',
      }}>
        Selected: <b>{tokensLabel}</b>{costLabel && <> · <b>{costLabel}</b></>}
      </div>
    </div>
  )
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

function Toggle({
  label, description, checked, onChange, disabled = false,
}: {
  label: string; description?: string;
  checked: boolean; onChange?: (b: boolean) => void;
  disabled?: boolean
}) {
  return (
    <button
      onClick={() => !disabled && onChange?.(!checked)}
      disabled={disabled}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10,
        padding: '8px 10px', width: '100%', textAlign: 'left',
        backgroundColor: checked && !disabled ? 'rgba(124, 58, 237, 0.08)' : 'transparent',
        border: '1px solid ' + (checked && !disabled ? 'rgba(124, 58, 237, 0.3)' : '#2a2a2a'),
        borderRadius: 6, cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1, marginBottom: 6, fontFamily: 'inherit', color: '#e5e5e5',
      }}
    >
      <span style={{
        width: 16, height: 16, borderRadius: 4, marginTop: 2,
        background: checked ? '#7c3aed' : 'transparent',
        border: '1.5px solid ' + (checked ? '#7c3aed' : '#555'),
        flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {checked && <span style={{ color: '#fff', fontSize: 11 }}>✓</span>}
      </span>
      <div>
        <div style={{ fontSize: 12, fontWeight: 500 }}>{label}</div>
        {description && <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>{description}</div>}
      </div>
    </button>
  )
}

function Radio({ active }: { active: boolean }) {
  return (
    <span style={{
      width: 14, height: 14, borderRadius: '50%',
      border: '2px solid ' + (active ? '#7c3aed' : '#555'),
      backgroundColor: active ? '#7c3aed' : 'transparent',
      flexShrink: 0,
    }} />
  )
}

function btn(enabled: boolean, color?: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
    color: enabled ? '#e5e5e5' : '#555',
    backgroundColor: color ? color : '#2a2a2a',
    border: `1px solid ${color || '#3a3a3a'}`,
    borderRadius: 5,
    cursor: enabled ? 'pointer' : 'not-allowed',
    opacity: enabled ? 1 : 0.5,
  }
}
