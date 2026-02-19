import { useState, useRef, useEffect } from 'react'
import { User, Users, Settings, LogOut, IdCard } from 'lucide-react'
import { Link } from '@tanstack/react-router'
import { useTeams } from '../../hooks/useTeams'
import { useAuth } from '../../hooks/useAuth'

export function TeamsDropdown() {
  const { teams, currentTeam, switchTeam } = useTeams()
  const { logout } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} className="relative inline-block">
      {/* Trigger button - matches Flask .btn .btn-secondary */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-[30px] bg-[#2980b9] border-2 border-[#2980b9] px-3 py-1.5 text-sm font-bold text-white hover:brightness-90 transition-all"
      >
        <User className="h-3.5 w-3.5" />
        {currentTeam?.name || 'Account'}
      </button>

      {/* Menu - matches Flask menu.css */}
      {open && (
        <div
          className="absolute right-0 z-[1000] mt-2 min-w-[180px] rounded-lg border bg-white p-1.5"
          style={{
            borderColor: 'rgba(0,0,0,.15)',
            boxShadow: '0 8px 24px rgba(0,0,0,.12)',
          }}
        >
          {/* Team list */}
          {teams.map((team) => {
            const isActive = team.uuid === currentTeam?.uuid
            return (
              <button
                key={team.uuid}
                onClick={() => {
                  switchTeam(team.uuid)
                  setOpen(false)
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
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-[#111] hover:bg-black/[.04] transition-colors"
          >
            <Settings className="h-4 w-4 shrink-0" style={{ width: 18 }} />
            <span>Manage teams</span>
          </Link>

          {/* My Account */}
          <Link
            to="/account"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-[#111] hover:bg-black/[.04] transition-colors"
          >
            <IdCard className="h-4 w-4 shrink-0" style={{ width: 18 }} />
            <span>My Account</span>
          </Link>

          {/* Divider */}
          <hr className="my-1.5 border-0 h-px bg-[#cdcdcd]" />

          {/* Logout */}
          <button
            onClick={() => {
              setOpen(false)
              logout()
            }}
            className="flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
          >
            <LogOut className="h-4 w-4 shrink-0" style={{ width: 18 }} />
            <span>Logout</span>
          </button>
        </div>
      )}
    </div>
  )
}
