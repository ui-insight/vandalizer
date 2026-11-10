/**
 * One step at a time for multi-step requests (support ticket: setting up a
 * subaward left Move files, Add to inbox and Save page waiting at once, and a
 * typed "Yes, go ahead" didn't say which card it approved).
 *
 * The server keeps the waiting cards in the order they were prepared
 * (``pending_approvals``). The first is the current step and the only one
 * with buttons; the rest read "Up next". A typed yes approves the current
 * step, exactly like clicking its button; it asks which one only when the
 * current step's card isn't in the chat to point at.
 */
import { createContext, useContext } from 'react'
import type { ChatMessage, PlanTask, ToolResultInfo } from '../../types/chat'

export interface ApprovalQueue {
  /** Waiting cards' tool call ids, in the order the server armed them. */
  pending: readonly string[]
  plan: readonly PlanTask[] | null
}

export const ApprovalQueueContext = createContext<ApprovalQueue>({ pending: [], plan: null })

export function useApprovalQueue(): ApprovalQueue {
  return useContext(ApprovalQueueContext)
}

export interface ApprovalStep {
  /** 0 for the current step. */
  position: number
  current: boolean
  /** "Step 2 of 5", or "" when a lone card isn't part of a plan. */
  heading: string
}

/** Where a waiting card sits in the queue, or null when it isn't waiting. */
export function approvalStep(cardId: string | undefined, queue: ApprovalQueue): ApprovalStep | null {
  const position = cardId ? queue.pending.indexOf(cardId) : -1
  if (position < 0) return null
  const plan = queue.plan ?? []
  let heading = ''
  if (plan.length > 1) {
    const done = plan.filter(t => t.status === 'completed').length
    heading = `Step ${Math.min(done + 1 + position, plan.length)} of ${plan.length}`
  } else if (queue.pending.length > 1) {
    heading = `Step ${position + 1} of ${queue.pending.length}`
  }
  return { position, current: position === 0, heading }
}

const ACTION_LABELS: Record<string, string> = {
  propose_obligations: 'Add to inbox', create_project: 'Create project', move_documents_to_project: 'Move files',
  create_workflow: 'Create workflow', update_workflow: 'Update workflow', create_automation: 'Create automation',
  create_extraction_from_document: 'Create extraction', run_workflow: 'Run workflow', run_validation: 'Run validation',
  approve_workflow_step: 'Approve and continue', reject_workflow_step: 'Reject run',
  complete_certification_module: 'Complete module', create_html_artifact: 'Save page', revise_html_artifact: 'Save page',
}

/** The approve button's label. The preview names its own (approval_label);
 * the map covers chats saved before previews carried one. */
export function cardActionLabel(
  toolName: string, content: Record<string, unknown> | undefined, args: Record<string, unknown> = {},
  fallback: (toolName: string) => string = name => `Approve ${name.replaceAll('_', ' ')}`,
): string {
  if (typeof content?.approval_label === 'string' && content.approval_label) return content.approval_label
  if (toolName === 'select_skill') return args.skill_uuid === null || content?.skill_uuid === null ? 'Remove Skill' : 'Use Skill'
  return ACTION_LABELS[toolName] ?? fallback(toolName)
}

export interface WaitingAction {
  id: string
  label: string
  /** The card's preview text ("Add 3 deadlines to the RA inbox"). */
  detail?: string
  /** A Page card approves with its stored preview, not just its call id. */
  pageApproval?: string
}

function resultsOf(message: ChatMessage): ToolResultInfo[] {
  return [...(message.tool_results ?? []), ...(message.segments?.flatMap(s => s.kind === 'tool_result' ? [s.result] : []) ?? [])]
}

/** The waiting cards, current step first, with the labels their buttons show. */
export function waitingActions(messages: readonly ChatMessage[], pending: readonly string[]): WaitingAction[] {
  const byId = new Map<string, ToolResultInfo>()
  for (const message of messages) for (const result of resultsOf(message)) byId.set(result.tool_call_id, result)
  const actions: WaitingAction[] = pending.flatMap(id => {
    const result = byId.get(id)
    if (!result) return []
    const content = (result.content && typeof result.content === 'object' ? result.content : {}) as Record<string, unknown>
    const pageApproval = ['create_html_artifact', 'revise_html_artifact'].includes(result.tool_name) && typeof content.preview_id === 'string'
      ? content.preview_id : undefined
    const detail = typeof content.preview === 'string' && content.preview ? content.preview : undefined
    return [{ id, label: cardActionLabel(result.tool_name, content), ...(detail ? { detail } : {}), ...(pageApproval ? { pageApproval } : {}) }]
  })
  // Three "Add to inbox" cards need three different buttons.
  const counts = new Map<string, number>()
  for (const a of actions) counts.set(a.label, (counts.get(a.label) ?? 0) + 1)
  const seen = new Map<string, number>()
  return actions.map(a => {
    if ((counts.get(a.label) ?? 0) < 2) return a
    const n = (seen.get(a.label) ?? 0) + 1
    seen.set(a.label, n)
    return { ...a, label: `${a.label} (${n})` }
  })
}

const AFFIRM = new Set(['yes', 'yeah', 'yep', 'yup', 'y', 'sure', 'ok', 'okay', 'k', 'approve', 'approved', 'confirm',
  'confirmed', 'go', 'proceed', 'do'])
const FILLER = new Set(['ahead', 'it', 'please', 'thanks', 'thank', 'you', 'sounds', 'looks', 'good', 'great', 'fine',
  'perfect', 'lets', "let's", 'that', 'thats', "that's", 'this', 'one', 'for', 'with', 'and', 'right', 'sir'])

/** "Yes, go ahead", "ok do it", "approve": a bare yes that names no action. */
export function isPlainApproval(text: string): boolean {
  const words = text.toLowerCase().replace(/[^a-z' ]+/g, ' ').split(/\s+/).filter(Boolean)
  if (!words.length || words.length > 8) return false
  return words.some(w => AFFIRM.has(w)) && words.every(w => AFFIRM.has(w) || FILLER.has(w))
}

export type TypedApproval = { approve: WaitingAction } | { ask: WaitingAction[] } | null

/** What a bare "yes" does: approve the current step (the first waiting card,
 * the one with buttons), or ask which one when that card isn't loaded here.
 * null: let the message go to the Assistant as typed. */
export function typedApprovalTarget(text: string, messages: readonly ChatMessage[], pending: readonly string[]): TypedApproval {
  if (!pending.length || !isPlainApproval(text)) return null
  const actions = waitingActions(messages, pending)
  if (actions[0] && actions[0].id === pending[0]) return { approve: actions[0] }
  return actions.length > 1 ? { ask: actions } : null
}

/** "Which one: Add to inbox or Save page?" */
export function whichOneQuestion(actions: readonly WaitingAction[]): string {
  const labels = actions.map(a => a.label)
  const list = labels.length > 2 ? `${labels.slice(0, -1).join(', ')} or ${labels[labels.length - 1]}` : labels.join(' or ')
  return `Which one: ${list}?`
}
