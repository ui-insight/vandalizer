import { useEffect, useState } from 'react'
import { Check } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { CoreSkillsSection } from '../components/assistant/CoreSkillsSection'
import {
  getAssistantCapabilities, setAssistantCapabilities, setAssistantCapabilityLimits,
  type AssistantCapability, type AssistantPage,
} from '../api/assistant'

function Switch({ on, disabled, label, onChange }: { on: boolean; disabled?: boolean; label: string; onChange: (next: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className="relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50"
      style={{ backgroundColor: on ? '#15803d' : '#9ca3af' }}
    >
      <span
        aria-hidden="true"
        className="absolute top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-white shadow transition-all"
        style={{ left: on ? 'calc(100% - 22px)' : 2 }}
      />
    </button>
  )
}

function status(c: AssistantCapability): string | null {
  if (!c.allowed) return 'Turned off for everyone by an administrator.'
  if (!c.available) return 'Not set up on this deployment. An administrator can set it up in Admin.'
  return null
}

/**
 * Assistant settings: what chat can use, and the switches for it. (The
 * workspace's chat tab is itself called "Assistant", hence "settings".)
 *
 * Reached from the chat composer, the account menu and the link chat gives
 * when a request needs something that is off. Deliberately not a left-bar
 * item: it is set up once and visited rarely, unlike Files or Knowledge.
 */
export default function Assistant() {
  const [page, setPage] = useState<AssistantPage | null>(null)
  const [loadError, setLoadError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saving, setSaving] = useState<string | null>(null)

  const load = () => {
    setLoadError('')
    getAssistantCapabilities().then(setPage).catch(() => setLoadError('Could not load what chat can use.'))
  }
  useEffect(load, [])

  const save = async (key: string, request: Promise<AssistantPage>) => {
    setSaving(key)
    setSaveError('')
    try {
      setPage(await request)
    } catch {
      setSaveError('Could not save that change. Nothing was changed; try again.')
    } finally {
      setSaving(null)
    }
  }

  const toggleOwn = (c: AssistantCapability, next: boolean) => {
    if (!page) return
    const off = page.capabilities.filter(x => (x.id === c.id ? !next : !x.enabled)).map(x => x.id)
    void save(`own:${c.id}`, setAssistantCapabilities(off))
  }

  const toggleLimit = (c: AssistantCapability, next: boolean) => {
    if (!page) return
    const off = page.capabilities.filter(x => (x.id === c.id ? !next : !x.allowed)).map(x => x.id)
    void save(`limit:${c.id}`, setAssistantCapabilityLimits(off))
  }

  return (
    <PageLayout>
      <div style={{ maxWidth: 820, margin: '0 auto' }}>
        <header style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: '#111827', margin: 0 }}>Assistant settings</h1>
          <p style={{ fontSize: 14, color: '#4b5563', margin: '6px 0 0', maxWidth: 640 }}>
            The Skills chat keeps on hand for you, and what it can use when it works. Changes apply from your
            next message, and chat still asks before it creates, changes or shares anything.
          </p>
        </header>

        <CoreSkillsSection />

        {loadError && <div role="alert" className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{loadError} <button type="button" className="underline" onClick={load}>Retry</button></div>}
        {saveError && <div role="alert" className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{saveError}</div>}
        {!page && !loadError && <p role="status" className="text-sm text-gray-600">Loading…</p>}

        {page && <>
          <section aria-labelledby="assistant-capabilities" className="mb-8">
            <h2 id="assistant-capabilities" className="mb-2 text-base font-semibold text-gray-900">What chat can use</h2>
            <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
              {page.capabilities.map(c => {
                const note = status(c)
                return (
                  <li key={c.id} className="flex items-start gap-4 p-4">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-gray-900">{c.label}</div>
                      <div className="mt-0.5 text-sm text-gray-600">{c.description}</div>
                      {note && <div className="mt-1 text-sm text-amber-800">{note}</div>}
                    </div>
                    <Switch
                      on={c.enabled && c.allowed && c.available}
                      disabled={!!note || saving !== null}
                      label={`${c.label}: ${c.active ? 'on' : 'off'}`}
                      onChange={next => toggleOwn(c, next)}
                    />
                  </li>
                )
              })}
            </ul>
          </section>

          <section aria-labelledby="assistant-always-on" className="mb-8">
            <h2 id="assistant-always-on" className="mb-2 text-base font-semibold text-gray-900">Always on</h2>
            <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
              {page.always_on.map(c => (
                <li key={c.id} className="flex items-start gap-4 p-4">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-gray-900">{c.label}</div>
                    <div className="mt-0.5 text-sm text-gray-600">{c.description}</div>
                  </div>
                  <span className="flex shrink-0 items-center gap-1 text-sm text-gray-600"><Check className="h-4 w-4" aria-hidden="true" />Always on</span>
                </li>
              ))}
            </ul>
          </section>

          {page.can_set_limits && (
            <section aria-labelledby="assistant-limits" className="mb-8">
              <h2 id="assistant-limits" className="mb-1 text-base font-semibold text-gray-900">Allowed for everyone</h2>
              <p className="mb-2 text-sm text-gray-600">
                Administrators only. Turning one off removes it from chat for every person on this deployment, whatever they chose above.
              </p>
              <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
                {page.capabilities.map(c => (
                  <li key={c.id} className="flex items-center gap-4 px-4 py-3">
                    <div className="min-w-0 flex-1 text-sm font-medium text-gray-900">{c.label}</div>
                    <Switch
                      on={c.allowed}
                      disabled={saving !== null}
                      label={`Allow ${c.label} for everyone: ${c.allowed ? 'on' : 'off'}`}
                      onChange={next => toggleLimit(c, next)}
                    />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>}
      </div>
    </PageLayout>
  )
}
