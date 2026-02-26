import { useEffect, useState } from 'react'
import { getOnboardingStatus, type OnboardingStatus } from '../api/config'

interface PillDef {
  id: string
  label: string
  gateFlag: keyof OnboardingStatus | null
}

const FEATURE_PILLS: PillDef[] = [
  { id: 'add-file', label: 'How do I upload a document?', gateFlag: 'has_documents' },
  { id: 'create-prompt', label: 'How do I save a reusable prompt?', gateFlag: 'has_library_items' },
  { id: 'create-formatter', label: 'What are formatters?', gateFlag: 'has_extraction_sets' },
  { id: 'build-from-doc', label: 'Can I auto-generate an extraction set?', gateFlag: 'has_extraction_sets' },
  { id: 'create-workflow', label: 'How do I set up a workflow?', gateFlag: 'has_workflows' },
  { id: 'pin-item', label: 'What does pinning do?', gateFlag: 'has_pinned_item' },
  { id: 'favorite-item', label: 'What does favoriting do?', gateFlag: 'has_favorited_item' },
  { id: 'invite-team', label: 'How do I invite teammates?', gateFlag: 'has_team_members' },
  { id: 'create-automation', label: 'What can automations do?', gateFlag: 'has_automations' },
  { id: 'chat-kb', label: 'How do knowledge bases work?', gateFlag: 'has_ready_knowledge_base' },
]

const LEARN_PILLS: PillDef[] = [
  { id: 'learn-task-types', label: 'What workflow task types are there?', gateFlag: null },
  { id: 'learn-inputs', label: 'How do workflow inputs work?', gateFlag: null },
  { id: 'learn-step-inputs', label: 'How do I chain workflow steps?', gateFlag: null },
  { id: 'learn-outputs', label: 'How do I export workflow results?', gateFlag: null },
  { id: 'learn-folder-watch', label: 'What are folder watch triggers?', gateFlag: null },
  { id: 'learn-m365', label: 'What are M365 intake triggers?', gateFlag: null },
  { id: 'learn-api', label: 'Can I trigger a workflow via API?', gateFlag: null },
  { id: 'learn-schedule', label: 'Can I schedule a workflow to run automatically?', gateFlag: null },
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

export function useOnboarding(): string[] {
  const [pills, setPills] = useState<string[]>([])

  useEffect(() => {
    getOnboardingStatus()
      .then((status) => {
        const now = new Date()
        const seed = now.getFullYear() * 10000 + (now.getMonth() + 1) * 100 + now.getDate() + now.getHours()

        // Feature-gated pills: only show if user hasn't done the thing yet
        const eligible = FEATURE_PILLS.filter(
          (p) => p.gateFlag && !status[p.gateFlag],
        )
        const shuffledFeature = seededShuffle(eligible, seed)
        const shuffledLearn = seededShuffle(LEARN_PILLS, seed + 1)

        // Prioritize feature pills, fill remaining slots with learn pills
        const combined = [...shuffledFeature, ...shuffledLearn].slice(0, 4)
        setPills(combined.map((p) => p.label))
      })
      .catch(() => {
        setPills([
          'What can I do here?',
          'How do I set up a workflow?',
          'How do knowledge bases work?',
        ])
      })
  }, [])

  return pills
}
