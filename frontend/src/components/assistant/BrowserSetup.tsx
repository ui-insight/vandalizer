import './browser-setup.css'
import { ArrowLeft, ArrowRight, Check, CheckCircle2, Copy, Download, ExternalLink, FolderOpen, Globe2, Loader2, Puzzle, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { AssistantCapability } from '../../api/assistant'
import { browserConnection, browserStoreUrl, type BrowserConnection } from '../../lib/browserSetup'

const steps = ['Download', 'Install', 'Connect', 'Try a Skill']
const progressKey = 'vandalizer-browser-setup-step'

function savedStep() {
  try { return Math.min(2, Math.max(0, Math.floor(Number(sessionStorage.getItem(progressKey)) || 0))) }
  catch { return 0 }
}

export function BrowserSetup({ capability, onEnable, saving = false }: {
  capability?: AssistantCapability
  onEnable?: () => void
  saving?: boolean
}) {
  const [state, setState] = useState<BrowserConnection>('checking')
  const [expanded, setExpanded] = useState(() => location.hash === '#browser-setup')
  const [step, setStep] = useState(savedStep)
  const [downloaded, setDownloaded] = useState(false)
  const [edge, setEdge] = useState(() => navigator.userAgent.includes('Edg/'))
  const [copyNotice, setCopyNotice] = useState('')
  const [checking, setChecking] = useState(false)
  const [checkNotice, setCheckNotice] = useState('')
  const previous = useRef<BrowserConnection>('checking')
  const pending = useRef(false)
  const mounted = useRef(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const focusStep = useRef(false)
  const browserName = edge ? 'Edge' : 'Chrome'
  const extensionsAddress = edge ? 'edge://extensions' : 'chrome://extensions'
  const blocked = capability && (!capability.allowed || !capability.available || !capability.enabled)

  const check = useCallback(async (manual = false) => {
    if (pending.current) return
    pending.current = true
    if (manual) { setChecking(true); setCheckNotice('') }
    try {
      const next = await browserConnection()
      if (!mounted.current) return
      setState(next)
      if (next !== previous.current) {
        if (next === 'connected') setStep(3)
        else if (next === 'installed' || previous.current === 'connected') setStep(2)
        // Returning users need a connection summary, not the installation flow.
        if (next === 'connected' && previous.current === 'checking') setExpanded(false)
        previous.current = next
      }
      if (manual && next !== 'connected') {
        setCheckNotice(next === 'installed' ? 'Extension found. Connect this Vandalizer site using the steps below.' : 'No connection yet. Open Vandalizer Browser from the Extensions menu to finish connecting.')
      }
    } catch {
      if (mounted.current && manual) setCheckNotice('Could not check the connection. Try again, or reload this tab.')
    } finally {
      pending.current = false
      if (mounted.current) setChecking(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void check()
    const refresh = () => { if (!document.hidden) void check() }
    const timer = setInterval(refresh, 2500)
    window.addEventListener('focus', refresh)
    return () => { mounted.current = false; clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [check])

  useEffect(() => {
    try { sessionStorage.setItem(progressKey, String(step)) } catch { /* Private browsing may block storage. */ }
    if (focusStep.current) { heading.current?.focus(); focusStep.current = false }
  }, [step, expanded])

  useEffect(() => {
    const open = () => { if (location.hash === '#browser-setup') setExpanded(true) }
    window.addEventListener('hashchange', open)
    return () => window.removeEventListener('hashchange', open)
  }, [])

  const go = (next: number) => { focusStep.current = true; setExpanded(true); setCopyNotice(''); setCheckNotice(''); setStep(next) }
  const status = state === 'checking' ? 'Checking your browser…' : state === 'connected' ? 'Browser connected' : state === 'installed' ? 'Extension installed · ready to connect' : 'Browser not connected'
  const title = step === 0 ? 'Get Vandalizer Browser' : step === 1 ? 'Add it to ' + browserName : step === 2 ? 'Connect this Vandalizer site' : 'Your browser is ready'

  return <section id="browser-setup" tabIndex={-1} aria-labelledby="browser-setup-title" className="browser-panel browser-wizard" data-compact={!expanded}>
    <header className="browser-wizard-header">
      <div className="browser-header-copy">
      <div className="browser-eyebrow"><Globe2 size={17} aria-hidden="true" /> Vandalizer Browser</div>
      <h2 id="browser-setup-title">{!expanded && state === 'connected' ? 'Your browser is ready' : 'Bring your websites into chat'}</h2>
      <p>{!expanded && state === 'connected' ? <>Connected to <strong>{location.origin}</strong>. Use a browser Skill from your Library.</> : 'Collect figures from the sites you use, with a source for every value.'}</p>
      <div className="browser-status" role="status" data-connected={state === 'connected'}>
        {state === 'connected' ? <CheckCircle2 size={16} aria-hidden="true" /> : state === 'checking' ? <Loader2 size={16} aria-hidden="true" className="animate-spin" /> : <span className="browser-status-dot" aria-hidden="true" />}
        {status}
      </div>
      </div>
      <div className="browser-header-actions">
        {expanded ? <button type="button" className="browser-text-button" aria-expanded="true" aria-controls="browser-setup-content" onClick={() => { setExpanded(false); document.getElementById('browser-setup')?.focus() }}>Close guide</button> : state !== 'checking' && <>
          <button type="button" className="browser-secondary" aria-expanded="false" aria-controls="browser-setup-content" onClick={() => go(state === 'connected' ? 3 : step)}>{state === 'connected' ? 'Try a Skill' : state === 'installed' ? 'Connect this site' : 'Set up browser'}</button>
          {state === 'connected' && <button type="button" className="browser-text-button" onClick={() => go(2)}>Connection help</button>}
        </>}
      </div>
    </header>

    {blocked && <div className="browser-blocked" role="status"><strong>{!capability.allowed ? 'Your administrator has turned off browser access.' : !capability.available ? 'Browser access is unavailable on this Vandalizer site.' : 'Turn on “Use your browser” to use browser Skills.'}</strong><p>{!capability.allowed || !capability.available ? 'Ask your administrator to enable it before setting up your browser.' : 'You can turn it on when you need it. You still approve each website separately.'}</p>{capability.allowed && capability.available && onEnable && <button className="browser-secondary" type="button" disabled={saving} onClick={onEnable}>{saving ? 'Saving…' : 'Turn on Use your browser'}</button>}</div>}

    {expanded && <div id="browser-setup-content">
    <ol className="browser-steps" aria-label="Browser setup progress">
      {steps.map((label, index) => <li key={label} data-current={step === index} data-complete={state === 'connected' || (state === 'installed' && index < 2)}>
        <button type="button" aria-current={step === index ? 'step' : undefined} disabled={index > step && !(state === 'connected' || state === 'installed' && index <= 2)} onClick={() => go(index)}>
          <span className="browser-step-number" aria-hidden="true">{(state === 'connected' && index < 3) || (state === 'installed' && index < 2) ? <Check size={15} /> : index + 1}</span>
          <span>{label}</span>
        </button>
      </li>)}
    </ol>

    <div className="browser-stage">
      <div className="browser-stage-heading"><span className="browser-step-label">Step {step + 1} of 4</span>{step < 2 && <fieldset className="browser-choice"><legend className="sr-only">Your browser</legend>{['Chrome', 'Edge'].map(name => <label key={name}><input type="radio" name="setup-browser" checked={edge === (name === 'Edge')} onChange={() => { setEdge(name === 'Edge'); setCopyNotice('') }} /><span>{name}</span></label>)}</fieldset>}</div>
      <h3 ref={heading} tabIndex={-1}>{title}</h3>

      {step === 0 && <>
        <p className="browser-stage-intro">A small extension lets chat read websites in your own browser, including sites you’re signed into.</p>
        {browserStoreUrl ? <>
          <a className="browser-primary" href={browserStoreUrl} target="_blank" rel="noreferrer" onClick={() => go(2)}>Install the extension <ExternalLink size={16} aria-hidden="true" /></a>
          <p className="browser-hint">Install it from the store, then return here to connect.</p>
        </> : <>
          <div className="browser-download-card"><Puzzle size={30} aria-hidden="true" /><div><strong>Vandalizer Browser</strong><span>Desktop Chrome and Edge · ZIP download</span></div>
            <a className={downloaded ? 'browser-secondary' : 'browser-primary'} href="/vandalizer-browser.zip" download onClick={() => setDownloaded(true)}><Download size={16} aria-hidden="true" />{downloaded ? 'Download again' : 'Download extension'}</a>
          </div>
          <div className="browser-folder-note"><FolderOpen size={20} aria-hidden="true" /><p><strong>Unzip the download.</strong> Open the ZIP in Downloads, then keep the extracted folder somewhere permanent. {browserName} will use that folder.</p></div>
          <div className="browser-stage-actions"><button className={downloaded ? 'browser-primary' : 'browser-secondary'} type="button" onClick={() => go(1)}>I’ve unzipped it <ArrowRight size={16} aria-hidden="true" /></button></div>
          <p className="browser-hint">Not in the Chrome Web Store yet. The next step walks you through adding it manually.</p>
        </>}
        <button type="button" className="browser-text-button" onClick={() => go(2)}>Already installed? Connect it</button>
      </>}

      {step === 1 && <>
        <p className="browser-stage-intro">Open {browserName}’s extensions page in a new tab. Keep this tab open to follow along.</p>
        <div className="browser-address"><code>{extensionsAddress}</code><button type="button" className="browser-secondary" aria-label="Copy extensions address" onClick={async () => {
          try { await navigator.clipboard.writeText(extensionsAddress); setCopyNotice('Copied. Paste it into a new tab’s address bar.') }
          catch { setCopyNotice('Select the address above and copy it manually.') }
        }}><Copy size={16} aria-hidden="true" />Copy address</button></div>
        <p className="browser-hint" role="status">{copyNotice || 'Paste this into the address bar, not a search box.'}</p>
        <ol className="browser-instructions">
          <li><span>1</span><div>Turn on <strong>Developer mode</strong>.<small>{edge ? 'Look in the left sidebar.' : 'Look in the top-right corner.'}</small></div></li>
          <li><span>2</span><div>Click <strong>Load unpacked</strong>.<small>Select the folder you unzipped, then confirm. It contains a file named manifest.json.</small></div></li>
          <li><span>3</span><div>Return to this Vandalizer tab.<small>You should see Vandalizer Browser in your extensions list.</small></div></li>
        </ol>
        <div className="browser-stage-actions"><button type="button" className="browser-primary" onClick={() => go(2)}>I’ve added the extension <ArrowRight size={16} aria-hidden="true" /></button></div>
        <details className="browser-help"><summary>Can’t select the folder?</summary><p>Select the extracted folder, not the ZIP file. If the folder contains another folder, open it until you see manifest.json.</p></details>
      </>}

      {step === 2 && <>
        <p className="browser-stage-intro">Give the extension permission to work with this Vandalizer address.</p>
        <div className="browser-site"><Globe2 size={19} aria-hidden="true" /><strong>{location.origin}</strong></div>
        <ol className="browser-instructions">
          <li><span>1</span><div>Open <strong>Extensions <Puzzle size={15} aria-label="puzzle icon" /></strong> in your browser’s toolbar.<small>Choose <strong>Vandalizer Browser</strong> while you’re on this tab.</small></div></li>
          <li><span>2</span><div>Click <strong>Connect this site</strong>.<small>On the page that opens, click <strong>Allow connection</strong> and approve {browserName}’s request.</small></div></li>
          <li><span>3</span><div>Come back here.<small>We’ll detect the connection and take you to the next step.</small></div></li>
        </ol>
        <div className="browser-waiting"><span className="browser-status-dot" aria-hidden="true" />{state === 'connected' ? 'This site is already connected' : 'Waiting for your connection'}<button type="button" onClick={() => void check(true)} disabled={checking} className="browser-text-button">{checking ? 'Checking…' : 'Check again'}</button></div>
        {state === 'connected' && <button type="button" className="browser-secondary" onClick={() => go(3)}>Try a Skill <ArrowRight size={16} aria-hidden="true" /></button>}
        {checkNotice && <p role="status" className="browser-hint">{checkNotice}</p>}
        <details className="browser-help"><summary>Need help connecting?</summary><p>Open the extension from this Vandalizer tab so it picks up the right address. If you’ve already allowed the connection, reload this tab once.</p><button type="button" className="browser-text-button" onClick={() => go(0)}>Show installation steps</button></details>
      </>}

      {step === 3 && <>
        <p className="browser-stage-intro">Connected to <strong>{location.origin}</strong>. Try it with a Skill from your Library.</p>
        <div className="browser-skill-card"><div className="browser-eyebrow">Try with public university pages</div><h4>University research snapshot</h4><p>Collect enrollment, research spending, and economic impact from the University of Idaho’s website.</p><ul><li><Check size={16} aria-hidden="true" />No university login needed</li><li><Check size={16} aria-hidden="true" />A table with page links</li></ul><a className="browser-primary" href="/?tab=library&browserSkill=demo">Add Skill to Library <ArrowRight size={16} aria-hidden="true" /></a><p className="browser-hint">Review and save it, then choose <strong>Run Skill</strong> in your Library.</p></div>
        <p className="browser-library-note">This is a regular Library Skill. Use it in one chat, or add it to Core Skills in Assistant settings.</p>
        <details className="browser-help"><summary>Use your own instructions</summary><p>Start with a template in the same Library editor, or download the example to import into another account.</p><div className="browser-extra-links"><a href="/?tab=library&browserSkill=starter">Write a Skill</a><a href="/skills/browser-demo.json" download>Download example Skill</a></div></details>
      </>}

      {step > 0 && step < 3 && <button type="button" className="browser-back browser-text-button" onClick={() => go(step - 1)}><ArrowLeft size={15} aria-hidden="true" />Back</button>}
    </div>
    <footer className="browser-safety"><ShieldCheck size={18} aria-hidden="true" /><div><strong>Read-only. You choose the sites.</strong><span>Chat won’t enter passwords or click buttons that submit, pay, save, or change anything. If sign-in is needed, you take over.</span></div></footer>
    </div>}
  </section>
}
