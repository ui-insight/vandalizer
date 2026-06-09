import { Link } from '@tanstack/react-router'
import { Presentation } from 'lucide-react'
import { TRACK_ORDER, TRACKS, type AudienceId } from '../content'
import { cn } from '../../../lib/cn'

interface PresentSidebarProps {
  /** Highlight the current track when rendered inside the Present page. */
  activeAudience?: AudienceId
  /** Called after a link is clicked (e.g. to close the Docs mobile drawer). */
  onNavigate?: () => void
}

/**
 * The distinct "Present & Pitch" block. Rendered at the top of the Docs sidebar
 * (so it reads as its own section within Docs) and reused as the Present page's
 * own TOC. Links navigate to the real /docs/present routes.
 */
export function PresentSidebar({ activeAudience, onNavigate }: PresentSidebarProps) {
  return (
    <div className="rounded-lg border border-[#f1b300]/30 bg-[#f1b300]/[0.06] p-3">
      <Link
        to="/docs/present"
        onClick={onNavigate}
        className="flex items-center gap-2 mb-2 text-[#f1b300] hover:opacity-80 transition-opacity"
      >
        <Presentation className="w-4 h-4 shrink-0" />
        <span className="text-xs font-bold uppercase tracking-wider">Present &amp; Pitch</span>
      </Link>
      <nav className="space-y-0.5">
        {TRACK_ORDER.map((id) => {
          const track = TRACKS[id]
          const Icon = track.icon
          const active = activeAudience === id
          return (
            <Link
              key={id}
              to="/docs/present/$audience"
              params={{ audience: id }}
              search={{ mode: undefined, slide: undefined, pitch: undefined }}
              onClick={onNavigate}
              className={cn(
                'flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-sm transition-colors',
                active
                  ? 'bg-[#f1b300]/15 text-[#f1b300]'
                  : 'text-gray-300 hover:text-white hover:bg-white/5',
              )}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {track.label}
            </Link>
          )
        })}
      </nav>
    </div>
  )
}
