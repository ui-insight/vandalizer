import '../assistant/browser-setup.css'
import { useState } from 'react'
import { focusBrowserTab } from '../../lib/browserSetup'
import { useWorkspace } from '../../contexts/WorkspaceContext'
export function BrowserActivity({ result }: { result?: Record<string, unknown> | null }) {
  const { sendChatMessage } = useWorkspace()
  const [notice, setNotice] = useState('')
  const [continued, setContinued] = useState(false)
  const page = result?.page as Record<string, unknown> | undefined
  let site = typeof result?.site === 'string' ? result.site : ''
  try { if (page?.url) site = new URL(String(page.url)).host } catch { /* No readable page. */ }
  const paused = Boolean(result?.login_required || result?.error === 'unapproved_site')
  return <div className="browser-panel px-3 pb-3 text-sm">
    <p>Read-only browser{site ? ` · ${site}` : ''}</p>
    {paused && <p>Sign in yourself in the working tab. Return here when you’re ready. Never send your password in chat.</p>}
    <button type="button" className="mr-3 mt-2 underline" onClick={async () => {
      const outcome = await focusBrowserTab()
      setNotice(outcome.ok ? '' : 'Could not open the working tab. Reconnect in Assistant settings, or select the tab beside Vandalizer.')
    }}>Open working tab</button>
    {paused && <button type="button" disabled={continued} className="mt-2 underline disabled:opacity-50" onClick={() => { if (continued) return; setContinued(true); sendChatMessage('I have signed in in the working tab. Continue the selected Skill; read the current page first.'); setNotice('Continue request sent to chat.') }}>Continue after sign-in</button>}
    {notice && <p role="status">{notice}</p>}
  </div>
}
