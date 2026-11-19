import '../assistant/browser-setup.css'
import { ExternalLink, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { focusBrowserTab } from '../../lib/browserSetup'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { browserMessage } from './browserMessages'

export function browserSite(result?: Record<string, unknown> | null) {
  const page = result?.page as Record<string, unknown> | undefined
  try { if (page?.url) return new URL(String(page.url)).host } catch { /* No readable page. */ }
  return typeof result?.site === 'string' ? result.site : ''
}

export function BrowserActivity({ result, active = false }: { result?: Record<string, unknown> | null; active?: boolean }) {
  const { sendChatMessage } = useWorkspace()
  const [notice, setNotice] = useState('')
  const [continued, setContinued] = useState(false)
  const site = browserSite(result)
  const error = String(result?.error || '')
  const permission = ['unapproved_site', 'site_not_allowed'].includes(error)
  const redirected = error === 'unapproved_site'
  const disconnected = ['browser_not_connected', 'extension_unavailable', 'browser_unavailable'].includes(error)
  const signIn = !permission && Boolean(result?.login_required)
  const refused = error.startsWith('blocked_')
  // The server refuses Vandalizer's own pages outright; its message is written for the person.
  const ownSite = error === 'vandalizer_itself'
  const title = active ? 'Reading in your browser…' : permission ? 'Site permission needed' : signIn ? 'Sign in to continue' : disconnected ? 'Reconnect your browser' : refused ? 'Action blocked · read-only' : ownSite ? 'Not available on Vandalizer itself' : error ? 'Browser needs attention' : 'Read-only browser'
  const continueLabel = redirected ? 'Check page and continue' : permission ? 'Ask for site access' : signIn ? 'Continue after sign-in' : 'Continue browser task'
  // Sent in the person's name, in chats with and without a Skill: say "what you
  // were doing", never "the selected Skill" (support ticket). A selected Skill
  // stays on the conversation, so it still applies to the next reply.
  const continueMessage = redirected
    ? 'Continue what you were doing in my browser; read the current working tab again. If it still needs site permission, ask me before opening it with browser_open. Never bypass site permissions.'
    : permission ? 'Continue what you were doing in my browser. Ask for permission with browser_open before reading the site that was not allowed. Never bypass site permissions.'
    : signIn ? 'I have finished signing in in the working tab. Continue what you were doing; read the current page first.'
      : 'Continue what you were doing in my browser. Reopen the page if the working tab has closed.'
  return <div className="browser-panel browser-activity">
    <div className="browser-activity-heading"><ShieldCheck size={17} aria-hidden="true" /><strong>{title}</strong>{site && <span>{site}</span>}</div>
    {redirected ? <p>The working tab moved to a site you haven’t allowed. Chat hasn’t read it. If this is a sign-in page, sign in yourself and return to the allowed site, then continue here.</p> : permission && <p>You haven’t allowed this site, so chat hasn’t opened or read it. Ask again when you’re ready to allow access.</p>}
    {signIn && <p>Sign in yourself in the working tab, then return here. Keep your password out of chat.</p>}
    {disconnected && <p>Open browser settings to reconnect this Vandalizer site, then continue your task.</p>}
    {refused && <p>This control could change something on the site. Chat stopped without using it.</p>}
    {error && !permission && !disconnected && !refused && <p>{browserMessage(result ?? {})}</p>}
    {!active && <div className="browser-activity-actions">
      {disconnected ? <a className="browser-secondary" href="/assistant#browser-setup">Open browser settings</a> : error !== 'site_not_allowed' && !ownSite && <button type="button" className="browser-text-button" onClick={async () => {
        const outcome = await focusBrowserTab()
        setNotice(outcome.ok ? '' : outcome.error === 'no_open_page' ? 'The working tab has closed. Ask chat to open the site again.' : 'Could not open the tab. Check your connection in Assistant settings, or select the tab in your browser.')
      }}>Open working tab <ExternalLink size={14} aria-hidden="true" /></button>}
      {(permission || signIn || disconnected || error === 'no_open_page') && <button type="button" disabled={continued} className="browser-secondary" onClick={() => {
        if (continued) return
        sendChatMessage(continueMessage)
        setContinued(true)
        setNotice('Continue request sent to chat.')
      }}>{continued ? 'Request sent' : continueLabel}</button>}
    </div>}
    {notice && <p role="status" className="browser-hint">{notice}</p>}
  </div>
}
