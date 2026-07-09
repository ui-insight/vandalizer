import { useEffect, useState, useCallback } from 'react'
import { getOnboardingStatus, type OnboardingStatus } from '../api/config'

interface PillDef {
  id: string
  label: string
  gateFlag: keyof OnboardingStatus | null
}

const FEATURE_PILLS: PillDef[] = [
  { id: 'add-file', label: 'Upload a document and summarize it', gateFlag: 'has_documents' },
  { id: 'create-prompt', label: 'Save a reusable prompt for this task', gateFlag: 'has_library_items' },
  { id: 'create-formatter', label: 'Build an extraction template from my documents', gateFlag: 'has_extraction_sets' },
  { id: 'build-from-doc', label: 'Auto-generate a template from a sample file', gateFlag: 'has_extraction_sets' },
  { id: 'create-workflow', label: 'Turn this into a repeatable workflow', gateFlag: 'has_workflows' },
  { id: 'pin-item', label: 'Pin the workflows I use most', gateFlag: 'has_pinned_item' },
  { id: 'favorite-item', label: 'Favorite the templates I come back to', gateFlag: 'has_favorited_item' },
  { id: 'invite-team', label: 'Invite teammates to review this with me', gateFlag: 'has_team_members' },
  { id: 'create-automation', label: 'Set up an automation for incoming files', gateFlag: 'has_automations' },
  { id: 'chat-kb', label: 'Ask my knowledge base a grounded question', gateFlag: 'has_ready_knowledge_base' },
]

const LEARN_PILLS: PillDef[] = [
  { id: 'learn-task-types', label: 'Show me which workflow should handle this document', gateFlag: null },
  { id: 'learn-inputs', label: 'Help me choose the right inputs for this workflow', gateFlag: null },
  { id: 'learn-step-inputs', label: 'Help me chain extraction and review steps together', gateFlag: null },
  { id: 'learn-outputs', label: 'Show me how to export the results', gateFlag: null },
  { id: 'learn-folder-watch', label: 'Help me watch a folder for new files', gateFlag: null },
  { id: 'learn-m365', label: 'Show me how M365 intake would work here', gateFlag: null },
  { id: 'learn-api', label: 'Show me how to trigger this workflow via API', gateFlag: null },
]

/** Deterministic shuffle seeded by day+hour so pills rotate but stay stable within the hour. */
function seededShuffle<T>(arr: T[], seed: number): T[] {
  const copy = [...arr]
  let s = seed
  for (let i = copy.length - 1; i > 0; i--) {
    s = (s * 16807 + 0) % 2147483647
    const j = s % (i + 1)
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

function applyStatus(s: OnboardingStatus) {
  // Prefer server-generated action pills when available
  if (s.suggestion_pills?.length) {
    return s.suggestion_pills.slice(0, 4)
  }

  // Fallback: client-side pill generation
  const now = new Date()
  const seed = now.getFullYear() * 10000 + (now.getMonth() + 1) * 100 + now.getDate() + now.getHours()

  const eligible = FEATURE_PILLS.filter((p) => p.gateFlag && !s[p.gateFlag])
  const shuffledFeature = seededShuffle(eligible, seed)
  const shuffledLearn = seededShuffle(LEARN_PILLS, seed + 1)

  const remaining = [...shuffledFeature, ...shuffledLearn]
    .map((p) => p.label)
    .slice(0, 4)

  return remaining
}

export interface OnboardingResult {
  pills: string[]
  /** True when user has never interacted with Vandalizer — first-session onboarding experience */
  isFirstSession: boolean
  /** True until user has files or sidebar activities (workflows, extractions, knowledge bases) */
  isNewUser: boolean
  status: OnboardingStatus | null
  loading: boolean
  refetchStatus: () => void
}

export function useOnboarding(): OnboardingResult {
  const [pills, setPills] = useState<string[]>([])
  const [isFirstSession, setIsFirstSession] = useState(false)
  const [isNewUser, setIsNewUser] = useState(true)
  const [status, setStatus] = useState<OnboardingStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchStatus = useCallback(() => {
    getOnboardingStatus()
      .then((s) => {
        setStatus(s)
        // User is "new" if they have no files and no sidebar activities
        const hasActivity = s.has_documents || s.has_workflows || s.has_extraction_sets || s.has_knowledge_base
        setIsNewUser(!hasActivity)

        // First session: never completed onboarding, no conversations, no activity
        const firstSession = !s.first_session_completed && !s.has_conversations && !hasActivity
        setIsFirstSession(firstSession)

        // First-session users get the dedicated home surface instead of pills.
        setPills(firstSession ? [] : applyStatus(s))
      })
      .catch(() => {
        // Default to first-session experience on API failure
        setIsFirstSession(true)
        setIsNewUser(true)
        setPills([])
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchStatus() }, [fetchStatus])

  return { pills, isFirstSession, isNewUser, status, loading, refetchStatus: fetchStatus }
}
