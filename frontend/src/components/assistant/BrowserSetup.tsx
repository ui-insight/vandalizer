import './browser-setup.css'
import { CheckCircle2, Monitor, Plus, PenLine } from 'lucide-react'
import { useEffect, useState } from 'react'
import { browserConnection, browserStoreUrl, type BrowserConnection } from '../../lib/browserSetup'

export function BrowserSetup() {
  const [state, setState] = useState<BrowserConnection>('checking')
  useEffect(() => {
    let alive = true
    let pending = false
    const check = async () => {
      if (pending) return
      pending = true
      try { const next = await browserConnection(); if (alive) setState(next) }
      finally { pending = false }
    }
    void check()
    const timer = setInterval(() => { if (!document.hidden) void check() }, 2500)
    window.addEventListener('focus', check)
    return () => { alive = false; clearInterval(timer); window.removeEventListener('focus', check) }
  }, [])
  return <section id="browser-setup" tabIndex={-1} aria-labelledby="browser-setup-title" className="browser-panel mb-6 scroll-mt-4 rounded-lg border p-5 text-sm">
    <div className="browser-setup-header"><Monitor aria-hidden="true" className="browser-setup-icon" size={40} /><div><h2 id="browser-setup-title" className="text-base font-semibold">Set up Vandalizer Browser</h2><p>Read figures from your portals and keep the source for each one.</p></div></div>
    <p className="mt-2">Collect figures from websites you already use, signed in as you. Chat only reads: it refuses password fields and buttons that submit, save, pay or change anything. You allow each site separately.</p>
    <p role="status" data-connected={state === 'connected'} className="browser-connection my-3 font-medium">{state === 'connected' && <CheckCircle2 size={16} aria-hidden="true" />}{state === 'checking' ? 'Checking connection…' : state === 'connected' ? `Connected to ${location.origin}` : state === 'installed' ? 'Installed · Connect this site' : 'Not detected · Install or connect the extension'}</p>
    <p>Use Chrome or Edge on a computer. Keep “Use your browser” switched on above; your administrator must also allow it.</p>
    {state === 'installed' && <p className="mt-2 font-medium">Your extension is installed. Finish connecting in step 3.</p>}
    {state !== 'connected' && <ol className="my-3 list-decimal space-y-3 pl-5">
      <li>{browserStoreUrl ? <a className="underline" href={browserStoreUrl} target="_blank" rel="noreferrer">Install Vandalizer Browser</a> : <><a className="font-medium underline" href="/vandalizer-browser.zip" download>Download Vandalizer Browser</a>. Extract the zip and keep the extracted folder on your computer.</>}</li>
      {!browserStoreUrl && <li>Open a new tab and enter <code>chrome://extensions</code> (Edge: <code>edge://extensions</code>). Turn on <strong>Developer mode</strong>. Click <strong>Load unpacked</strong> and select the extracted folder containing <code>manifest.json</code>.</li>}
      <li>Return to this Vandalizer tab. Open the browser’s <strong>Extensions</strong> menu (puzzle icon), then <strong>Vandalizer Browser</strong>. Check that it shows <strong>{location.origin}</strong>. Click <strong>Connect this site</strong>. On the connection page, check the address and click <strong>Allow connection</strong>, then allow access when Chrome asks.</li>
      <li>Return to this tab. This status updates automatically. If it still does not say Connected, reload this tab once. If the extension is already installed but not detected, open its popup to connect it.</li>
    </ol>}
    <div className="browser-demo-guide"><h3 className="font-semibold">Try it with a Skill</h3>
    <p className="mt-1">Add “University research snapshot” to your Library. Run it in Vandalizer chat to collect figures from the University of Idaho’s public website and make a table with sources. It runs as a regular Skill in your account.</p>
    <div className="browser-setup-actions"><a className="browser-primary" href="/?tab=library&browserSkill=demo"><Plus size={16} aria-hidden="true" />Add example Skill</a><a href="/?tab=library&browserSkill=starter"><PenLine size={16} aria-hidden="true" />Write a browser Skill</a><a href="/skills/browser-demo.json" download>Download example Skill</a></div>
    <p className="mt-2">Review and save the instructions in the Library editor. Open the saved Skill, choose “Run Skill”, and ask “Run the research snapshot”. You can also import the downloaded JSON through Library → New Skill → Upload file.</p>
    </div>
  </section>
}
