import { useEffect, useRef } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import type { SkillSnapshot } from '../../types/chat'

interface Props {
  skill: SkillSnapshot
  accepting: boolean
  error: string | null
  onAccept: () => void
  onCancel: () => void
}

/** A shared Skill's instructions, shown before chat may use them.
 *
 * Suggestion ticket: a Skill shared with the team started in a teammate's chat
 * without them ever seeing its instructions. Skills someone else wrote are now
 * read and accepted first, and again after an edit. */
export function SkillReviewDialog({ skill, accepting, error, onAccept, onCancel }: Props) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [skill.version])
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/50 p-4" style={{ zIndex: 950 }} onKeyDown={event => { if (event.key === 'Escape' && !accepting) onCancel() }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div role="dialog" aria-modal="true" aria-labelledby="skill-review-title" aria-describedby="skill-review-intro" className="flex max-h-[90dvh] w-full max-w-lg flex-col rounded-lg bg-white shadow-xl">
          <div className="border-b border-gray-200 px-5 py-3">
            <h3 id="skill-review-title" ref={heading} tabIndex={-1} className="break-words font-medium text-gray-900">Review “{skill.title}”</h3>
          </div>
          <div className="space-y-3 overflow-y-auto p-5 text-sm">
            <p id="skill-review-intro" className="text-gray-600">
              This Skill was shared with you, or changed since you last accepted it. Chat follows these instructions as written. Read them, then accept to use the Skill in your chats.
            </p>
            {skill.when_to_use && <p className="break-words"><strong>When to use:</strong> {skill.when_to_use}</p>}
            {/* Focusable so long instructions scroll from the keyboard, and so the
                focus trap keeps a tabbable node while both buttons are disabled. */}
            <pre tabIndex={0} aria-label={`Instructions for ${skill.title}`} className="max-h-[50dvh] overflow-auto whitespace-pre-wrap break-words rounded border border-gray-200 bg-gray-50 p-3 font-sans">{skill.instructions}</pre>
            {error && <p role="alert" className="text-red-700">{error}</p>}
          </div>
          <div className="flex justify-end gap-2 border-t border-gray-200 px-5 py-3">
            <button type="button" onClick={onCancel} disabled={accepting} className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50 disabled:opacity-50">Cancel</button>
            <button type="button" onClick={onAccept} disabled={accepting} className="rounded-md bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50">{accepting ? 'Accepting…' : 'Accept'}</button>
          </div>
        </div>
      </FocusTrap>
    </div>
  )
}
