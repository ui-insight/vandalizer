import { apiFetch } from './client'
import type { SkillSnapshot } from '../types/chat'

export const CORE_SKILLS_CHANGED = 'assistant-core-skills-changed'

/** Refresh retained chat panels and other tabs after a settings change. */
export function notifyCoreSkillsChanged() {
  window.dispatchEvent(new Event(CORE_SKILLS_CHANGED))
  try { localStorage.setItem(CORE_SKILLS_CHANGED, `${Date.now()}:${Math.random()}`) } catch { /* Storage may be unavailable. */ }
}

export interface AssistantCapability {
  id: string
  label: string
  description: string
  /** The person's own choice, kept while an admin limit hides it. */
  enabled: boolean
  /** False when an administrator switched it off for everyone. */
  allowed: boolean
  /** False when the deployment has not set it up (web search with no provider). */
  available: boolean
  /** What chat actually has right now. */
  active: boolean
}

export interface AssistantPage {
  capabilities: AssistantCapability[]
  always_on: { id: string; label: string; description: string }[]
  can_set_limits: boolean
}

export function getAssistantCapabilities() {
  return apiFetch<AssistantPage>('/api/assistant/capabilities')
}

/** A person's own switch for one capability. */
export function setAssistantCapability(id: string, on: boolean) {
  return apiFetch<AssistantPage>(`/api/assistant/capabilities/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ on }) })
}

/** Admin only: whether one capability is allowed for everyone on this deployment. */
export function setAssistantCapabilityLimit(id: string, on: boolean) {
  return apiFetch<AssistantPage>(`/api/assistant/capabilities/${encodeURIComponent(id)}/limit`, { method: 'PUT', body: JSON.stringify({ on }) })
}

export interface CoreSkill {
  uuid: string
  /** Null when the Skill was deleted or is no longer shared. */
  title: string | null
  /** Only `ok` is used by chat; the others say why not. */
  status: 'ok' | 'changed' | 'other_team' | 'no_line' | 'unavailable'
  usable: boolean
  problem: string | null
  when_to_use: string
  /** The Skill's current text version; sent back when accepting an edit. */
  version: string | null
  /** The edited text, sent only when status is `changed`, for review. */
  instructions: string | null
}

export interface CoreSkillsPage {
  skills: CoreSkill[]
  max: number
}

export interface CoreSkillChoice {
  uuid: string
  title: string
  /** Empty when the Skill has no When to use line and so cannot be added. */
  when_to_use: string
}

export function getCoreSkills() {
  return apiFetch<CoreSkillsPage>('/api/assistant/core-skills')
}

/** Library Skills that could be added: the same search chat uses to find Skills. */
export function getCoreSkillChoices(search: string) {
  const query = search ? `?search=${encodeURIComponent(search)}` : ''
  return apiFetch<{ choices: CoreSkillChoice[]; more: boolean }>(`/api/assistant/core-skills/choices${query}`)
}

/** Core Skills the person has to act on. One that belongs to another team is
 * working as designed, so it is not counted or announced in chat. */
export function coreSkillsNeedingAttention(page: CoreSkillsPage | null): CoreSkill[] {
  return page?.skills.filter(skill => !skill.usable && skill.status !== 'other_team') ?? []
}

export function getCoreSkillPreview(uuid: string) {
  return apiFetch<SkillSnapshot>(`/api/assistant/core-skills/${encodeURIComponent(uuid)}/preview`)
}

/** Add only the instruction version the person reviewed. */
export function addCoreSkill(uuid: string, version: string) {
  return apiFetch<CoreSkillsPage>('/api/assistant/core-skills', { method: 'POST', body: JSON.stringify({ uuid, version }) })
}

/** Accept an edited Skill's text, naming the version the page showed. */
export function acceptCoreSkill(uuid: string, version: string) {
  return apiFetch<CoreSkillsPage>(`/api/assistant/core-skills/${encodeURIComponent(uuid)}/accept`, { method: 'POST', body: JSON.stringify({ version }) })
}

export function removeCoreSkill(uuid: string) {
  return apiFetch<CoreSkillsPage>(`/api/assistant/core-skills/${encodeURIComponent(uuid)}`, { method: 'DELETE' })
}
