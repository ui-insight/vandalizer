import { useCallback } from 'react'
import { useToast } from '../contexts/ToastContext'
import { mintWorkflowShareToken } from '../api/workflows'

export type ShareableKind = 'workflow' | 'extraction' | 'kb'

export function buildShareUrl(kind: ShareableKind, uuid: string, shareToken?: string): string {
  const params = new URLSearchParams({ [kind]: uuid })
  if (shareToken) params.set(`${kind}_share_token`, shareToken)
  return `${window.location.origin}/?${params.toString()}`
}

/** What a chat setup link carries: the chips that scope a conversation. */
export interface ChatSetup {
  kbUuids: string[]
  docUuids: string[]
  folderUuids: string[]
}

/**
 * A link that opens a fresh chat with the same knowledge bases, library
 * documents and folders attached. It extends the single-KB `?kb=` link — `kb`
 * now takes a comma-separated list — so a link copied from a chip keeps
 * working. It grants nothing: the recipient's own access decides what attaches.
 */
export function buildChatSetupUrl(setup: ChatSetup): string {
  const params = new URLSearchParams()
  if (setup.kbUuids.length) params.set('kb', setup.kbUuids.join(','))
  if (setup.docUuids.length) params.set('docs', setup.docUuids.join(','))
  if (setup.folderUuids.length) params.set('folders', setup.folderUuids.join(','))
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

export function useShareLink() {
  const { toast } = useToast()
  return useCallback(
    async (kind: ShareableKind, uuid: string, label?: string) => {
      let shareToken: string | undefined
      if (kind === 'workflow') {
        try {
          const r = await mintWorkflowShareToken(uuid)
          shareToken = r.share_token
        } catch {
          toast('Could not generate share link.', 'error')
          return
        }
      }
      const url = buildShareUrl(kind, uuid, shareToken)
      try {
        await navigator.clipboard.writeText(url)
        const what = label ? `“${label}”` : 'Link'
        toast(`${what} copied. Share it with anyone.`, 'success')
      } catch {
        toast('Could not copy link to clipboard.', 'error')
      }
    },
    [toast],
  )
}
