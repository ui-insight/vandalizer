import { useEffect, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'
import {
  acceptCoreSkill, addCoreSkill, getCoreSkillChoices, getCoreSkillPreview, notifyCoreSkillsChanged, removeCoreSkill,
  type CoreSkill, type CoreSkillChoice, type CoreSkillsPage,
} from '../../api/assistant'
import { ApiError } from '../../api/client'
import { useCoreSkills } from '../../hooks/useCoreSkills'
import type { SkillSnapshot } from '../../types/chat'
import { SkillInstructions } from './SkillInstructions'

function message(reason: unknown): string {
  return reason instanceof Error && reason.message ? reason.message : 'Could not confirm the change.'
}

export function CoreSkillsSection() {
  const { scope, page, error: loadError, loading, refresh, replace } = useCoreSkills()
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState<string | null>(null)
  const [savingTarget, setSavingTarget] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const [picking, setPicking] = useState(false)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [choices, setChoices] = useState<{ choices: CoreSkillChoice[]; more: boolean; query: string } | null>(null)
  const [choicesError, setChoicesError] = useState('')
  const [choicesAttempt, setChoicesAttempt] = useState(0)
  const [reviewId, setReviewId] = useState<string | null>(null)
  const [preview, setPreview] = useState<SkillSnapshot | null>(null)
  const [previewError, setPreviewError] = useState('')
  const [previewAttempt, setPreviewAttempt] = useState(0)
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null)
  const [updatedPreview, setUpdatedPreview] = useState<CoreSkill | null>(null)
  const sectionHeading = useRef<HTMLHeadingElement>(null)
  const previewHeading = useRef<HTMLHeadingElement>(null)
  const addButton = useRef<HTMLButtonElement>(null)
  const searchBox = useRef<HTMLInputElement>(null)
  const removeButtons = useRef(new Map<string, HTMLButtonElement>())
  const focusTarget = useRef<string | null>(null)
  const pending = useRef(false)
  const currentScope = useRef(scope)
  currentScope.current = scope

  useEffect(() => {
    setPicking(false); setReviewId(null); setPreview(null); setSearch(''); setQuery(''); setChoices(null)
    setError(''); setNotice(''); setUncertain(false); setExpandedSkill(null); setUpdatedPreview(null)
    focusTarget.current = null
  }, [scope])

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 250)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (!picking || reviewId) return
    let cancelled = false
    setChoices(null); setChoicesError('')
    getCoreSkillChoices(query)
      .then(found => { if (!cancelled) setChoices({ ...found, query }) })
      .catch(() => { if (!cancelled) setChoicesError('Could not load your Skills.') })
    return () => { cancelled = true }
  }, [picking, query, scope, choicesAttempt, reviewId])

  useEffect(() => {
    if (!reviewId) return
    let cancelled = false
    setPreview(null); setPreviewError('')
    getCoreSkillPreview(reviewId)
      .then(found => { if (!cancelled) setPreview(found) })
      .catch(reason => { if (!cancelled) setPreviewError(message(reason)) })
    return () => { cancelled = true }
  }, [reviewId, scope, previewAttempt])

  useEffect(() => {
    if (picking) {
      if (reviewId) previewHeading.current?.focus()
      else searchBox.current?.focus()
    }
  }, [picking, reviewId])

  useEffect(() => {
    if (saving || !focusTarget.current) return
    const target = focusTarget.current
    focusTarget.current = null
    const row = removeButtons.current.get(target)
    if (row) row.focus()
    else if (addButton.current && !addButton.current.disabled) addButton.current.focus()
    else sectionHeading.current?.focus()
  }, [page, picking, saving, reviewId, notice])

  const closePicker = (target = 'add') => {
    if (pending.current) return
    focusTarget.current = target
    setPicking(false); setReviewId(null); setPreview(null); setSearch(''); setQuery(''); setChoices(null); setError('')
  }

  const refreshSettings = async () => {
    if (pending.current) return
    if (await refresh()) { setUncertain(false); setError(''); setNotice('Core Skills refreshed.') }
  }

  const blocked = !!saving || (!page && loading) || !!loadError || uncertain
  const change = async (
    label: string, uuid: string, request: () => Promise<CoreSkillsPage>, confirmed: (saved: CoreSkillsPage) => boolean,
  ): Promise<CoreSkillsPage | null> => {
    if (pending.current || blocked) return null
    pending.current = true
    const startedIn = scope
    setSaving(label); setSavingTarget(uuid); setError(''); setNotice('')
    try {
      const saved = await request()
      if (currentScope.current !== startedIn) { notifyCoreSkillsChanged(); return null }
      replace(saved)
      notifyCoreSkillsChanged()
      return saved
    } catch (reason) {
      if (currentScope.current !== startedIn) { notifyCoreSkillsChanged(); return null }
      const fresh = await refresh()
      if (currentScope.current !== startedIn) return null
      if (reason instanceof ApiError && reason.status === 409) {
        setPreviewAttempt(attempt => attempt + 1)
        const latest = fresh?.skills.find(skill => skill.uuid === uuid)
        if (latest?.status === 'changed') setUpdatedPreview(latest)
        setError(fresh ? 'This Skill changed while you were reviewing it. Review the updated instructions before accepting them.' : 'This Skill changed. Refresh your core Skills before reviewing it again.')
      } else if (fresh && confirmed(fresh)) {
        notifyCoreSkillsChanged()
        return fresh
      } else {
        setError(`${message(reason)} ${fresh ? 'Your saved core Skills are shown. Review them before trying again.' : 'Your saved core Skills could not be checked. Refresh them before making another change.'}`)
      }
      setUncertain(!fresh)
      return null
    } finally {
      pending.current = false
      setSaving(null)
      setSavingTarget('')
    }
  }

  const add = async () => {
    if (!preview) return
    const saved = await change('Adding Skill…', preview.uuid, () => addCoreSkill(preview.uuid, preview.version), found => found.skills.some(skill => skill.uuid === preview.uuid))
    if (!saved) return
    closePicker(preview.uuid)
    setNotice(`${preview.title} added. ${saved.skills.length} of ${saved.max} core Skills.`)
  }
  const remove = async (skill: CoreSkill) => {
    if (!await change('Removing Skill…', skill.uuid, () => removeCoreSkill(skill.uuid), found => !found.skills.some(row => row.uuid === skill.uuid))) return
    focusTarget.current = 'add'
    setNotice(`${skill.title ?? 'Unavailable Skill'} removed.`)
    // The removed button no longer exists. Move focus after the list updates.
    setExpandedSkill(null)
  }
  const accept = async (skill: CoreSkill) => {
    if (!skill.version) return
    const version = skill.version
    const saved = await change('Accepting instructions…', skill.uuid, () => acceptCoreSkill(skill.uuid, version), found => found.skills.some(row => row.uuid === skill.uuid && row.version === version && row.usable))
    if (!saved) return
    focusTarget.current = skill.uuid
    setExpandedSkill(null)
    setNotice(saved.skills.some(row => row.uuid === skill.uuid && row.usable) ? `${skill.title} is ready to use again.` : 'Instructions accepted, but this Skill is still paused. Review its current status.')
  }

  const current = page?.skills ?? []
  const full = !!page && current.length >= page.max
  const choicesLoading = !choices || choices.query !== search.trim() || choices.query !== query
  const errorBox = error && <p role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>

  return (
    <section aria-labelledby="assistant-core-skills" className="mb-8">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 ref={sectionHeading} tabIndex={-1} id="assistant-core-skills" className="text-base font-semibold text-gray-900">Core Skills</h2>
        {page && <span className="text-sm text-gray-600">{current.length} of {page.max} added</span>}
      </div>
      <p className="mb-3 max-w-[680px] text-sm text-gray-600">
        Your usual checklists and writing instructions, saved in Library. Add up to five; chat uses one when your request matches its “When to use” description.
      </p>
      <details className="mb-3 text-sm text-gray-600">
        <summary className="cursor-pointer font-medium text-gray-700">When core Skills apply</summary>
        <p className="mt-2">Choosing a Skill for a conversation, including a project's default Skill, replaces all core Skills for that conversation. A team's Skill applies only in that team. If someone edits a core Skill, it pauses until you review and accept the updated instructions.</p>
      </details>

      {loadError && <div role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{loadError} {page && 'The list below may be out of date.'} <button type="button" className="underline" disabled={loading} onClick={() => void refreshSettings()}>Refresh core Skills</button></div>}
      {uncertain && !loadError && <button type="button" className="mb-3 text-sm underline" disabled={loading} onClick={() => void refreshSettings()}>Refresh core Skills</button>}
      {!picking && errorBox}
      <p role="status" aria-atomic="true" className={saving || notice || (!page && loading) ? 'mb-3 text-sm text-gray-700' : 'sr-only'}>{saving ?? (!page && loading ? 'Loading your core Skills…' : notice)}</p>

      {page && <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
        {current.length === 0 && <li className="p-4 text-sm text-gray-600">No core Skills yet. Add a Skill you use for most of your work, such as your office's award review checklist.</li>}
        {current.map(skill => {
          const name = skill.title ?? 'Skill no longer available'
          return <li key={skill.uuid} className="p-4">
            <div className="flex flex-col items-start gap-3 sm:flex-row sm:gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="break-words text-sm font-semibold text-gray-900">{name}</span>
                  <span className={`text-xs font-medium ${skill.usable ? 'text-gray-600' : 'text-amber-800'}`}>{skill.usable ? 'Ready when needed' : 'Paused'}</span>
                </div>
                {skill.when_to_use && <p className="mt-1 break-words text-sm text-gray-600"><span className="font-medium">When to use:</span> {skill.when_to_use}</p>}
                {skill.problem && <p className="mt-1 text-sm text-amber-800">Chat is not using this Skill. {skill.problem}</p>}
              </div>
              <button ref={element => { if (element) removeButtons.current.set(skill.uuid, element); else removeButtons.current.delete(skill.uuid) }} type="button" aria-disabled={blocked} onClick={() => void remove(skill)} aria-label={`Remove ${name} from core Skills`}
                className="flex shrink-0 items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1.5 text-sm text-gray-700 hover:bg-gray-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50">
                <X className="h-4 w-4" aria-hidden="true" />{saving === 'Removing Skill…' && savingTarget === skill.uuid ? saving : 'Remove'}
              </button>
            </div>
            {skill.status === 'changed' && skill.instructions !== null && <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3">
              <button type="button" aria-expanded={expandedSkill === skill.uuid} onClick={() => { setExpandedSkill(expandedSkill === skill.uuid ? null : skill.uuid); setUpdatedPreview(skill) }} className="text-left text-sm font-medium text-gray-900 underline">{expandedSkill === skill.uuid ? 'Hide updated instructions' : 'Review updated instructions'}</button>
              {expandedSkill === skill.uuid && updatedPreview?.uuid === skill.uuid && <div className="mt-2 space-y-3">
                <p className="text-sm text-gray-700"><strong>{updatedPreview.title}</strong><br /><strong>When to use:</strong> {updatedPreview.when_to_use}</p>
                <SkillInstructions instructions={updatedPreview.instructions ?? ''} label={`Updated instructions for ${name}`} />
                {updatedPreview.version !== skill.version && <p role="status" className="text-sm text-amber-900">This Skill changed again. <button type="button" className="font-medium underline" onClick={() => setUpdatedPreview(skill)}>Load updated instructions</button> before accepting it.</p>}
                <button type="button" aria-disabled={blocked || updatedPreview.version !== skill.version} onClick={() => { if (updatedPreview.version === skill.version) void accept(updatedPreview) }} className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50 aria-disabled:opacity-50">{saving === 'Accepting instructions…' ? saving : 'Use this version'}</button>
              </div>}
            </div>}
          </li>
        })}
      </ul>}

      {page && !picking && <div className="mt-3 flex flex-wrap items-center gap-3">
        <button ref={addButton} type="button" disabled={full || blocked} onClick={() => { setError(''); setPicking(true) }} className="flex items-center gap-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"><Plus className="h-4 w-4" aria-hidden="true" />Add a core Skill</button>
        {full && <span className="text-sm text-gray-600">You can keep up to {page.max}. Remove one to add another.</span>}
      </div>}

      {page && picking && <div className="mt-3 rounded-lg border border-gray-200 bg-white p-4" role="group" aria-label="Choose a Skill to add" onKeyDown={event => { if (event.key === 'Escape' && !pending.current) { event.preventDefault(); closePicker() } }}>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 ref={previewHeading} tabIndex={-1} className="text-sm font-semibold text-gray-900">{reviewId ? 'Review Skill instructions' : 'Choose a Skill'}</h3>
          <button type="button" disabled={!!saving} className="text-sm text-gray-700 underline disabled:opacity-50" onClick={() => closePicker()}>Cancel</button>
        </div>
        {errorBox}
        {reviewId ? <>
          {!preview && !previewError && <p role="status" className="text-sm text-gray-600">Loading instructions…</p>}
          {previewError && <p role="alert" className="text-sm text-red-800">{previewError} <button type="button" className="underline" onClick={() => setPreviewAttempt(attempt => attempt + 1)}>Retry instructions</button></p>}
          {preview && <div className="space-y-3">
            <p className="break-words text-sm font-semibold text-gray-900">{preview.title}</p>
            <p className="break-words text-sm text-gray-600"><strong>When to use:</strong> {preview.when_to_use}</p>
            <SkillInstructions instructions={preview.instructions} />
            <p className="text-sm text-gray-600">Chat can use these instructions when your request matches, without asking you to select the Skill each time. Changes apply from your next message.</p>
            <button type="button" aria-disabled={blocked || full} onClick={() => { if (!full) void add() }} className="rounded-md bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-800 aria-disabled:opacity-50">{saving === 'Adding Skill…' ? saving : 'Add this core Skill'}</button>
          </div>}
          <button type="button" disabled={!!saving} className="mt-3 text-sm text-gray-700 underline disabled:opacity-50" onClick={() => { setReviewId(null); setPreview(null); setError('') }}>Back to Skills</button>
        </> : <>
          <label className="mb-3 block text-sm text-gray-700">Search your Skills
            <input ref={searchBox} type="search" value={search} onChange={event => setSearch(event.target.value)} className="mt-1 w-full rounded border border-gray-300 p-2" />
          </label>
          {choicesError ? <p role="alert" className="text-sm text-red-800">{choicesError} <button type="button" className="underline" onClick={() => setChoicesAttempt(attempt => attempt + 1)}>Retry Skills</button></p>
            : choicesLoading ? <p role="status" className="text-sm text-gray-600">Loading your Skills…</p>
              : choices && <>
                {choices.choices.length === 0 && <p className="text-sm text-gray-600">{query ? 'No Skills match that search. Try another name.' : 'No other Skills to add. Create one in Library, then add it here.'}</p>}
                <ul className="max-h-96 space-y-2 overflow-y-auto p-1">
                  {choices.choices.map(choice => <li key={choice.uuid}>
                    <button type="button" disabled={!choice.when_to_use} onClick={() => { setPreview(null); setReviewId(choice.uuid) }} className="w-full rounded-md border border-gray-300 p-3 text-left hover:bg-gray-50 disabled:cursor-not-allowed disabled:bg-gray-50">
                      <span className="block break-words text-sm font-medium text-gray-900">{choice.title}</span>
                      <span className="mt-1 block break-words text-sm text-gray-600">{choice.when_to_use ? <><strong>When to use:</strong> {choice.when_to_use}</> : 'Unavailable: no “When to use” description. Add one in Library → More actions → Edit.'}</span>
                      {choice.when_to_use && <span className="mt-2 block text-sm font-medium text-gray-700 underline">Review instructions</span>}
                    </button>
                  </li>)}
                </ul>
                {choices.more && <p className="mt-2 text-sm text-gray-600">Showing the first 50. Search by name to narrow the list.</p>}
              </>}
          <a href="/?tab=library" className="mt-3 inline-block text-sm text-gray-700 underline">Open Library to create or edit a Skill</a>
        </>}
      </div>}
    </section>
  )
}
