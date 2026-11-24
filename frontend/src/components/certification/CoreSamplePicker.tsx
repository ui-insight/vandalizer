import { useEffect, useState } from 'react'
import { listConversations } from '../../api/chat'
import { listProjects } from '../../api/projects'
import type { CoreSampleSelection } from '../../types/certification'

type Option = { uuid: string; title: string }

export function CoreSamplePicker({ title, value, disabled, onChange }: {
  title: string
  value: CoreSampleSelection
  disabled: boolean
  onChange: (selection: CoreSampleSelection) => void
}) {
  const [options, setOptions] = useState<{ projects: Option[]; chats: Option[] }>()
  const [error, setError] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    Promise.all([listProjects(), listConversations(200)]).then(([projects, chats]) => {
      if (active) {
        setOptions({ projects: projects.filter(p => !p.team_id && p.title.trim().toLowerCase() === title.toLowerCase()), chats })
        setError(false)
      }
    }).catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [title, revision])
  return <fieldset disabled={disabled} className="space-y-3 rounded-lg border border-gray-200 p-4">
    <legend className="px-1 font-semibold">Your private work sample</legend>
    <p className="text-sm">In Project context, save the four lines you selected below, one per line. Select the training project and the chat you used for its award, policy, Skill and browser lookup.</p>
    <label className="block text-sm">Training project
      <select className="block min-h-11 w-full" value={value.project_id} onChange={e => onChange({ project_id: e.target.value, conversation_id: value.conversation_id })}>
        <option value="">Choose your project</option>
        {options?.projects.map(p => <option key={p.uuid} value={p.uuid}>{p.title}</option>)}
      </select>
    </label>
    <label className="block text-sm">Case chat
      <select className="block min-h-11 w-full" value={value.conversation_id} onChange={e => onChange({ project_id: value.project_id, conversation_id: e.target.value })}>
        <option value="">Choose your case chat</option>
        {options?.chats.map(c => <option key={c.uuid} value={c.uuid}>{c.title}</option>)}
      </select>
    </label>
    {error && <p role="alert">Could not load your projects and chats.</p>}
    {options && !options.projects.length && <p className="text-sm">Create a personal project named {title}, then refresh this list.</p>}
    <button type="button" className="min-h-11 text-sm underline" onClick={() => setRevision(r => r + 1)}>Refresh projects and recent chats</button>
  </fieldset>
}
