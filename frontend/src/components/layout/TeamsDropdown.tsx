import { useState, useRef, useEffect } from 'react'
import type { KeyboardEvent } from 'react'
import { Award, User, Users, Settings, LogOut, IdCard, Shield, ClipboardCheck, ChevronDown, MessageSquare, KeyRound } from 'lucide-react'
import { Link } from '@tanstack/react-router'
import { useTeams } from '../../hooks/useTeams'
import { useAuth } from '../../hooks/useAuth'
import { useCertificationPanel } from '../../contexts/CertificationPanelContext'
import { VersionMenuFooter } from './VersionMenuFooter'

export function TeamsDropdown() {
  const { teams, currentTeam, switchTeam } = useTeams()
  const { user, logout } = useAuth()
  const certPanel = useCertificationPanel()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // Collect the currently rendered menuitems (order = DOM order).
  const getMenuItems = () =>
    Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])

  // Close the menu and (by default) return focus to the trigger button.
  const closeMenu = (restoreFocus = true) => {
    setOpen(false)
    if (restoreFocus) triggerRef.current?.focus()
  }

  useEffect(() => {
    // Only listen while the menu is open — an always-on handler steals focus
    // on the next frame after any mousedown on non-focusable content, which
    // cancels the browser's drag-to-select before it can extend.
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        // Restore focus to the trigger only when the click didn't land on
        // another focusable element (avoids stealing focus).
        requestAnimationFrame(() => {
          if (document.activeElement === document.body) triggerRef.current?.focus()
        })
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Move focus to the first menuitem when the menu opens.
  useEffect(() => {
    if (!open) return
    const items = menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]')
    items?.[0]?.focus()
  }, [open])

  // Roving keyboard navigation within the menu.
  const handleMenuKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      closeMenu()
      return
    }

    const items = getMenuItems()
    if (items.length === 0) return

    const currentIndex = items.indexOf(document.activeElement as HTMLElement)
    let nextIndex: number

    switch (e.key) {
      case 'ArrowDown':
        nextIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0
        break
      case 'ArrowUp':
        nextIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1
        break
      case 'Home':
        nextIndex = 0
        break
      case 'End':
        nextIndex = items.length - 1
        break
      default:
        return
    }

    e.preventDefault()
    items[nextIndex]?.focus()
  }

  return (
    <div ref={ref} className="relative inline-block">
      {/* Trigger button - matches Flask .btn .btn-secondary */}
      <button
        ref={triggerRef}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`Account menu: ${currentTeam?.name || 'Account'}`}
        className="flex items-center gap-1.5 rounded-[30px] border border-gray-300 px-3 py-1.5 text-sm font-medium text-[#555] hover:bg-gray-100 transition-all"
      >
        <User className="h-3.5 w-3.5" />
        {currentTeam?.name || 'Account'}
        <ChevronDown className="h-3 w-3" />
      </button>

      {/* Menu - matches Flask menu.css */}
      {open && (
        <div
          ref={menuRef}
          role="menu"
          className="absolute right-0 z-[1000] mt-2 min-w-[180px] rounded-lg border bg-white p-1.5"
          style={{
            borderColor: 'rgba(0,0,0,.15)',
            boxShadow: '0 8px 24px rgba(0,0,0,.12)',
          }}
          onKeyDown={handleMenuKeyDown}
        >
          {/* Team list */}
          {teams.map((team) => {
            const isActive = team.uuid === currentTeam?.uuid
            return (
              <button
                key={team.uuid}
                role="menuitem"
                tabIndex={-1}
                onClick={() => {
                  switchTeam(team.uuid)
                  closeMenu()
                }}
                className="menu-item flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
              >
                <Users className="h-4 w-4 shrink-0" style={{ width: 18 }} />
                <span>{team.name}</span>
                {isActive && (
                  <span className="text-[11px] text-[#36c] ml-2">(current)</span>
                )}
              </button>
            )
          })}

          {/* Divider */}
          <hr className="my-1.5 border-0 h-px bg-[#cdcdcd]" />

          {/* Manage teams */}
          <Link
            to="/teams"
            role="menuitem"
            tabIndex={-1}
            onClick={() => closeMenu()}
            className="flex items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-[#111] hover:bg-black/[.04] transition-colors"
          >
            <Settings className="h-4 w-4 shrink-0" style={{ width: 18 }} />
            <span>Manage teams</span>
          </Link>

          {/* My Account */}
          <Link
            to="/account"
            role="menuitem"
            tabIndex={-1}
            onClick={() => closeMenu()}
            className="flex items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-[#111] hover:bg-black/[.04] transition-colors"
          >
            <IdCard className="h-4 w-4 shrink-0" style={{ width: 18 }} />
            <span>My Account</span>
          </Link>

          {/* Credentials */}
          <Link
            to="/credentials"
            role="menuitem"
            tabIndex={-1}
            onClick={() => closeMenu()}
            className="flex items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-[#111] hover:bg-black/[.04] transition-colors"
          >
            <KeyRound className="h-4 w-4 shrink-0" style={{ width: 18 }} />
            <span>Credentials</span>
          </Link>

          {/* Certification */}
          <button
            role="menuitem"
            tabIndex={-1}
            onClick={() => {
              certPanel.openPanel()
              // Don't restore focus to the trigger: the panel manages its own focus.
              closeMenu(false)
            }}
            className="flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
          >
            <Award className="h-4 w-4 shrink-0" style={{ width: 18 }} />
            <span>Certification</span>
          </button>

          {/* Support agent: Support Center */}
          {user?.is_support_agent && (
            <>
              <hr className="my-1.5 border-0 h-px bg-[#cdcdcd]" />
              <Link
                to="/support"
                search={{ ticket: undefined }}
                role="menuitem"
                tabIndex={-1}
                onClick={() => closeMenu()}
                className="flex items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-[#111] hover:bg-black/[.04] transition-colors"
              >
                <MessageSquare className="h-4 w-4 shrink-0" style={{ width: 18 }} />
                <span>Support Center</span>
              </Link>
            </>
          )}

          {/* Admin / Analytics: full admins and staff (analytics-only) and examiners */}
          {(user?.is_admin || user?.is_staff || user?.is_examiner) && (
            <>
              {!user?.is_support_agent && <hr className="my-1.5 border-0 h-px bg-[#cdcdcd]" />}
              <Link
                to="/admin"
                role="menuitem"
                tabIndex={-1}
                onClick={() => closeMenu()}
                className="flex items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-[#111] hover:bg-black/[.04] transition-colors"
              >
                <Shield className="h-4 w-4 shrink-0" style={{ width: 18 }} />
                <span>{user?.is_admin ? 'Admin' : 'Analytics'}</span>
              </Link>
            </>
          )}

          {/* Examiner: Verification Management */}
          {user?.is_examiner && (
            <>
              {!user?.is_admin && <hr className="my-1.5 border-0 h-px bg-[#cdcdcd]" />}
              <Link
                to="/verification"
                role="menuitem"
                tabIndex={-1}
                onClick={() => closeMenu()}
                className="flex items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-[#111] hover:bg-black/[.04] transition-colors"
              >
                <ClipboardCheck className="h-4 w-4 shrink-0" style={{ width: 18 }} />
                <span>Verification Management</span>
              </Link>
            </>
          )}

          {/* Divider */}
          <hr className="my-1.5 border-0 h-px bg-[#cdcdcd]" />

          {/* Logout */}
          <button
            role="menuitem"
            tabIndex={-1}
            onClick={() => {
              closeMenu(false)
              logout()
            }}
            className="flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
          >
            <LogOut className="h-4 w-4 shrink-0" style={{ width: 18 }} />
            <span>Logout</span>
          </button>

          {/* Deployment / build info */}
          <VersionMenuFooter />
        </div>
      )}
    </div>
  )
}
