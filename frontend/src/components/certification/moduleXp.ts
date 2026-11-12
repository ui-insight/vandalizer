/** How a module's XP reads before it is completed.
 *
 * Completing a module awards its base XP plus a bonus for each star earned.
 * Listed at the base alone, AI Literacy showed 50 XP and awarded 125 for 3
 * stars, and nothing said stars add XP. A course with no star bonus (5.0)
 * reads as its base XP. */

// The original course's rubric, for the panel when no versioned course is pinned.
export const LEGACY_STAR_BONUS_XP = 25
export const LEGACY_MAXIMUM_STARS = 3

export function moduleMaxXp(baseXp: number, starBonusXp: number, maximumStars: number): number {
  return baseXp + Math.max(0, starBonusXp) * Math.max(0, maximumStars)
}

/** "50–125 XP", or "100 XP" when stars add nothing. */
export function moduleXpLabel(baseXp: number, maxXp?: number | null): string {
  return maxXp != null && maxXp > baseXp ? `${baseXp}–${maxXp} XP` : `${baseXp} XP`
}

/** The rule behind the range, for a tooltip or screen reader. */
export function moduleXpExplanation(baseXp: number, maxXp?: number | null, starBonusXp?: number | null): string {
  if (maxXp == null || maxXp <= baseXp) return `${baseXp} XP for completing this module`
  const perStar = starBonusXp ? ` plus ${starBonusXp} XP for each star you earn` : ' plus a bonus for each star you earn'
  return `${baseXp} XP for completing this module,${perStar}: up to ${maxXp} XP`
}
