import React from 'react'

// --- mock: ../../hooks/useTeams ---
export function useTeams() {
  const [currentTeam, setCurrent] = React.useState({ uuid: 't1', name: 'Alpha Team' })
  return {
    teams: [
      { uuid: 't1', name: 'Alpha Team' },
      { uuid: 't2', name: 'Beta Team' },
      { uuid: 't3', name: 'Gamma Team' },
    ],
    currentTeam,
    switchTeam: (uuid: string) => {
      const map: Record<string, string> = { t1: 'Alpha Team', t2: 'Beta Team', t3: 'Gamma Team' }
      setCurrent({ uuid, name: map[uuid] })
      ;(window as any).__lastSwitch = uuid
    },
  }
}

// --- mock: ../../hooks/useAuth ---
export function useAuth() {
  return {
    user: { is_support_agent: false, is_admin: true, is_staff: false, is_examiner: true },
    logout: () => { (window as any).__loggedOut = true },
  }
}

// --- mock: ../../contexts/CertificationPanelContext ---
export function useCertificationPanel() {
  return { openPanel: () => { (window as any).__certOpened = true } }
}

// --- mock: ./VersionMenuFooter ---
export function VersionMenuFooter() {
  return <div style={{ padding: 8, fontSize: 11, color: '#999' }}>build abc123</div>
}

// --- mock: @tanstack/react-router Link ---
export function Link({ to, children, className, onClick }: any) {
  return (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        e.preventDefault()
        onClick?.(e)
      }}
    >
      {children}
    </a>
  )
}
