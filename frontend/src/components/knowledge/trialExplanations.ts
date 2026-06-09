// Plain-English explanations for KB optimization trial settings.
//
// A "trial" runs the knowledge base through one specific combination of search
// + answer settings and scores how well it answered the test questions. The
// optimizer tries many combinations to find the best one. These helpers turn a
// trial's raw config into language a non-expert (e.g. a new QA reviewer) can
// read: what each knob is, what value this trial used, and *why it matters*.
//
// Pure functions only — no React — so they're trivially unit-testable and can
// be reused by tooltips, the running-state summary, or future surfaces.

import type { OptimizationTrial, TrialConfig } from '../../api/knowledge'

export interface ParamExplanation {
  /** Config key this explains (stable id for React keys / tests). */
  key: string
  /** Human-friendly name, e.g. "Passages read". */
  label: string
  /** The value this trial used, formatted for display, e.g. "8" or "Strict". */
  value: string
  /** One-line "why this setting matters / what it trades off". */
  why: string
}

/** Format a model id for humans — null/empty means "the KB's default model". */
export function formatModel(model: string | null | undefined): string {
  if (!model) return 'Default model'
  return model
}

/** Default a trial's optional sweep axes the way the backend does. */
function withDefaults(config: TrialConfig): Required<Pick<TrialConfig,
  'rerank' | 'answer_temperature'>> & TrialConfig {
  return {
    ...config,
    rerank: config.rerank ?? 'off',
    answer_temperature: config.answer_temperature ?? 0.0,
  }
}

/**
 * Build the per-parameter breakdown for a trial's config — one entry per knob,
 * each with the chosen value and a plain-English note on why it matters.
 *
 * Order is intentional: the settings with the biggest, most intuitive impact on
 * answer quality come first.
 */
export function explainTrialParameters(config: TrialConfig): ParamExplanation[] {
  const c = withDefaults(config)

  const promptWhy: Record<string, string> = {
    default: 'Balanced — answers normally from whatever the search turned up.',
    strict: "Cautious — only answers when the passages clearly back it up, and says “I don’t know” otherwise. Cuts down on made-up answers.",
    concise: 'Brief — keeps answers short and to the point, trimming extra explanation.',
  }
  const promptLabel: Record<string, string> = {
    default: 'Balanced', strict: 'Strict', concise: 'Concise',
  }

  const params: ParamExplanation[] = [
    {
      key: 'k',
      label: 'Passages read',
      value: String(c.k),
      why:
        `The AI searches your documents and reads the top ${c.k} matching ` +
        'passages before answering. More passages give it more context to work ' +
        'with, but also raise the chance of pulling in off-topic text that ' +
        'muddies the answer.',
    },
    {
      key: 'model',
      label: 'Answering model',
      value: formatModel(c.model),
      why:
        'The AI model that actually writes the answer from the retrieved ' +
        'passages. Stronger models reason better but are slower and cost more.',
    },
    {
      key: 'prompt_variant',
      label: 'Answer style',
      value: promptLabel[c.prompt_variant] ?? c.prompt_variant,
      why: promptWhy[c.prompt_variant] ??
        'Controls how loosely or strictly the AI is allowed to answer.',
    },
    {
      key: 'query_rewriting',
      label: 'Query rewriting',
      value: c.query_rewriting ? 'On' : 'Off',
      why: c.query_rewriting
        ? 'Before searching, the AI rephrases and expands the question so it ' +
          'can find documents that use different wording. Helps on vaguely ' +
          'phrased questions, but can occasionally drift off-topic.'
        : 'The question is searched exactly as written — no rephrasing. ' +
          'Predictable, but may miss documents that word things differently.',
    },
    {
      key: 'rerank',
      label: 'Reranking',
      value: c.rerank === 'off' ? 'Off' : 'AI rerank',
      why: c.rerank === 'off'
        ? 'Passages are used in the order the initial search returned them.'
        : 'After the first search, a second AI pass re-orders the passages by ' +
          'how well they actually answer the question, pushing the best ones to ' +
          'the top. Improves precision at extra cost and time.',
    },
    {
      key: 'source_label_visibility',
      label: 'Source labels',
      value: c.source_label_visibility ? 'Visible' : 'Hidden',
      why: c.source_label_visibility
        ? 'The AI can see each passage’s document title while answering, ' +
          'which can help it weigh and cite trustworthy sources.'
        : 'Document titles are hidden, forcing the AI to judge each passage ' +
          'purely on its content rather than where it came from.',
    },
    {
      key: 'answer_temperature',
      label: 'Answer variability',
      value: c.answer_temperature === 0 ? 'Deterministic (0.0)' : `Varied (${c.answer_temperature})`,
      why: c.answer_temperature === 0
        ? 'Temperature 0 — the AI gives the same, most-likely answer every time. ' +
          'Best for factual, repeatable results.'
        : `Temperature ${c.answer_temperature} — the AI varies its wording a ` +
          'little for more natural phrasing, at the cost of some repeatability.',
    },
  ]

  return params
}

/**
 * A single plain-English sentence summarizing what this trial actually did —
 * the "what it tried" headline. Reads like a recipe: search settings first,
 * then how it answered.
 */
export function describeTrialPlainly(config: TrialConfig): string {
  const c = withDefaults(config)
  const clauses: string[] = []

  clauses.push(`read the top ${c.k} passage${c.k === 1 ? '' : 's'}`)
  if (c.query_rewriting) clauses.push('after rephrasing the question to widen the search')
  if (c.rerank !== 'off') clauses.push('re-ranked them with a second AI pass')

  const styleWord = c.prompt_variant === 'strict' ? 'cautious, strict'
    : c.prompt_variant === 'concise' ? 'short, concise'
    : 'balanced'
  let answerClause = `then answered in a ${styleWord} style with ${formatModel(c.model)}`
  if (c.source_label_visibility === false) answerClause += ', without seeing source titles'
  if (c.answer_temperature !== 0) answerClause += `, at temperature ${c.answer_temperature}`
  clauses.push(answerClause)

  // Capitalize the first letter for a clean sentence.
  const sentence = clauses.join(', ')
  return sentence.charAt(0).toUpperCase() + sentence.slice(1) + '.'
}

/** Plain-English reason an early-stopped trial bailed before finishing. */
export function explainEarlyStop(reason: OptimizationTrial['early_stop_reason']): string | null {
  if (reason === 'below_no_kb') {
    return 'Stopped early — its answers were scoring below what the AI manages ' +
      'with no knowledge base at all, so finishing wasn’t worth the cost.'
  }
  if (reason === 'below_best') {
    return 'Stopped early — it was trailing the best configuration so far by ' +
      'enough that finishing wouldn’t have changed the winner.'
  }
  return null
}

/**
 * One-line "why this trial matters" relative to the current settings, derived
 * from its lift. Deliberately avoids claiming *which* knob caused the change —
 * it states the measured result honestly and points the reader at the
 * parameter list for the how.
 */
export function explainTrialOutcome(trial: OptimizationTrial): string {
  const scorePct = Math.round((trial.score ?? 0) * 100)
  const lift = trial.lift_vs_default

  if (trial.status === 'failed') {
    return 'This configuration failed to run, so it has no score to compare.'
  }

  if (lift == null) {
    return `This configuration scored ${scorePct}% on the test questions.`
  }
  const liftPts = Math.round(lift * 100)
  if (liftPts > 0) {
    return `This configuration scored ${scorePct}% — about ${liftPts} point` +
      `${liftPts === 1 ? '' : 's'} higher than your current settings. The ` +
      'parameters below are what it changed to get there.'
  }
  if (liftPts < 0) {
    return `This configuration scored ${scorePct}% — about ${Math.abs(liftPts)} point` +
      `${Math.abs(liftPts) === 1 ? '' : 's'} lower than your current settings, ` +
      'so the changes below didn’t help here.'
  }
  return `This configuration scored ${scorePct}% — roughly tied with your ` +
    'current settings.'
}
