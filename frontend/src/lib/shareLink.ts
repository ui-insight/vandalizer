import { useCallback } from 'react'
import { useToast } from '../contexts/ToastContext'
import { mintWorkflowShareToken } from '../api/workflows'

export type ShareableKind = 'workflow' | 'extraction' | 'kb'

export function buildShareUrl(kind: ShareableKind, uuid: string, shareToken?: string): string {
  const params = new URLSearchParams({ [kind]: uuid })
  if (shareToken) params.set(`${kind}_share_token`, shareToken)
  return `${window.location.origin}/?${params.toString()}`
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
        toast(`${what} copied — share it with anyone.`, 'success')
      } catch {
        toast('Could not copy link to clipboard.', 'error')
      }
    },
    [toast],
  )
}
