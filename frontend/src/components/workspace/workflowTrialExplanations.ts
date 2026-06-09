// Plain-English explanations for WORKFLOW optimization trial settings.
//
// A workflow "trial" re-runs the whole workflow with tweaked settings on one or
// more of its LLM steps (each step can get a different model and prompt style)
// and scores how well the run did against the test inputs. Unlike KB/extraction
// — which tune one flat config — a workflow trial's config is *per step*, so the
// explanation reads step-by-step. Pure functions only — no React.

import type {
  WorkflowOptimizationTrial,
  WorkflowStepOverride,
} from '../../api/workflows'

export interface PromptVariantInfo {
  label: string
  why: string
}

/** What each workflow prompt variant tells a step to do (mirrors
 * backend workflow_prompt_variants.PROMPT_VARIANTS). */
export const PROMPT_VARIANTS: Record<string, PromptVariantInfo> = {
  default: {
    label: 'Default',
    why: 'The step’s normal prompt, unchanged.',
  },
  concise: {
    label: 'Concise',
    why: 'Tells the step to answer briefly and directly, with no preamble.',
  },
  detailed: {
    label: 'Detailed',
    why: 'Tells the step to take its time and give a thorough, complete response.',
  },
  cot: {
    label: 'Step-by-step',
    why: 'Tells the step to reason through the problem before answering — helps on reasoning-heavy steps.',
  },
  strict: {
    label: 'Strict',
    why: 'Tells the step to follow instructions literally, with no extra commentary or caveats.',
  },
}

export function promptVariantLabel(variant: string | null | undefined): string {
  if (!variant) return 'Default'
  return PROMPT_VARIANTS[variant]?.label ?? variant
}

export function formatModel(model: string | null | undefined): string {
  return model || 'Default model'
}

export interface StepExplanation {
  step: string
  model: string
  promptVariant: string
  /** Why the chosen prompt variant matters (empty for the default variant). */
  promptWhy: string
}

type Config = { step_overrides?: Record<string, WorkflowStepOverride> }

/** Normalize a trial's config into a per-step explanation list. */
export function explainWorkflowSteps(config: Config): StepExplanation[] {
  const overrides = config.step_overrides ?? {}
  return Object.entries(overrides).map(([step, ov]) => {
    const variant = ov.prompt_variant ?? 'default'
    return {
      step,
      model: formatModel(ov.model),
      promptVariant: promptVariantLabel(variant),
      promptWhy: variant && variant !== 'default' ? (PROMPT_VARIANTS[variant]?.why ?? '') : '',
    }
  })
}

/** Terse one-liner for the trials-table row. */
export function summariseWorkflowTrialConfig(config: Config, verbose = false): string {
  const steps = explainWorkflowSteps(config)
  if (steps.length === 0) return 'current settings'

  const models = Array.from(new Set(
    steps.map(s => s.model).filter(m => m !== 'Default model'),
  ))
  const variants = Array.from(new Set(
    steps.map(s => s.promptVariant).filter(v => v !== 'Default'),
  ))

  const bits: string[] = [
    verbose
      ? `${steps.length} step${steps.length === 1 ? '' : 's'} tuned`
      : `${steps.length} step${steps.length === 1 ? '' : 's'}`,
  ]
  for (const m of models) bits.push(m)
  for (const v of variants) bits.push(verbose ? `${v.toLowerCase()} prompt` : v.toLowerCase())
  return bits.join(' · ')
}

/** A single plain-English "what this trial tried" sentence. */
export function describeWorkflowTrialPlainly(config: Config): string {
  const steps = explainWorkflowSteps(config)
  if (steps.length === 0) {
    return 'Ran the workflow with its current settings on every step.'
  }
  const n = steps.length
  const lead = `This trial changed settings on ${n} of the workflow’s step${n === 1 ? '' : 's'}`
  // Name the first couple of steps concretely; the per-step list below has the rest.
  const examples = steps.slice(0, 2).map(s => {
    const promptBit = s.promptVariant === 'Default' ? '' : ` with the ${s.promptVariant.toLowerCase()} prompt`
    return `“${s.step}” → ${s.model}${promptBit}`
  })
  const tail = n > 2 ? ', and others' : ''
  return `${lead}: ${examples.join('; ')}${tail}.`
}

/** One-line "why this trial matters" from its lift vs. the current settings. */
export function explainWorkflowOutcome(trial: WorkflowOptimizationTrial): string {
  const scorePct = Math.round((trial.score ?? 0) * 100)
  if (trial.status === 'failed') {
    return 'This configuration failed to run, so it has no score to compare.'
  }
  const lift = trial.lift_vs_default
  if (lift == null) {
    return `This configuration scored ${scorePct}% across the test inputs.`
  }
  const liftPts = Math.round(lift * 100)
  if (liftPts > 0) {
    return `This configuration scored ${scorePct}% — about ${liftPts} point` +
      `${liftPts === 1 ? '' : 's'} higher than your current settings. The ` +
      'per-step changes below are what it did differently to get there.'
  }
  if (liftPts < 0) {
    return `This configuration scored ${scorePct}% — about ${Math.abs(liftPts)} point` +
      `${Math.abs(liftPts) === 1 ? '' : 's'} lower than your current settings, ` +
      'so the per-step changes below didn’t help here.'
  }
  return `This configuration scored ${scorePct}% — roughly tied with your current settings.`
}
