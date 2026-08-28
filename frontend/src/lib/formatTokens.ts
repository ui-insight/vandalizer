/**
 * Render an LLM token count for humans.
 *
 * Trial balances run to millions, and a reader wants the magnitude, not the
 * digits: 2000000 → "2M", 1500000 → "1.5M", 250000 → "250K", 900 → "900".
 */
export function formatTokens(tokens: number | null | undefined): string {
  if (!tokens) return '0'
  if (tokens >= 1_000_000) {
    const millions = tokens / 1_000_000
    return `${Number.isInteger(millions) ? millions : millions.toFixed(1)}M`
  }
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}K`
  return String(tokens)
}
