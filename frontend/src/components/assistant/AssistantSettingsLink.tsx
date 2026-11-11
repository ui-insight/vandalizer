import type { MouseEvent } from 'react'
import { useRouter } from '@tanstack/react-router'
import { SlidersHorizontal } from 'lucide-react'

/**
 * The composer's way into Assistant settings. Inside the app it navigates
 * through the router, so a reply that is still streaming and an unsent draft
 * survive; the href is the fallback where no router is mounted.
 */
export function AssistantSettingsLink() {
  const router = useRouter({ warn: false })
  const open = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!router || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
    event.preventDefault()
    void router.navigate({ to: '/assistant' })
  }
  return (
    <a href="/assistant" onClick={open} title="What chat can use: turn capabilities on or off" aria-label="Assistant settings: what chat can use"
      className="flex items-center justify-center rounded-[var(--ui-radius)] p-1.5 text-gray-600 hover:text-gray-800 transition-colors">
      <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
    </a>
  )
}
