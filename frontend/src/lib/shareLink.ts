import { useCallback } from 'react'
import { useToast } from '../contexts/ToastContext'
import { mintWorkflowShareToken } from '../api/workflows'
import { mintSearchSetShareToken } from '../api/extractions'
import { ApiError } from '../api/client'

export type ShareableKind = 'workflow' | 'extraction' | 'kb'

export function buildShareUrl(kind: ShareableKind, uuid: string, shareToken?: string): string {
  // A Skill link with a token goes through /shared, which records the person
  // opening it before the Skill is shown.
  if (kind === 'extraction' && shareToken) {
    return `${window.location.origin}/shared?${new URLSearchParams({ item: uuid, token: shareToken }).toString()}`
  }
  const params = new URLSearchParams({ [kind]: uuid })
  if (shareToken) params.set(`${kind}_share_token`, shareToken)
  return `${window.location.origin}/?${params.toString()}`
}

/** What a chat setup link carries: the chips that scope a conversation. */
export interface ChatSetup {
  kbUuids: string[]
  docUuids: string[]
  folderUuids: string[]
  skillUuid?: string
}

/**
 * A link that opens a fresh chat with the same knowledge bases, library
 * documents, folders and Skill attached. The Skill is resolved using the
 * recipient's access and its current instructions. It extends the single-KB
 * `?kb=` link — `kb` now takes a comma-separated list — so a link copied from a chip keeps
 * working. It grants nothing: the recipient's own access decides what attaches.
 */
export function buildChatSetupUrl(setup: ChatSetup): string {
  const params = new URLSearchParams()
  if (setup.kbUuids.length) params.set('kb', setup.kbUuids.join(','))
  if (setup.docUuids.length) params.set('docs', setup.docUuids.join(','))
  if (setup.folderUuids.length) params.set('folders', setup.folderUuids.join(','))
  if (setup.skillUuid) params.set('skill', setup.skillUuid)
  return `${window.location.origin}/?${params.toString()}`
}

/**
 * The ids in one chat setup param, de-duplicated, blanks dropped. The router
 * JSON-parses search values, so a hand-edited link can hand us a number,
 * boolean, array or object here; coerce rather than crash the workspace.
 */
export function parseIdList(value: unknown): string[] {
  if (value == null || value === '' || (typeof value === 'object' && !Array.isArray(value))) return []
  return [...new Set(String(value).split(',').map(s => s.trim()).filter(Boolean))]
}

/**
 * Copy text that is only known after a request. Safari refuses a clipboard
 * write that starts after an await (the click no longer counts), so where the
 * browser allows it the write starts at once with the text still pending.
 */
async function copyWhenReady(text: Promise<string>): Promise<void> {
  if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
    const blob = text.then(value => new Blob([value], { type: 'text/plain' }))
    await navigator.clipboard.write([new ClipboardItem({ 'text/plain': blob })])
    return
  }
  await navigator.clipboard.writeText(await text)
}

class NoLinkError extends Error {}

export function useShareLink() {
  const { toast } = useToast()
  return useCallback(
    async (kind: ShareableKind, uuid: string, label?: string) => {
      // Whether the link lets in someone who could not already open the item.
      let open = false
      const url = (async () => {
        let shareToken: string | undefined
        if (kind === 'workflow') {
          try {
            shareToken = (await mintWorkflowShareToken(uuid)).share_token
            open = true
          } catch {
            throw new NoLinkError()
          }
        } else if (kind === 'extraction') {
          // A Skill gets an open link when the person may share it outside
          // the team. An extraction, or a Skill they may not share, is
          // refused by the server and keeps the link for people who already
          // have access.
          try {
            shareToken = (await mintSearchSetShareToken(uuid)).share_token
            open = true
          } catch (err) {
            if (!(err instanceof ApiError) || ![400, 403, 404].includes(err.status)) throw new NoLinkError()
          }
        }
        return buildShareUrl(kind, uuid, shareToken)
      })()
      let made = true
      url.catch(() => { made = false })
      try {
        await copyWhenReady(url)
        await url
        const what = label ? `“${label}”` : 'Link'
        toast(
          open
            ? `${what} copied. Anyone signed in can open it.`
            : `${what} copied. It opens for people who already have access.`,
          'success',
        )
      } catch {
        toast(made ? 'Could not copy link to clipboard.' : 'Could not generate share link.', 'error')
      }
    },
    [toast],
  )
}
