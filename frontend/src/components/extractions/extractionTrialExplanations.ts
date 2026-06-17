// Plain-English explanations for EXTRACTION optimization trial settings.
//
// An extraction "trial" runs the field extraction with one specific combination
// of engine settings (strategy, thinking, consensus, chunking, prompt style,
// model) against the test documents and scores how accurately it pulled each
// field. These helpers turn a trial's raw `config_override` into language a
// non-expert can read: what each knob is, what value this trial used, and why
// it matters.
//
// Unlike KB's flat config, the extraction config is nested (one_pass/two_pass
// carry their own thinking/structured flags), so the readers below normalize
// the shape before explaining it. Pure functions only — no React.

import type { ExtractionTrial } from '../../api/extractions'

type Config = Record<string, unknown>

export interface ExtractionParamExplanation {
  key: string
  label: string
  value: string
  why: string
}

// --- config shape readers (normalize the nested one_pass/two_pass shape) ------

function asObj(v: unknown): Record<string, unknown> | undefined {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : undefined
}

/** 'one_pass' | 'two_pass' | null — inferred from `mode` or the nested keys. */
export function getStrategy(c: Config): 'one_pass' | 'two_pass' | null {
  if (c.mode === 'one_pass' || c.mode === 'two_pass') return c.mode
  if (asObj(c.one_pass)) return 'one_pass'
  if (asObj(c.two_pass)) return 'two_pass'
  return null
}

/** Whether extended thinking is on, reading whichever pass shape is present. */
export function getThinking(c: Config): boolean {
  const op = asObj(c.one_pass)
  if (op && typeof op.thinking === 'boolean') return op.thinking
  const tp = asObj(c.two_pass)
  if (tp) {
    const p1 = asObj(tp.pass_1)
    const p2 = asObj(tp.pass_2)
    return Boolean(p1?.thinking || p2?.thinking)
  }
  return false
}

/** Structured-output flag, or null when the config doesn't pin it. */
export function getStructured(c: Config): boolean | null {
  const op = asObj(c.one_pass)
  if (op && typeof op.structured === 'boolean') return op.structured
  const tp = asObj(c.two_pass)
  const p2 = asObj(tp?.pass_2)
  if (p2 && typeof p2.structured === 'boolean') return p2.structured
  return null
}

/** Whether consensus (3× majority-vote) is enabled. */
export function getConsensus(c: Config): boolean {
  const r = asObj(c.repetition)
  return Boolean(r?.enabled)
}

/** Fields-per-chunk when chunking is on, else null. */
export function getChunkSize(c: Config): number | null {
  const ch = asObj(c.chunking)
  if (ch?.enabled && typeof ch.max_keys_per_chunk === 'number') {
    return ch.max_keys_per_chunk
  }
  return null
}

export function getPromptVariant(c: Config): string {
  return typeof c.prompt_variant === 'string' && c.prompt_variant ? c.prompt_variant : 'standard'
}

export function getModel(c: Config): string | null {
  return typeof c.model === 'string' && c.model ? c.model : null
}

export function formatModel(model: string | null): string {
  return model || 'Default model'
}

// --- parameter breakdown ------------------------------------------------------

const STRATEGY_LABEL: Record<string, string> = {
  one_pass: 'One pass', two_pass: 'Two passes',
}
const PROMPT_LABEL: Record<string, string> = {
  strict: 'Strict', instructive: 'Instructive', standard: 'Standard',
}

/**
 * Per-parameter breakdown for an extraction trial's config — one entry per
 * knob, each with the chosen value and a plain-English note on why it matters.
 * Always returns the full set so the reader sees every lever, including the
 * ones left at their default ("Off"/"Standard").
 */
export function explainExtractionParameters(config: Config): ExtractionParamExplanation[] {
  const strategy = getStrategy(config)
  const thinking = getThinking(config)
  const structured = getStructured(config)
  const consensus = getConsensus(config)
  const chunk = getChunkSize(config)
  const prompt = getPromptVariant(config)
  const model = getModel(config)

  const params: ExtractionParamExplanation[] = [
    {
      key: 'strategy',
      label: 'Strategy',
      value: strategy ? STRATEGY_LABEL[strategy] : 'Default',
      why: strategy === 'two_pass'
        ? 'Two passes — a first pass drafts the values, a second pass re-checks ' +
          'and corrects them against the document. Slower, but usually more ' +
          'accurate on tricky fields.'
        : strategy === 'one_pass'
          ? 'One pass — the AI reads the document once and fills every field in ' +
            'a single go. Faster and cheaper.'
          : 'Uses the standard extraction strategy.',
    },
    {
      key: 'thinking',
      label: 'Extended thinking',
      value: thinking ? 'On' : 'Off',
      why: thinking
        ? 'The model works through its reasoning before committing to each ' +
          'value. Helps on fields that need inference or math, at extra time and cost.'
        : 'The model answers directly without an explicit reasoning step — faster and cheaper.',
    },
    {
      key: 'consensus',
      label: 'Consensus (3× runs)',
      value: consensus ? 'On' : 'Off',
      why: consensus
        ? 'Runs the extraction three times and keeps the most common value for ' +
          'each field. Costs about 3× but irons out one-off mistakes, raising consistency.'
        : 'Extracts once. Faster and cheaper, but more exposed to one-off slips.',
    },
    {
      key: 'chunking',
      label: 'Field chunking',
      value: chunk != null ? `${chunk} fields per batch` : 'Off',
      why: chunk != null
        ? `Extracts the fields in batches of ${chunk} so the model concentrates ` +
          'on fewer fields at a time. Helps accuracy when there are many fields.'
        : 'All fields are extracted together in one prompt.',
    },
    {
      key: 'prompt_variant',
      label: 'Prompt style',
      value: PROMPT_LABEL[prompt] ?? prompt,
      why: prompt === 'strict'
        ? 'Tells the model to return a value only when the document clearly ' +
          'supports it, cutting down on guesses.'
        : prompt === 'instructive'
          ? 'Gives the model extra step-by-step guidance on how to locate each field.'
          : 'The default extraction prompt.',
    },
    {
      key: 'model',
      label: 'Extraction model',
      value: formatModel(model),
      why: 'The AI model doing the extracting. Stronger models read tricky ' +
        'documents better but cost more and run slower.',
    },
  ]

  // Structured output is only meaningful when the config pins it; show it then.
  if (structured != null) {
    params.splice(2, 0, {
      key: 'structured',
      label: 'Structured output',
      value: structured ? 'On' : 'Off',
      why: structured
        ? 'The model returns values in a strict machine-readable format, so ' +
          'there’s less guesswork parsing its output.'
        : 'The model writes its answer as text that the system then parses.',
    })
  }

  return params
}

/** Terse one-liner for the trials-table row (and verbose for the progress card). */
export function summariseExtractionTrialConfig(config: Config, verbose = false): string {
  const strategy = getStrategy(config)
  const bits: string[] = []

  if (strategy) bits.push(verbose ? STRATEGY_LABEL[strategy].toLowerCase() : strategy.replace('_', '-'))
  const model = getModel(config)
  if (model) bits.push(model)
  if (getThinking(config)) bits.push(verbose ? 'with thinking' : 'thinking')
  if (getConsensus(config)) bits.push(verbose ? '3× consensus' : 'consensus')
  const chunk = getChunkSize(config)
  if (chunk != null) bits.push(verbose ? `chunks of ${chunk} fields` : `chunk=${chunk}`)
  const prompt = getPromptVariant(config)
  if (prompt !== 'standard') bits.push(verbose ? `${prompt} prompt` : prompt)

  return bits.length > 0 ? bits.join(' · ') : 'default settings'
}

/** A single plain-English "what this trial tried" sentence. */
export function describeExtractionTrialPlainly(config: Config): string {
  const strategy = getStrategy(config)
  const model = formatModel(getModel(config))
  const passes = strategy === 'two_pass' ? 'two passes'
    : strategy === 'one_pass' ? 'one pass'
    : 'the default strategy'

  const clauses: string[] = [`Extracted every field in ${passes} with ${model}`]
  if (getThinking(config)) clauses.push('thinking through each field')
  const chunk = getChunkSize(config)
  if (chunk != null) clauses.push(`in batches of ${chunk} fields`)
  const prompt = getPromptVariant(config)
  if (prompt !== 'standard') clauses.push(`using the ${prompt} prompt`)
  if (getConsensus(config)) clauses.push('and ran the whole thing 3× to majority-vote the answers')

  return clauses.join(', ') + '.'
}

/** One-line "why this trial matters" from its lift vs. the current settings. */
export function explainExtractionOutcome(trial: ExtractionTrial): string {
  const scorePct = Math.round((trial.score ?? 0) * 100)
  if (trial.status === 'failed') {
    return 'This configuration failed to run, so it has no score to compare.'
  }
  const lift = trial.lift_vs_default
  if (lift == null) {
    return `This configuration scored ${scorePct}% overall on the test documents.`
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
  return `This configuration scored ${scorePct}% — roughly tied with your current settings.`
}
