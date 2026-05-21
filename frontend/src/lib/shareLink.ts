import { useCallback } from 'react'
import { useToast } from '../contexts/ToastContext'

export type ShareableKind = 'workflow' | 'extraction' | 'kb'

export function buildShareUrl(kind: ShareableKind, uuid: string): string {
  const params = new URLSearchParams({ [kind]: uuid })
  return `${window.location.origin}/?${params.toString()}`
}

export function useShareLink() {
  const { toast } = useToast()
  return useCallback(
    async (kind: ShareableKind, uuid: string, label?: string) => {
      const url = buildShareUrl(kind, uuid)
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
