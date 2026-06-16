import { useProjectPins } from '../../hooks/useProjects'
import type { ProjectPin } from '../../types/project'

export interface ProjectSuggestion {
  label: string
  message: string
}

const MAX_SUGGESTIONS = 6

/**
 * Build the suggested-action chips for a project from its pins and the viewer's
 * role. Pure + exported so it can be unit-tested without rendering.
 *
 * - Read-only helpers are shown to everyone (including viewers).
 * - "Run {name}" actions appear only for owners/editors, and only for
 *   workflow/extraction pins (automation/KB pins aren't runnable from chat).
 *
 * The "Run {name}" message wording is a contract with the backend agent's
 * run_pin_on_project intent — keep it aligned with the system prompt.
 */
export function buildProjectSuggestions(
  pins: ProjectPin[],
  role: string | null,
): ProjectSuggestion[] {
  const canAct = role === 'owner' || role === 'editor'
  const suggestions: ProjectSuggestion[] = [
    { label: 'Summarize this project', message: 'Summarize this project.' },
  ]

  if (canAct) {
    for (const p of pins) {
      if (p.pin_type === 'workflow' || p.pin_type === 'extraction') {
        suggestions.push({
          label: `Run ${p.name}`,
          message: `Run the "${p.name}" ${p.pin_type} on this project's documents.`,
        })
      }
    }
  }

  suggestions.push({
    label: "What's missing from this project?",
    message:
      "What's missing from this project? Identify gaps in documents, data, or required deliverables.",
  })
  suggestions.push({
    label: 'What can I do next?',
    message: 'What are the recommended next steps for this project?',
  })

  return suggestions.slice(0, MAX_SUGGESTIONS)
}

/**
 * A row of one-tap suggested prompts shown when chatting inside a project.
 * Tapping a chip sends the composed message through ChatPanel's handleSend,
 * which already scopes the request to the active project.
 */
export function ProjectSuggestedActions({
  projectUuid,
  role,
  disabled = false,
  onSend,
}: {
  projectUuid: string
  role: string | null
  disabled?: boolean
  onSend: (message: string) => void
}) {
  const { pins } = useProjectPins(projectUuid)
  const suggestions = buildProjectSuggestions(pins, role)

  return (
    <>
      {suggestions.map(s => (
        <button
          key={s.label}
          disabled={disabled}
          onClick={() => onSend(s.message)}
          style={{
            padding: '8px 14px',
            fontSize: 13,
            fontWeight: 500,
            fontFamily: 'inherit',
            border: '1px solid #e5e7eb',
            borderRadius: 20,
            backgroundColor: '#fff',
            color: '#374151',
            cursor: disabled ? 'default' : 'pointer',
            opacity: disabled ? 0.5 : 1,
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            if (disabled) return
            e.currentTarget.style.borderColor = 'var(--highlight-color, #eab308)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = '#e5e7eb'
          }}
        >
          {s.label}
        </button>
      ))}
    </>
  )
}
