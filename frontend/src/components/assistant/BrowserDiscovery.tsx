import './browser-setup.css'
import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, Globe2, X } from 'lucide-react'
import { browserConnection, type BrowserConnection } from '../../lib/browserSetup'
import { AssistantSettingsAnchor } from './AssistantSettingsLink'

// Like the other Home preferences, this choice belongs to this browser/site.
// Completing setup also retires the suggestion; a temporary disconnect is
// handled in browser settings, not by advertising installation again.
const hiddenKey = 'vandalizer:home:hide-browser-suggestion'
function isHidden() {
  try { return localStorage.getItem(hiddenKey) === '1' } catch { return false }
}

export function BrowserDiscovery() {
  const [hidden, setHidden] = useState(isHidden)
  const [connection, setConnection] = useState<BrowserConnection>('checking')
  const dismiss = useCallback(() => {
    setHidden(true)
    try { localStorage.setItem(hiddenKey, '1') } catch { /* Still hide it for this visit. */ }
  }, [])

  useEffect(() => {
    if (hidden) return
    let active = true
    let pending = false
    const check = async () => {
      if (pending || document.hidden) return
      pending = true
      try {
        const next = await browserConnection()
        if (!active) return
        if (next === 'connected') dismiss()
        else setConnection(next)
      } catch { /* An uncertain connection is no reason to suggest installing. */ }
      finally { pending = false }
    }
    const refresh = () => { void check() }
    const syncDismissal = (event: StorageEvent) => {
      if (event.key === hiddenKey && event.newValue === '1') setHidden(true)
    }
    refresh()
    const timer = window.setInterval(refresh, 5000)
    window.addEventListener('focus', refresh)
    window.addEventListener('storage', syncDismissal)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      active = false
      clearInterval(timer)
      window.removeEventListener('focus', refresh)
      window.removeEventListener('storage', syncDismissal)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [hidden, dismiss])

  if (hidden || connection === 'checking') return null

  return <aside className="browser-panel browser-discovery" aria-label="Optional browser feature">
    <Globe2 className="browser-discovery-icon" size={20} aria-hidden="true" />
    <div className="browser-discovery-copy"><strong>Read from your websites</strong><p>An optional way to collect figures in chat, with source links.</p></div>
    <AssistantSettingsAnchor browser className="browser-discovery-action" label={connection === 'installed' ? 'Connect your browser to this site' : 'Learn more about browser access'}>
      {connection === 'installed' ? 'Connect this site' : 'Learn more'} <ArrowRight size={14} aria-hidden="true" />
    </AssistantSettingsAnchor>
    <button type="button" className="browser-discovery-dismiss" aria-label="Dismiss browser suggestion" title="Dismiss suggestion" onClick={dismiss}><X size={16} aria-hidden="true" /></button>
  </aside>
}
