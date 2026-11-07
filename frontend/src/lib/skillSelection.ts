import type { SkillSnapshot } from '../types/chat'

/** A persisted selection receipt is proof of a change; model arguments are not.
 * undefined means no valid receipt, while null confirms removal. */
export function completedSkillSelection(content: unknown): SkillSnapshot | null | undefined {
  if (!content || typeof content !== 'object') return undefined
  const result = content as Record<string, unknown>
  if (result.status !== 'selected' || result.needs_confirmation || result.error) return undefined
  if (result.active_skill === null) return null
  const skill = result.active_skill as Partial<SkillSnapshot> | undefined
  if (skill && typeof skill.uuid === 'string' && typeof skill.title === 'string' &&
    typeof skill.version === 'string' && typeof skill.instructions === 'string') return skill as SkillSnapshot
  return undefined
}
