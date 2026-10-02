import { useEffect, useState, type ReactNode } from 'react'
import {
  getKBOptimizationModels,
  type KBOptimizationModelPlan,
  type KBOptimizationRun,
} from '../../api/knowledge'
import { TermDef } from '../shared/TermDef'

/** Who judges, who answers today, and who competes in a KB tuning run.
 *
 * The wizard always shows the one-line summary; the judge dropdown and the
 * challenger checklist sit behind an Advanced toggle. ``judgeModel`` /
 * ``challengerModels`` null mean the defaults: the admin's Validation grader
 * judges and every eligible model competes. */
export function TuningModelsPicker({
  kbUuid, judgeModel, challengerModels, onChange, questionCount, trialsLabel,
}: {
  kbUuid: string
  judgeModel: string | null
  challengerModels: string[] | null
  onChange: (judgeModel: string | null, challengerModels: string[] | null) => void
  questionCount: number
  trialsLabel: string
}) {
  const [plan, setPlan] = useState<KBOptimizationModelPlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [advanced, setAdvanced] = useState(judgeModel != null || challengerModels != null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    getKBOptimizationModels(kbUuid, judgeModel)
      .then(p => {
        if (cancelled) return
        setPlan(p)
        // A new judge can make a picked challenger ineligible (same family);
        // drop it so the run isn't rejected for it.
        if (challengerModels != null) {
          const ok = new Set(p.models.filter(m => m.eligible).map(m => m.name))
          const kept = challengerModels.filter(m => ok.has(m))
          if (kept.length !== challengerModels.length) onChange(judgeModel, kept)
        }
      })
      .catch(e => { if (!cancelled) setError((e as Error).message || 'Could not load models.') })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbUuid, judgeModel])

  if (error) {
    return <div style={{ fontSize: 12, color: '#f87171' }}>{error}</div>
  }
  if (!plan) {
    return <div style={{ fontSize: 12, color: '#888' }}>Loading models…</div>
  }

  const eligible = plan.models.filter(m => m.eligible).map(m => m.name)
  // A custom pick survives a judge change only where it is still eligible.
  const chosen = challengerModels == null
    ? eligible
    : challengerModels.filter(m => eligible.includes(m))

  const setJudge = (name: string) => {
    onChange(name === plan.validation_grader ? null : name, challengerModels)
  }
  const toggleChallenger = (name: string) => {
    const next = chosen.includes(name) ? chosen.filter(m => m !== name) : [...chosen, name]
    const isAll = next.length === eligible.length
    onChange(judgeModel, isAll ? null : next)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <ModelPlanSummary
        judge={plan.judge_model}
        judgeIsGrader={judgeModel == null}
        current={plan.current_model}
        challengers={chosen}
        questionCount={questionCount}
        trialsLabel={trialsLabel}
      />
      {plan.judge_model_fallback && (
        <div style={{ fontSize: 11, color: '#fbbf24' }}>
          The Validation grader is set to {plan.judge_model_fallback.configured}, which isn't
          configured any more, so {plan.judge_model_fallback.used} judges instead.
        </div>
      )}
      {plan.current_shares_judge_family && (
        <div style={{ fontSize: 11, color: '#fbbf24' }}>
          Your current model ({plan.current_model}) is from the judge's family, so the judge may
          rate your current settings a little high. Pick a judge from another family to avoid this.
        </div>
      )}
      {chosen.length === 0 && (
        <div style={{ fontSize: 11, color: '#bbb' }}>
          No challenger models — tuning only tries retrieval and prompt settings
          on {plan.current_model}.
        </div>
      )}

      <button
        type="button"
        onClick={() => setAdvanced(v => !v)}
        aria-expanded={advanced}
        style={{
          alignSelf: 'flex-start', padding: 0, background: 'transparent', border: 'none',
          color: '#a78bfa', fontSize: 11, fontWeight: 600, fontFamily: 'inherit', cursor: 'pointer',
        }}
      >
        {advanced ? '▾' : '▸'} Advanced: choose the judge and challengers
      </button>

      {advanced && (
        <div style={{
          display: 'flex', flexDirection: 'column', gap: 10, padding: '10px 12px',
          backgroundColor: '#181818', border: '1px solid #2a2a2a', borderRadius: 6,
        }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, color: '#bbb' }}>
            Judge
            <select
              value={plan.judge_model}
              onChange={e => setJudge(e.target.value)}
              style={{
                padding: '5px 8px', fontSize: 12, fontFamily: 'inherit', color: '#e5e5e5',
                backgroundColor: '#262626', border: '1px solid #333', borderRadius: 4,
              }}
            >
              {plan.models.map(m => (
                <option key={m.name} value={m.name}>
                  {m.name}{m.name === plan.validation_grader ? ' (Validation grader — default)' : ''}
                </option>
              ))}
            </select>
          </label>

          <fieldset style={{ margin: 0, padding: 0, border: 'none' }}>
            <legend style={{ fontSize: 11, color: '#bbb', marginBottom: 4 }}>Challengers</legend>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {plan.models.map(m => (
                <label
                  key={m.name}
                  title={m.ineligible_reason ?? undefined}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 12,
                    color: m.eligible ? '#e5e5e5' : '#666',
                    cursor: m.eligible ? 'pointer' : 'not-allowed',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={m.eligible && chosen.includes(m.name)}
                    disabled={!m.eligible}
                    onChange={() => toggleChallenger(m.name)}
                    style={{ marginTop: 2 }}
                  />
                  <span>
                    {m.name}{m.is_current ? ' (current)' : ''}
                    {m.ineligible_reason && (
                      <span style={{ display: 'block', fontSize: 11, color: '#777' }}>
                        {m.ineligible_reason}
                      </span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>
      )}
    </div>
  )
}

function ModelPlanSummary({
  judge, judgeIsGrader, current, challengers, questionCount, trialsLabel,
}: {
  judge: string
  judgeIsGrader: boolean
  current: string
  challengers: string[]
  questionCount: number
  trialsLabel: string
}) {
  const rows: [string, ReactNode][] = [
    [
      'Judge',
      <>{judge}{judgeIsGrader && <span style={{ color: '#888' }}> · Validation grader</span>}</>,
    ],
    ['Current answer model', current],
    ['Challengers', challengers.length > 0 ? challengers.join(', ') : 'none'],
    ['Trials', trialsLabel],
    ['Questions', String(questionCount)],
  ]
  return (
    <div
      data-testid="tuning-plan-summary"
      style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '3px 12px', fontSize: 12 }}
    >
      {rows.map(([label, value]) => (
        <div key={label} style={{ display: 'contents' }}>
          <span style={{ color: '#888' }}>
            {label === 'Judge' ? <TermDef term="judge">Judge</TermDef> : label}
          </span>
          <span style={{ color: '#e5e5e5', wordBreak: 'break-word' }}>{value}</span>
        </div>
      ))}
    </div>
  )
}

/** One line on a finished run: who judged, who answered, who competed. */
export function TuningModelsLine({ run }: { run: KBOptimizationRun }) {
  if (!run.judge_model) return null
  const parts = [`Judged by ${run.judge_model}`]
  if (run.judge_source === 'validation_grader') parts[0] += ' (Validation grader)'
  if (run.current_model) parts.push(`current model ${run.current_model}`)
  if (run.challenger_models) {
    parts.push(
      run.challenger_models.length > 0
        ? `challengers ${run.challenger_models.join(', ')}`
        : 'no challenger models',
    )
  }
  return (
    <div data-testid="tuning-models-line" style={{ fontSize: 11, color: '#999', lineHeight: 1.5 }}>
      {parts.join(' · ')}
    </div>
  )
}
