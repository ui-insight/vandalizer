import { BookOpen, ClipboardCheck, Cloud, FileText, Globe, MessageSquare, Shield, Users, Workflow, Zap } from 'lucide-react'
import { Link, useRouterState } from '@tanstack/react-router'
import { cn } from '../../lib/cn'
import { useAuth } from '../../hooks/useAuth'
import { useTeams } from '../../hooks/useTeams'

export function Sidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const { user } = useAuth()
  const { currentTeam } = useTeams()

  const isTeamAdmin = currentTeam?.role === 'owner' || currentTeam?.role === 'admin'
  const showAdmin = !!user?.is_admin || !!user?.is_examiner || isTeamAdmin

  const links = [
    { href: '/', label: 'Documents', icon: FileText },
    { href: '/chat', label: 'Chat', icon: MessageSquare },
    { href: '/library', label: 'Library', icon: BookOpen },
    { href: '/workflows', label: 'Workflows', icon: Workflow },
    { href: '/automation', label: 'Automation', icon: Zap },
    { href: '/office', label: 'Office 365', icon: Cloud },
    { href: '/browser-automation', label: 'Browser', icon: Globe },
    { href: '/teams', label: 'Teams', icon: Users },
    ...(user?.is_examiner ? [{ href: '/verification', label: 'Verification', icon: ClipboardCheck }] : []),
    ...(showAdmin ? [{ href: '/admin', label: 'Admin', icon: Shield }] : []),
  ] as const

  return (
    <aside className="flex w-56 flex-col border-r border-gray-200 bg-gray-50">
      <nav aria-label="Main navigation" className="flex-1 p-3 space-y-1">
        {links.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            to={href}
            aria-current={(href === '/' ? pathname === '/' : pathname.startsWith(href)) ? 'page' : undefined}
            className={cn(
              'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium',
              (href === '/' ? pathname === '/' : pathname.startsWith(href))
                ? 'bg-blue-50 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  )
}
