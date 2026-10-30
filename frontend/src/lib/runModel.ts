/**
 * The "Model: …" line a workflow run shows. Prefers the models the run's steps
 * actually ran on (recorded when the run is built, after step overrides); runs
 * from before that was recorded fall back to the run's model. Null when the
 * run recorded neither.
 */
export function runModelLabel(run: { model?: string | null; models_used?: string[] | null } | null | undefined): string | null {
  const used = (run?.models_used ?? []).filter(Boolean)
  if (used.length > 1) return `Models: ${used.join(', ')}`
  const one = used[0] || run?.model
  return one ? `Model: ${one}` : null
}
