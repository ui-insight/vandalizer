import './browser-setup.css'
import { ArrowRight, Globe2 } from 'lucide-react'
import { AssistantSettingsAnchor } from './AssistantSettingsLink'

export function BrowserDiscovery() {
  return <div className="browser-panel browser-discovery">
    <AssistantSettingsAnchor browser label="Read from your websites: set up your browser">
      <span className="browser-discovery-icon"><Globe2 size={23} aria-hidden="true" /></span>
      <div className="browser-discovery-copy"><strong>Read from your websites</strong><p>Collect figures from your portals in chat, with a source for every value.</p></div>
      <span className="browser-discovery-action">Set up browser <ArrowRight size={16} aria-hidden="true" /></span>
    </AssistantSettingsAnchor>
  </div>
}
