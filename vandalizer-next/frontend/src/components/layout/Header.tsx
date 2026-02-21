import { CircleHelp } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { TeamsDropdown } from './TeamsDropdown'
import { useOptionalWorkspace } from '../../contexts/WorkspaceContext'

export function Header() {
  const navigate = useNavigate()
  const workspace = useOptionalWorkspace()

  const handleLogoClick = () => {
    navigate({ to: '/' })
    workspace?.resetToHome()
  }

  return (
    <header
      className="flex items-center justify-between bg-white shrink-0"
      style={{
        height: 69,
        borderBottom: '2px solid #F4F4F6',
        padding: '0 30px',
      }}
    >
      {/* Left: Logo images - matches Flask navbar-header */}
      <div className="flex items-center">
        <button onClick={handleLogoClick} className="flex items-center" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
          {/* Joe Vandal icon */}
          <img
            src="/images/joevandal.png"
            alt="Joe Vandal Logo"
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

      {/* Right: Support + Teams dropdown */}
      <div className="flex items-center gap-4">
        <a
          href="https://reporting.insight.uidaho.edu"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 rounded-[30px] border border-gray-300 px-3 py-1.5 text-sm font-medium text-[#555] hover:bg-gray-100 transition-all"
        >
          <CircleHelp className="h-3.5 w-3.5" />
          Support
        </a>
        <TeamsDropdown />
      </div>
    </header>
  )
}
