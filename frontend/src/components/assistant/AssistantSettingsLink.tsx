import type { MouseEvent, ReactNode } from 'react'
import { useRouter } from '@tanstack/react-router'
import { SlidersHorizontal } from 'lucide-react'

/**
 * The composer's way into Assistant settings. Inside the app it navigates
 * through the router, so a reply that is still streaming and an unsent draft
 * survive; the href is the fallback where no router is mounted.
 */
export function AssistantSettingsAnchor({ children, coreSkills = false, className, label, title }: { children: ReactNode; coreSkills?: boolean; className?: string; label?: string; title?: string }) {
  const router = useRouter({ warn: false })
  const open = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!router || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
    event.preventDefault()
    void router.navigate({ to: '/assistant', hash: coreSkills ? 'assistant-core-skills' : undefined })
  }
  return (
    <a href={coreSkills ? '/assistant#assistant-core-skills' : '/assistant'} onClick={open} title={title} aria-label={label} className={className}>{children}</a>
  )
}

export function AssistantSettingsLink({ pausedCount = 0, unavailable = false }: { pausedCount?: number; unavailable?: boolean }) {
  const attention = unavailable ? 'Core Skill availability could not be checked.' : pausedCount ? `${pausedCount} core Skill${pausedCount === 1 ? ' is' : 's are'} paused.` : ''
  return (
    <AssistantSettingsAnchor title={`Assistant settings: Core Skills and what chat can use${attention ? `. ${attention}` : ''}`} label={`Assistant settings: Core Skills and what chat can use${attention ? `. ${attention}` : ''}`}
      className="chat-composer-tool">
      <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
      <span className="chat-composer-tool-label">Settings</span>
      {(pausedCount > 0 || unavailable) && <span aria-hidden="true" className="rounded-full bg-amber-100 px-1.5 text-xs font-semibold text-amber-900">{unavailable ? '!' : pausedCount}</span>}
    </AssistantSettingsAnchor>
  )
}
