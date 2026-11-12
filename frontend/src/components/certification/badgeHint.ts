import { LEVEL_CONFIG, LEVEL_THRESHOLDS } from './constants'

/** Hover text for the certification badge in the Activity panel: what the
 *  level and the points mean, and how far the next level is. */
export function certificationBadgeHint({ level, xp, certified, title, levels }: {
  level: string
  xp: number
  certified: boolean
  /** The credential's name, shown once certified. */
  title: string
  /** The course's own level thresholds; the legacy course's when absent. */
  levels?: { name: string; xp: number }[]
}): string {
  const earning = 'XP (experience points) is earned by completing certification modules, and each level is reached at a set XP total.'
  if (xp <= 0 && !certified) {
    return `Get Certified: the certification course. ${earning} Click to start.`
  }
  const label = (name: string) => LEVEL_CONFIG[name]?.label ?? name.charAt(0).toUpperCase() + name.slice(1)
  const points = `${xp.toLocaleString()} XP`
  if (certified) {
    return `${title}: you have completed the certification course, with ${points}. ${earning} Click to open certification.`
  }
  const next = (levels?.length ? levels : LEVEL_THRESHOLDS).find(l => l.xp > xp)
  const ahead = next
    ? `Next level: ${label(next.name)} at ${next.xp.toLocaleString()} XP (${(next.xp - xp).toLocaleString()} XP to go).`
    : 'This is the highest level.'
  return `Certification level: ${label(level)}, with ${points}. ${earning} ${ahead} Click to open your progress.`
}
