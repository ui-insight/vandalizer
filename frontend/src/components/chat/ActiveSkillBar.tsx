import type { SkillSnapshot } from '../../types/chat'

export function ActiveSkillBar({ skill, busy, onChoose, onRemove }: {
  skill: SkillSnapshot | null
  busy: boolean
  onChoose: () => void
  onRemove: () => void
}) {
  return <div className="px-4 py-2 text-sm" aria-label="Chat Skill">
    <div className="flex flex-wrap items-center gap-3">
      {skill ? <strong>Skill: {skill.title}</strong> : <span>No Skill selected</span>}
      <button type="button" className="underline" disabled={busy} onClick={onChoose}>
        {skill ? 'Change Skill' : 'Choose Skill'}
      </button>
      {skill && <button type="button" className="underline" disabled={busy} onClick={onRemove}>Remove Skill</button>}
    </div>
    {skill && <details className="mt-2">
      <summary className="cursor-pointer">Inspect instructions</summary>
      <p className="mt-2 text-xs text-gray-600">This saved version guides this conversation. To use edits from the Library, select the Skill again.</p>
      <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words rounded border border-gray-200 bg-gray-50 p-3 font-sans">{skill.instructions}</pre>
    </details>}
  </div>
}
