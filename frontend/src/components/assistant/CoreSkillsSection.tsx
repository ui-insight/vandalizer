import { useEffect, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'
import {
  acceptCoreSkill, addCoreSkill, getCoreSkillChoices, getCoreSkills, removeCoreSkill,
  type CoreSkill, type CoreSkillChoice, type CoreSkillsPage,
} from '../../api/assistant'

function message(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback
}

/**
 * Core Skills: Library Skills a person keeps available in every chat. Chat
 * sees each one's name and "When to use" line and loads the instructions when
 * a task matches, so a Skill needs that line to be added here.
 *
 * A core Skill loads without an approval card, so the text is pinned when it
 * is added: if anyone edits the Skill, chat stops using it until the person
 * reads the new text here and accepts it.
 */
export function CoreSkillsSection() {
  const [page, setPage] = useState<CoreSkillsPage | null>(null)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [picking, setPicking] = useState(false)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [choices, setChoices] = useState<{ choices: CoreSkillChoice[]; more: boolean } | null>(null)
  const [choicesError, setChoicesError] = useState('')
  const [pickError, setPickError] = useState('')
  const addButton = useRef<HTMLButtonElement>(null)
  const searchBox = useRef<HTMLInputElement>(null)
  const restoreFocus = useRef(false)

  const load = () => {
    setLoadError('')
    getCoreSkills().then(setPage).catch(() => setLoadError('Could not load your core Skills.'))
  }
  useEffect(load, [])

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 250)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (!picking) return
    let cancelled = false
    setChoicesError('')
    getCoreSkillChoices(query)
      .then(found => { if (!cancelled) setChoices(found) })
      .catch(() => { if (!cancelled) setChoicesError('Could not load your Skills.') })
    return () => { cancelled = true }
  }, [picking, query])

  // The Add button and the picker replace each other, so move focus with them.
  useEffect(() => {
    if (picking) searchBox.current?.focus()
    else if (restoreFocus.current) { restoreFocus.current = false; addButton.current?.focus() }
  }, [picking])

  const closePicker = () => {
    restoreFocus.current = true
    setPicking(false)
    setSearch('')
    setQuery('')
    setChoices(null)
    setPickError('')
  }

  const change = async (request: Promise<CoreSkillsPage>, onError: (text: string) => void, fallback: string) => {
    setSaving(true)
    setError('')
    setPickError('')
    try {
      setPage(await request)
      return true
    } catch (reason) {
      onError(message(reason, fallback))
      return false
    } finally {
      setSaving(false)
    }
  }

  const add = async (choice: CoreSkillChoice) => {
    if (await change(addCoreSkill(choice.uuid), setPickError, 'Could not add that Skill. Try again.')) closePicker()
  }
  const remove = (skill: CoreSkill) => void change(removeCoreSkill(skill.uuid), setError, 'Could not remove that Skill. Try again.')
  const accept = (skill: CoreSkill) => {
    if (skill.version) void change(acceptCoreSkill(skill.uuid, skill.version), setError, 'Could not accept the new text. Try again.')
  }

  const current = page?.skills ?? []
  const full = !!page && current.length >= page.max

  return (
    <section aria-labelledby="assistant-core-skills" className="mb-8">
      <h2 id="assistant-core-skills" className="mb-1 text-base font-semibold text-gray-900">Core Skills</h2>
      <p className="mb-2 max-w-[640px] text-sm text-gray-600">
        Skills chat keeps on hand in every conversation. It reads each one's name and When to use line, and follows the
        Skill's instructions when your request matches. A Skill selected for a conversation, including a project's
        default Skill, takes their place in that conversation.
      </p>

      {loadError && <div role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{loadError} <button type="button" className="underline" onClick={load}>Retry</button></div>}
      {error && <div role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      {!page && !loadError && <p role="status" className="text-sm text-gray-600">Loading your core Skills…</p>}

      {page && (
        <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {current.length === 0 && (
            <li className="p-4 text-sm text-gray-600">
              No core Skills yet. Add a Skill you use for most of your work, such as your office's award review checklist.
            </li>
          )}
          {current.map(skill => {
            const name = skill.title ?? 'Skill no longer available'
            return (
              <li key={skill.uuid} className="p-4">
                <div className="flex items-start gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="break-words text-sm font-semibold text-gray-900">{name}</div>
                    {skill.when_to_use && <div className="mt-0.5 break-words text-sm text-gray-600"><span className="font-medium">When to use:</span> {skill.when_to_use}</div>}
                    {skill.problem && <div className="mt-1 text-sm text-amber-800">Chat is not using this Skill. {skill.problem}</div>}
                  </div>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => remove(skill)}
                    aria-label={`Remove ${name} from core Skills`}
                    className="flex shrink-0 items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />Remove
                  </button>
                </div>
                {skill.status === 'changed' && skill.instructions !== null && (
                  <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3">
                    <div className="text-sm font-medium text-gray-900">The Skill's text now</div>
                    <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-words font-sans text-sm text-gray-800">{skill.instructions}</pre>
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => accept(skill)}
                      className="mt-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-900 hover:bg-gray-50 disabled:opacity-50"
                    >
                      Use this version
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {page && !picking && (
        <div className="mt-3 flex items-center gap-3">
          <button
            ref={addButton}
            type="button"
            disabled={full || saving}
            onClick={() => setPicking(true)}
            className="flex items-center gap-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />Add a core Skill
          </button>
          {full && <span className="text-sm text-gray-600">You can keep up to {page.max}. Remove one to add another.</span>}
        </div>
      )}

      {page && picking && (
        <div className="mt-3 rounded-lg border border-gray-200 bg-white p-4" role="group" aria-label="Choose a Skill to add">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-gray-900">Choose a Skill</div>
            <button type="button" className="text-sm text-gray-700 underline" onClick={closePicker}>Cancel</button>
          </div>
          <label className="mb-3 block text-sm text-gray-700">Search your Skills
            <input ref={searchBox} type="search" value={search} onChange={event => setSearch(event.target.value)} className="mt-1 w-full rounded border border-gray-300 p-2" />
          </label>
          {pickError && <p role="alert" className="mb-2 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-800">{pickError}</p>}
          {choicesError && <p role="alert" className="text-sm text-red-800">{choicesError}</p>}
          {!choices && !choicesError && <p role="status" className="text-sm text-gray-600">Loading your Skills…</p>}
          {choices && choices.choices.length === 0 && (
            <p className="text-sm text-gray-600">
              {query ? 'No Skills match that search.' : 'No other Skills to add. Create one in Library, then add it here.'}
            </p>
          )}
          <ul className="space-y-2">
            {(choices?.choices ?? []).map(choice => (
              <li key={choice.uuid}>
                <button
                  type="button"
                  disabled={!choice.when_to_use || saving}
                  onClick={() => void add(choice)}
                  className="w-full rounded-md border border-gray-300 p-3 text-left hover:bg-gray-50 disabled:cursor-not-allowed disabled:bg-gray-50"
                >
                  <div className="break-words text-sm font-medium text-gray-900">{choice.title}</div>
                  <div className="mt-0.5 break-words text-sm text-gray-600">
                    {choice.when_to_use
                      ? <><span className="font-medium">When to use:</span> {choice.when_to_use}</>
                      : 'No When to use line yet. Add one in Library (More actions, Edit) so chat knows when to use it.'}
                  </div>
                </button>
              </li>
            ))}
          </ul>
          {choices?.more && <p className="mt-2 text-sm text-gray-600">Showing the first 50. Search by name to narrow the list.</p>}
        </div>
      )}
    </section>
  )
}
