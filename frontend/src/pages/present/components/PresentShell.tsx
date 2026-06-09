import type { ReactNode } from 'react'
import { Link } from '@tanstack/react-router'
import { ArrowLeft, ExternalLink } from 'lucide-react'
import { Footer } from '../../../components/layout/Footer'
import { PresentSidebar } from './PresentSidebar'
import type { AudienceId } from '../content'

interface PresentShellProps {
  children: ReactNode
  /** Highlight the active track in the sidebar. Omit on the hub. */
  activeAudience?: AudienceId
  /** Hub hides the sidebar (it has its own picker). */
  showSidebar?: boolean
}

/**
 * Dark, Docs-styled chrome for the Present & Pitch surface: same fixed top nav,
 * background, and Footer as /docs, so it reads as part of Docs while being its
 * own routed section. Public — no auth.
 */
export function PresentShell({ children, activeAudience, showSidebar = true }: PresentShellProps) {
  return (
    <div className="landing-page bg-[#0a0a0a] text-gray-200 antialiased w-full min-h-screen">
      {/* Fixed top nav — mirrors Docs.tsx */}
      <nav className="no-print fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <div className="flex items-center gap-6">
            <Link
              to="/landing"
              search={{ error: undefined, invite_token: undefined, admin: undefined, next: undefined }}
              className="text-xl font-bold text-white hover:text-[#f1b300] transition-colors"
            >
              Vandalizer
            </Link>
            <span className="text-sm text-[#f1b300] font-medium">Present &amp; Pitch</span>
          </div>
          <div className="flex items-center gap-4">
            <Link
              to="/docs"
              className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-[#f1b300] transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Docs
            </Link>
            <a
              href="https://github.com/ui-insight/vandalizer"
              target="_blank"
              rel="noopener noreferrer"
              className="hidden sm:inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-[#f1b300] transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              GitHub
            </a>
          </div>
        </div>
      </nav>

      <div className="pt-16 flex max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {showSidebar && (
          <aside className="no-print hidden lg:block w-64 shrink-0 pr-8">
            <div className="sticky top-24">
              <PresentSidebar activeAudience={activeAudience} />
            </div>
          </aside>
        )}
        <main className="flex-1 min-w-0 py-10">
          {/* Sidebar collapses inline above content on small screens */}
          {showSidebar && (
            <div className="no-print lg:hidden mb-8">
              <PresentSidebar activeAudience={activeAudience} />
            </div>
          )}
          {children}
        </main>
      </div>

      <div className="no-print">
        <Footer />
      </div>
    </div>
  )
}
