import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listSearchSets } from '../../api/extractions'
import { setProjectDefaultSkill } from '../../api/projects'
import { useProjectPins } from '../../hooks/useProjectPins'

const button = 'rounded border border-gray-300 bg-white px-3 py-2 text-sm disabled:opacity-50'

export function ProjectSkillsSection({ projectUuid, defaultSkillUuid, canManage, onChange }: {
  projectUuid: string; defaultSkillUuid?: string | null; canManage: boolean; onChange: () => void
}) {
  const { pins, loading, error: pinError, pin, unpin, refresh } = useProjectPins(projectUuid)
  const skills = pins.filter(p => p.pin_type === 'skill')
  const [adding, setAdding] = useState(false)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  const [choice, setChoice] = useState(defaultSkillUuid ?? '')
  useEffect(() => { setChoice(defaultSkillUuid ?? '') }, [defaultSkillUuid])
  useEffect(() => { const timer = setTimeout(() => setQuery(search.trim()), 250); return () => clearTimeout(timer) }, [search])
  const available = useQuery({ queryKey: ['project-skill-picker', query], queryFn: () => listSearchSets({ search: query }), enabled: adding && canManage })
  const candidates = (available.data ?? []).filter(s => s.set_type === 'prompt' && !skills.some(p => p.target_id === s.uuid))
  const act = async (work: () => Promise<void>) => {
    if (pending.current) return
    pending.current = true; setBusy(true); setError('')
    try { await work(); onChange() } catch (e) { setError(e instanceof Error ? e.message : 'Could not update project Skills.') }
    finally { pending.current = false; setBusy(false) }
  }
  return <section aria-label="Project Skills" className="mt-6 space-y-3 rounded-lg border p-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">Skills</h2>{canManage && <button className={button} onClick={() => setAdding(!adding)}>{adding ? 'Close Skill picker' : 'Pin a Skill'}</button>}</div>
    <p className="text-sm text-gray-600">Reuse Skills in this project. Pinning keeps their existing access permissions. The default applies to new chats; existing conversations keep their selected version.</p>
    {(error || pinError) && <p role="alert" className="text-sm text-red-800">{error || pinError} {pinError && <button className="underline" onClick={() => void refresh()}>Retry Skills</button>}</p>}
    {loading ? <p role="status">Loading Skills…</p> : !skills.length ? <p className="text-sm">No accessible Skills pinned yet.</p> : <ul className="space-y-2">{skills.map(skill => <li key={skill.target_id} className="flex flex-wrap items-center gap-2 rounded border p-3">
      <span className="min-w-0 flex-1 break-words font-medium">{skill.name}{skill.target_id === defaultSkillUuid && <span className="ml-2 text-xs font-normal">Default</span>}</span>
      <a className="text-sm underline" href={`/?project=${encodeURIComponent(projectUuid)}&skill=${encodeURIComponent(skill.target_id)}`}>Use in chat</a>
      {canManage && <button className={button} disabled={busy} onClick={() => void act(async () => { await unpin('skill', skill.target_id); if (choice === skill.target_id) setChoice('') })} aria-label={`Unpin ${skill.name}`}>Unpin</button>}
    </li>)}</ul>}
    {canManage && <div className="flex flex-wrap items-end gap-2">
      <label className="min-w-0 text-sm">Default Skill<select className="mt-1 block max-w-full rounded border p-2" value={choice} disabled={busy || loading} onChange={e => setChoice(e.target.value)}><option value="">No default Skill</option>{choice && !skills.some(s => s.target_id === choice) && <option value={choice}>Default Skill unavailable</option>}{skills.map(s => <option value={s.target_id} key={s.target_id}>{s.name}</option>)}</select></label>
      <button className={button} disabled={busy || loading || choice === (defaultSkillUuid ?? '')} onClick={() => void act(async () => { await setProjectDefaultSkill(projectUuid, choice || null) })}>Save default Skill</button>
    </div>}
    {adding && canManage && <div className="space-y-2 border-t pt-3"><label className="block text-sm">Search Skills<input type="search" className="mt-1 block w-full rounded border p-2" value={search} onChange={e => setSearch(e.target.value)} /></label>
      {available.isLoading && <p role="status">Finding Skills…</p>}
      {available.error && <p role="alert">Could not load Skills. <button className="underline" onClick={() => void available.refetch()}>Retry search</button></p>}
      {!available.isLoading && !available.error && !candidates.length && <p className="text-sm">No matching unpinned Skills. Try a different name or create a Skill in the Library.</p>}
      {candidates.map(s => <button key={s.uuid} disabled={busy} className={`${button} mr-2`} onClick={() => void act(async () => { await pin('skill', s.uuid) })}>Pin {s.title}</button>)}
      {(available.data?.length ?? 0) >= 100 && <p className="text-sm">Search by name to narrow these results.</p>}
    </div>}
  </section>
}
