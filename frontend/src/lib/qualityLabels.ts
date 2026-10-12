// How an unmeasured catalog rating is worded wherever it appears (#1013 §5).
// A tier typed by a starter's author is a claim, not a validation result.
export function assertedTierNote(tier: string | null | undefined): string | null {
  if (!tier) return null
  return `Rated ${tier.charAt(0).toUpperCase() + tier.slice(1)} by its author · not yet checked here`
}
