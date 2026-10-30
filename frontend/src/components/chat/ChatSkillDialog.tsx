import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { listSearchSets } from '../../api/extractions'
import type { SkillSnapshot } from '../../types/chat'

interface Props {
  mode: 'change' | 'inspect'
  skill: SkillSnapshot
  disabled: boolean
  onSelect: (uuid: string) => Promise<boolean>
  onClose: () => void
}

export function ChatSkillDialog({ mode, skill, disabled, onSelect, onClose }: Props) {
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const pending = useRef(false)
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 250)
    return () => clearTimeout(timer)
  }, [search])
  const available = useQuery({
    queryKey: ['chat-skill-picker', query],
    queryFn: () => listSearchSets({ search: query }),
    enabled: mode === 'change',
  })
  const skills = (available.data ?? []).filter(item => item.set_type === 'prompt')
  const choose = async (uuid: string) => {
    if (pending.current || disabled) return
    pending.current = true
    setSaving(true)
    setError('')
    try {
      if (await onSelect(uuid)) onClose()
      else setError('Could not change Skill. Your current Skill is still selected. Try again.')
    } catch {
      setError('Could not change Skill. Your current Skill is still selected. Try again.')
    } finally {
      pending.current = false
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/50 p-4" style={{ zIndex: 900 }} onKeyDown={event => { if (event.key === 'Escape') onClose() }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div role="dialog" aria-modal="true" aria-labelledby="chat-skill-title" className="flex max-h-[90dvh] w-full max-w-lg flex-col rounded-lg bg-white shadow-xl">
          <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-3">
            <h3 id="chat-skill-title" className="font-medium text-gray-900">{mode === 'inspect' ? `${skill.title} instructions` : 'Change Skill'}</h3>
            <button type="button" onClick={onClose} aria-label="Close Skill dialog" className="rounded p-1 text-gray-600"><X className="h-5 w-5" /></button>
          </div>
          <div className="space-y-3 overflow-y-auto p-5 text-sm">
            {mode === 'inspect' ? <>
              <p className="break-words text-gray-600">Selected version: {skill.version}</p>
              <pre className="whitespace-pre-wrap break-words font-sans">{skill.instructions}</pre>
            </> : <>
              <p className="text-gray-600">Choose the Skill for subsequent messages in this chat.</p>
              <label className="block">Search Skills
                <input type="search" value={search} onChange={event => setSearch(event.target.value)} className="mt-1 w-full rounded border border-gray-300 p-2" />
              </label>
              {error && <p role="alert" className="text-red-700">{error}</p>}
              {available.isLoading && <p role="status">Loading Skills…</p>}
              {available.isError && <p role="alert">Could not load Skills. <button type="button" className="underline" onClick={() => void available.refetch()}>Retry Skills</button></p>}
              {!available.isLoading && !available.isError && !skills.length && <p>No matching Skills. Try another name or create a Skill in the Library.</p>}
              <ul className="space-y-2">
                {skills.map(item => <li key={item.uuid}>
                  <button type="button" disabled={disabled || saving || item.uuid === skill.uuid} onClick={() => void choose(item.uuid)} className="w-full break-words rounded border border-gray-300 p-3 text-left hover:bg-gray-50 disabled:opacity-50">
                    {item.title}{item.uuid === skill.uuid && ' · Current Skill'}
                  </button>
                </li>)}
              </ul>
              {(available.data?.length ?? 0) >= 100 && <p>Search by name to narrow these results.</p>}
              {saving && <p role="status">Changing Skill…</p>}
            </>}
          </div>
        </div>
      </FocusTrap>
    </div>
  )
}
