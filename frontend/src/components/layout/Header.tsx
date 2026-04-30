import { useCallback, useEffect, useState } from 'react'
import { CircleHelp } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { TeamsDropdown } from './TeamsDropdown'
import { NotificationBell } from './NotificationBell'
import { SupportChatPanel } from '../support/SupportChatPanel'
import { FeedbackPromptCard } from '../support/FeedbackPromptCard'
import { useOptionalWorkspace } from '../../contexts/WorkspaceContext'
import { useFeedbackPrompt } from '../../hooks/useFeedbackPrompt'

export function Header() {
  const navigate = useNavigate()
  const workspace = useOptionalWorkspace()
  const [supportOpen, setSupportOpen] = useState(false)
  const [supportTicket, setSupportTicket] = useState<string | undefined>()
  const [promptCardHidden, setPromptCardHidden] = useState(false)
  const feedbackPrompt = useFeedbackPrompt()

  const handleLogoClick = () => {
    navigate({
      to: '/',
      search: {
        mode: undefined,
        tab: undefined,
        workflow: undefined,
        extraction: undefined,
        automation: undefined,
        kb: undefined,
      },
    })
    workspace?.resetToHome()
  }

  // Listen for support panel open requests from anywhere (notifications, teams dropdown, etc.)
  const handleSupportEvent = useCallback((e: Event) => {
    const detail = (e as CustomEvent).detail
    setSupportTicket(detail?.ticketUuid || undefined)
    setSupportOpen(true)
  }, [])

  useEffect(() => {
    window.addEventListener('open-support-panel', handleSupportEvent)
    return () => window.removeEventListener('open-support-panel', handleSupportEvent)
  }, [handleSupportEvent])

  // When opening with a pending feedback prompt, jump straight to its ticket.
  // The ticket is now created server-side on /pending so we just use it.
  const handleSupportClick = async () => {
    if (!supportOpen && feedbackPrompt.pendingPrompt?.ticket_uuid) {
      setSupportTicket(feedbackPrompt.pendingPrompt.ticket_uuid)
      setSupportOpen(true)
      feedbackPrompt.clearPending()
      return
    }
    setSupportTicket(undefined)
    setSupportOpen(!supportOpen)
  }

  const handlePromptRespond = () => {
    const ticketUuid = feedbackPrompt.pendingPrompt?.ticket_uuid
    if (!ticketUuid) return
    setSupportTicket(ticketUuid)
    setSupportOpen(true)
    feedbackPrompt.clearPending()
  }

  const handlePromptDismiss = async () => {
    await feedbackPrompt.dismissPrompt()
    setPromptCardHidden(true)
  }

  const showPromptCard =
    !!feedbackPrompt.pendingPrompt && !supportOpen && !promptCardHidden

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
        {/* Left: Logo images */}
        <div className="flex items-center">
          <button onClick={handleLogoClick} aria-label="Go to home page" className="flex items-center" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
            <img src="/images/joevandal.png" alt="" style={{ width: 25, height: 40, marginTop: 4 }} />
            <img src="/images/Vandalizer_Wordmark_RGB.png" alt="Vandalizer" style={{ width: 200, height: 50, marginLeft: 4 }} />
          </button>
        </div>

        {/* Right: Notifications + Support + Teams dropdown */}
        <div className="flex items-center gap-4">
          <NotificationBell />
          <button
            onClick={handleSupportClick}
            className="relative flex items-center gap-1.5 rounded-[30px] border border-gray-300 px-3 py-1.5 text-sm font-medium text-[#555] hover:bg-gray-100 transition-all"
          >
            <CircleHelp className="h-3.5 w-3.5" />
            Support
            {feedbackPrompt.pendingPrompt && !supportOpen && (
              <span className="absolute -top-0.5 -right-0.5 flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-500" />
              </span>
            )}
          </button>
          <TeamsDropdown />
        </div>
      </header>

      <SupportChatPanel
        open={supportOpen}
        onClose={() => setSupportOpen(false)}
        initialTicket={supportTicket}
        onDismissPrompt={feedbackPrompt.dismissPrompt}
      />

      {showPromptCard && feedbackPrompt.pendingPrompt && (
        <FeedbackPromptCard
          prompt={feedbackPrompt.pendingPrompt}
          onRespond={handlePromptRespond}
          onDismiss={handlePromptDismiss}
          onClose={() => setPromptCardHidden(true)}
        />
      )}
    </>
  )
}

// Re-export for convenience
export { openSupportPanel } from '../../utils/supportPanel'
