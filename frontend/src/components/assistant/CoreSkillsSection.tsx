import { useEffect, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { getCoreSkills, setCoreSkills, type CoreSkillsPage } from '../../api/assistant'
import { listSearchSets } from '../../api/extractions'
import type { SearchSet } from '../../types/workflow'

function whenToUse(skill: SearchSet): string {
  const line = skill.extraction_config?.when_to_use
  return typeof line === 'string' ? line.trim() : ''
}

/**
 * Core Skills: Library Skills a person keeps available in every chat. Chat
 * sees each one's name and "When to use" line and loads the instructions when
 * a task matches, so a Skill needs that line to be added here.
 */
export function CoreSkillsSection() {
  const [page, setPage] = useState<CoreSkillsPage | null>(null)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [picking, setPicking] = useState(false)
  const [library, setLibrary] = useState<SearchSet[] | null>(null)
  const [libraryError, setLibraryError] = useState('')

  const load = () => {
    setLoadError('')
    getCoreSkills().then(setPage).catch(() => setLoadError('Could not load your core Skills.'))
  }
  useEffect(load, [])

  const openPicker = () => {
    setPicking(true)
    setLibraryError('')
    listSearchSets()
      .then(items => setLibrary(items.filter(item => item.set_type === 'prompt')))
      .catch(() => setLibraryError('Could not load your Skills.'))
  }

  const save = async (uuids: string[]) => {
    setSaving(true)
    setError('')
    try {
      setPage(await setCoreSkills(uuids))
      setPicking(false)
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : 'Could not save your core Skills. Nothing was changed; try again.')
    } finally {
      setSaving(false)
    }
  }

  const current = page?.skills ?? []
  const full = !!page && current.length >= page.max
  const choices = (library ?? []).filter(item => !current.some(skill => skill.uuid === item.uuid))

  return (
    <section aria-labelledby="assistant-core-skills" className="mb-8">
      <h2 id="assistant-core-skills" className="mb-1 text-base font-semibold text-gray-900">Core Skills</h2>
      <p className="mb-2 max-w-[640px] text-sm text-gray-600">
        Skills chat keeps on hand in every conversation. It reads each one's name and When to use line, and follows the
        Skill's instructions when your request matches. A Skill you select in a conversation takes its place for that conversation.
      </p>

      {loadError && <div role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{loadError} <button type="button" className="underline" onClick={load}>Retry</button></div>}
      {error && <div role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      {page && (
        <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {current.length === 0 && (
            <li className="p-4 text-sm text-gray-600">
              No core Skills yet. Add a Skill you use for most of your work, such as your office's award review checklist.
            </li>
          )}
          {current.map(skill => (
            <li key={skill.uuid} className="flex items-start gap-4 p-4">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-gray-900">{skill.title ?? 'Skill no longer available'}</div>
                {skill.when_to_use && <div className="mt-0.5 text-sm text-gray-600"><span className="font-medium">When to use:</span> {skill.when_to_use}</div>}
                {skill.problem && <div className="mt-1 text-sm text-amber-800">Chat is not using this Skill. {skill.problem}</div>}
              </div>
              <button
                type="button"
                disabled={saving}
                onClick={() => void save(current.filter(other => other.uuid !== skill.uuid).map(other => other.uuid))}
                aria-label={`Remove ${skill.title ?? 'this Skill'} from core Skills`}
                className="flex shrink-0 items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                <X className="h-4 w-4" aria-hidden="true" />Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {page && !picking && (
        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            disabled={full || saving}
            onClick={openPicker}
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
            <button type="button" className="text-sm text-gray-700 underline" onClick={() => setPicking(false)}>Cancel</button>
          </div>
          {libraryError && <p role="alert" className="text-sm text-red-800">{libraryError} <button type="button" className="underline" onClick={openPicker}>Retry</button></p>}
          {!library && !libraryError && <p role="status" className="text-sm text-gray-600">Loading your Skills…</p>}
          {library && choices.length === 0 && (
            <p className="text-sm text-gray-600">
              {library.length === 0 ? 'You have no Skills yet. Create one in Library, then add it here.' : 'All your Skills are already core Skills.'}
            </p>
          )}
          <ul className="space-y-2">
            {choices.map(item => {
              const line = whenToUse(item)
              return (
                <li key={item.uuid}>
                  <button
                    type="button"
                    disabled={!line || saving}
                    onClick={() => void save([...current.map(skill => skill.uuid), item.uuid])}
                    className="w-full rounded-md border border-gray-300 p-3 text-left hover:bg-gray-50 disabled:cursor-not-allowed disabled:bg-gray-50"
                  >
                    <div className="break-words text-sm font-medium text-gray-900">{item.title}</div>
                    <div className="mt-0.5 break-words text-sm text-gray-600">
                      {line ? <><span className="font-medium">When to use:</span> {line}</> : 'No When to use line yet. Add one in Library (More actions, Edit) so chat knows when to use it.'}
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </section>
  )
}
