import { apiFetch } from './client'
import type { PageSpot } from '../components/artifacts/PublishedPageContent'

/** A viewer's question or flag on a page, and the owner's answer. */
export interface PageFeedbackItem {
  uuid: string
  revision: string
  version: number
  anchor: PageSpot
  message: string
  kind: 'question' | 'flag'
  status: 'open' | 'answered' | 'resolved'
  author_kind: 'member' | 'public'
  author_name: string
  /** Owner only: a public asker's email, if they left one. */
  author_email?: string | null
  created_at: string
  answer: { text: string; by_name: string; at: string; on_page: boolean } | null
}

export interface FeedbackSettings { public_questions: boolean; contact: string | null }

export type PageFeedbackList =
  | { role: 'owner'; items: PageFeedbackItem[]; settings: FeedbackSettings; shared_by: string }
  | { role: 'member'; items: PageFeedbackItem[]; shared_by: string }

export const listPageFeedback = (uuid: string, revision: string) =>
  apiFetch<PageFeedbackList>(`/api/pages/${encodeURIComponent(uuid)}/feedback?revision=${encodeURIComponent(revision)}`)

export const askPageOwner = (uuid: string, body: { revision: string; anchor: PageSpot | null; message: string; kind: 'question' | 'flag' }) =>
  apiFetch<PageFeedbackItem>(`/api/pages/${encodeURIComponent(uuid)}/feedback`, { method: 'POST', body: JSON.stringify({ ...body, anchor: body.anchor ?? {} }) })

export const answerPageFeedback = (uuid: string, feedback: string, text: string, onPage: boolean) =>
  apiFetch<PageFeedbackItem>(`/api/pages/${encodeURIComponent(uuid)}/feedback/${encodeURIComponent(feedback)}/answer`, { method: 'POST', body: JSON.stringify({ text, on_page: onPage }) })

export const setPageFeedbackStatus = (uuid: string, feedback: string, status: PageFeedbackItem['status']) =>
  apiFetch<PageFeedbackItem>(`/api/pages/${encodeURIComponent(uuid)}/feedback/${encodeURIComponent(feedback)}/status`, { method: 'POST', body: JSON.stringify({ status }) })

export const updatePageFeedbackSettings = (uuid: string, changes: Partial<FeedbackSettings>) =>
  apiFetch<{ settings: FeedbackSettings; shared_by: string }>(`/api/pages/${encodeURIComponent(uuid)}/feedback-settings`, { method: 'PUT', body: JSON.stringify(changes) })

export const getPublicPageFeedback = (token: string) =>
  apiFetch<{ shared_by: string; public_questions: boolean; items: PageFeedbackItem[] }>(`/api/pages/public/${encodeURIComponent(token)}/feedback`)

export const askPublicPageOwner = (token: string, body: { anchor: PageSpot | null; message: string; kind: 'question' | 'flag'; name: string; email: string; website: string }) =>
  apiFetch<{ ok: boolean }>(`/api/pages/public/${encodeURIComponent(token)}/feedback`, { method: 'POST', body: JSON.stringify({ ...body, anchor: body.anchor ?? {} }) })

/** A Request changes message built from a viewer's question. */
export function asChangeRequest(item: PageFeedbackItem): string {
  const lead = item.anchor.text ? `On “${item.anchor.text}” (version ${item.version}), ` : `On version ${item.version}, `
  return `${lead}${item.author_name} asked: ${item.message}\n\nUpdate the page to address this.`
}
