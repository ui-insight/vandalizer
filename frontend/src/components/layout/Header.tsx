import { useState } from 'react'
import { CircleHelp } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { TeamsDropdown } from './TeamsDropdown'
import { NotificationBell } from './NotificationBell'
import { SupportChatPanel } from '../support/SupportChatPanel'
import { useOptionalWorkspace } from '../../contexts/WorkspaceContext'

export function Header() {
  const navigate = useNavigate()
  const workspace = useOptionalWorkspace()
  const [supportOpen, setSupportOpen] = useState(false)

  const handleLogoClick = () => {
    navigate({
      to: '/',
      search: {
        mode: undefined,
        tab: undefined,
        workflow: undefined,
        extraction: undefined,
        automation: undefined,
      },
    })
    workspace?.resetToHome()
  }

  return (
    <>
      <header
        role="banner"
        className="flex items-center justify-between bg-white shrink-0"
        style={{
          height: 69,
          borderBottom: '2px solid #F4F4F6',
          padding: '0 30px',
        }}
      >
        {/* Left: Logo images - matches Flask navbar-header */}
        <div className="flex items-center">
          <button onClick={handleLogoClick} aria-label="Go to home page" className="flex items-center" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
            {/* Joe Vandal icon */}
            <img
              src="/images/joevandal.png"
              alt=""
              style={{ width: 25, height: 40, marginTop: 4 }}
            />
            {/* Vandalizer wordmark */}
            <img
              src="/images/Vandalizer_Wordmark_RGB.png"
              alt="Vandalizer"
              style={{ width: 200, height: 50, marginLeft: 4 }}
            />
          </button>
        </div>

        {/* Right: Notifications + Support + Teams dropdown */}
        <div className="flex items-center gap-4">
          <NotificationBell />
          <button
            onClick={() => setSupportOpen(!supportOpen)}
            className="flex items-center gap-1.5 rounded-[30px] border border-gray-300 px-3 py-1.5 text-sm font-medium text-[#555] hover:bg-gray-100 transition-all"
          >
            <CircleHelp className="h-3.5 w-3.5" />
            Support
          </button>
          <TeamsDropdown />
        </div>
      </header>

      <SupportChatPanel open={supportOpen} onClose={() => setSupportOpen(false)} />
    </>
  )
}
