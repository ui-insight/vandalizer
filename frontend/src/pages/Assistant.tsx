import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, LockKeyhole } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { CoreSkillsSection } from '../components/assistant/CoreSkillsSection'
import { useConfirm } from '../components/shared/useConfirm'
import {
  getAssistantCapabilities, setAssistantCapability, setAssistantCapabilityLimit,
  type AssistantCapability, type AssistantPage,
} from '../api/assistant'

function Switch({ on, busy, unavailable, muted, label, describedBy, onChange }: {
  on: boolean; busy?: boolean; unavailable?: boolean; muted?: boolean; label: string; describedBy?: string; onChange: (next: boolean) => void
}) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} aria-describedby={describedBy}
    aria-busy={busy || undefined} aria-disabled={busy || unavailable || undefined}
    onClick={() => { if (!busy && !unavailable) onChange(!on) }}
    className="flex min-h-11 shrink-0 items-center gap-2 rounded-md px-1 aria-disabled:cursor-not-allowed"
  >
    <span aria-hidden="true" className="text-sm font-medium text-gray-700">{on ? 'On' : 'Off'}</span>
    <span aria-hidden="true" className="relative block h-6 w-11 rounded-full transition-colors" style={{ backgroundColor: !on ? '#6b7280' : muted ? '#9ca3af' : '#15803d' }}>
      <span className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all" style={{ left: on ? 22 : 2 }} />
    </span>
  </button>
}

function status(c: AssistantCapability): string | null {
  if (!c.allowed) return 'Currently blocked for all users by an administrator. Your saved choice applies if it is allowed again.'
  if (!c.available) return 'Currently unavailable. An administrator needs to set it up in Admin. Your saved choice applies once it is available.'
  return null
}

/** What the confirmation says before a switch is saved: which feature, which
 *  way, and whose chats it changes. */
export function changeConfirmation(c: AssistantCapability, next: boolean, everyone: boolean) {
  if (everyone) {
    return {
      title: `${next ? 'Allow' : 'Block'} “${c.label}” for all users?`,
      message: next
        ? `This will change it for all users. Everyone on this Vandalizer site will be able to use ${c.label} in chat again, according to their own saved choice.`
        : `This will change it for all users. ${c.label} will be blocked in everyone’s chats on this Vandalizer site, whatever their own saved choice is.`,
      confirmLabel: next ? 'Allow for all users' : 'Block for all users',
      destructive: !next,
    }
  }
  const held = !c.allowed
    ? ' An administrator has blocked it for all users, so it stays off until they allow it.'
    : !c.available ? ' It isn’t set up on this site yet, so it stays off until an administrator sets it up.' : ''
  return {
    title: `Turn ${next ? 'on' : 'off'} “${c.label}”?`,
    message: `Are you sure you want to turn this ${next ? 'on' : 'off'}? This changes your own chats only, starting with your next message.${next ? held : ''}`,
    confirmLabel: next ? 'Turn on' : 'Turn off',
  }
}

export default function Assistant() {
  const confirm = useConfirm()
  const [page, setPage] = useState<AssistantPage | null>(null)
  const [loadError, setLoadError] = useState('')
  const [verified, setVerified] = useState(false)
  const [refreshing, setRefreshing] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const pending = useRef(false)
  const sequence = useRef(0)

  const load = useCallback(async () => {
    const request = ++sequence.current
    setRefreshing(true); setLoadError(''); setNotice('')
    try {
      const saved = await getAssistantCapabilities()
      if (request !== sequence.current) return null
      setPage(saved); setVerified(true)
      return saved
    } catch {
      if (request === sequence.current) {
        setVerified(false)
        setLoadError('We couldn’t confirm your saved settings. Refresh them before making another change.')
      }
      return null
    } finally {
      if (request === sequence.current) setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const refreshVisible = () => { if (!pending.current && document.visibilityState !== 'hidden') void load() }
    window.addEventListener('focus', refreshVisible)
    return () => { sequence.current++; window.removeEventListener('focus', refreshVisible) }
  }, [load])

  const save = async (c: AssistantCapability, next: boolean, everyone: boolean) => {
    if (pending.current || !verified || refreshing) return
    pending.current = true
    sequence.current++ // A previous read must not overwrite the write response.
    const key = `${everyone ? 'limit' : 'own'}:${c.id}`
    setSaving(key); setNotice(''); setLoadError('')
    const success = everyone
      ? `${c.label} is ${next ? 'allowed' : 'blocked'} for all users. Each person’s saved choice still applies.`
      : `${c.label}: your saved choice is ${next ? 'On' : 'Off'}. Changes apply from your next message.`
    try {
      const saved = await (everyone ? setAssistantCapabilityLimit(c.id, next) : setAssistantCapability(c.id, next))
      setPage(saved); setVerified(true); setNotice(`Saved. ${success}`)
    } catch {
      setVerified(false)
      // A lost response may still have applied the write. Keep controls blocked until the read succeeds.
      const saved = await load()
      if (saved) {
        const row = saved.capabilities.find(row => row.id === c.id)
        const confirmed = row && (everyone ? row.allowed : row.enabled) === next
        setNotice(confirmed ? `Saved. ${success}` : 'The change was not saved. Your saved settings are shown below. Try again.')
      }
    } finally {
      pending.current = false
      setSaving(null)
    }
  }

  // Every switch asks first: a click changes what chat can do, and for an
  // administrator it changes it for everyone on the site.
  const change = async (c: AssistantCapability, next: boolean, everyone: boolean) => {
    if (pending.current || !verified || refreshing) return
    if (!await confirm(changeConfirmation(c, next, everyone))) return
    await save(c, next, everyone)
  }

  const busy = saving !== null || refreshing
  const savingRow = saving ? page?.capabilities.find(c => saving.endsWith(`:${c.id}`)) : null

  return <PageLayout>
    <div className="mx-auto max-w-[820px]">
      <header className="mb-6">
        <h1 className="m-0 text-2xl font-bold text-gray-900">Assistant settings</h1>
        <p className="mt-2 max-w-[680px] text-sm text-gray-600">Choose your usual instructions and what chat can use. Changes apply from your next message. Chat still asks before it creates, changes or shares anything.</p>
      </header>

      <CoreSkillsSection />

      <section aria-labelledby="assistant-capabilities" className="mb-6">
        <h2 id="assistant-capabilities" className="mb-2 text-base font-semibold text-gray-900">What chat can use for you</h2>
        <p className="mb-3 text-sm text-gray-600">Switches show your saved choices. You can change a choice even when an administrator has blocked the feature.</p>
        <div className="mb-4 rounded-lg border border-gray-200 bg-white p-3 text-sm text-gray-700">
          These switches control chat’s direct actions. Workflows you run still follow their saved steps, including web searches. Existing automations and work already running are not stopped by these switches.
        </div>
        {loadError && <div role="alert" id="assistant-settings-unconfirmed" className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {loadError} {page && 'The values below may be out of date.'}{' '}
          <button type="button" disabled={busy} className="underline disabled:opacity-50" onClick={async () => { if (await load()) setNotice('Saved settings refreshed.') }}>Refresh settings</button>
        </div>}
        <p role="status" aria-atomic="true" id="assistant-settings-status" className={busy || notice ? 'mb-3 text-sm text-gray-700' : 'sr-only'}>
          {savingRow ? `Saving ${savingRow.label}${saving?.startsWith('limit:') ? ' for all users' : ''}…` : refreshing ? 'Loading saved settings…' : notice}
        </p>
        {page && <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {page.capabilities.map(c => {
            const note = status(c)
            return <li key={c.id} className="flex items-start gap-3 p-4 sm:gap-5">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-gray-900">{c.label}</div>
                <p id={`assistant-description-${c.id}`} className="mt-1 text-sm text-gray-600">{c.description}</p>
                {note && <p id={`assistant-note-${c.id}`} className="mt-2 text-sm text-amber-800"><LockKeyhole className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />{note}</p>}
              </div>
              <div className="shrink-0 text-right">
                <span className="block text-xs text-gray-600">{saving === `own:${c.id}` ? 'Saving…' : !verified ? 'Unconfirmed' : !c.allowed ? 'Blocked' : !c.available ? 'Not set up' : 'Saved choice'}</span>
                <Switch on={c.enabled} busy={busy} unavailable={!verified} muted={!c.allowed || !c.available} label={c.label}
                  describedBy={[`assistant-description-${c.id}`, note ? `assistant-note-${c.id}` : '', loadError ? 'assistant-settings-unconfirmed' : '', busy ? 'assistant-settings-status' : ''].filter(Boolean).join(' ')}
                  onChange={next => void change(c, next, false)} />
              </div>
            </li>
          })}
        </ul>}
      </section>

      {page?.can_set_limits && <details className="mb-6 rounded-lg border border-gray-300 bg-white p-4">
        <summary className="cursor-pointer font-semibold text-gray-900">Settings for all users — administrators</summary>
        <p id="assistant-limits-help" className="mt-3 text-sm text-gray-600">Turning a switch off blocks this feature in everyone’s chats on this Vandalizer site. Turning it on lets each person use their own saved choice. The certification exercises need “Extractions and compliance checks” and “Workflows” allowed.</p>
        <ul className="mt-3 divide-y divide-gray-200 rounded-md border border-gray-200">
          {page.capabilities.map(c => <li key={c.id} className="flex items-center gap-3 px-3 py-2">
            <span className="min-w-0 flex-1 text-sm font-medium text-gray-900">{c.label}</span>
            <div className="shrink-0 text-right"><span className="block text-xs text-gray-600">{saving === `limit:${c.id}` ? 'Saving…' : !verified ? 'Unconfirmed' : c.allowed ? 'Allowed' : 'Blocked'}</span>
              <Switch on={c.allowed} busy={busy} unavailable={!verified} label={`Allow ${c.label} for everyone`} describedBy={`assistant-limits-help${loadError ? ' assistant-settings-unconfirmed' : ''}${busy ? ' assistant-settings-status' : ''}`} onChange={next => void change(c, next, true)} />
            </div>
          </li>)}
        </ul>
      </details>}

      {page && <details className="mb-6 rounded-lg border border-gray-200 bg-white p-4">
        <summary className="cursor-pointer font-semibold text-gray-900">Always on: files, Skills, plans, help and certification</summary>
        <ul className="mt-3 divide-y divide-gray-200">
          {page.always_on.map(c => <li key={c.id} className="py-3">
            <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-semibold text-gray-900">{c.label}</span><span className="flex items-center gap-1 text-sm text-gray-600"><Check className="h-4 w-4" aria-hidden="true" />Always on</span></div>
            <p className="mt-1 text-sm text-gray-600">{c.description}</p>
          </li>)}
        </ul>
      </details>}
    </div>
  </PageLayout>
}
