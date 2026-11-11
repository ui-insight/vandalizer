import { coreSkillsNeedingAttention, type CoreSkillsPage } from '../../api/assistant'
import { AssistantSettingsAnchor } from './AssistantSettingsLink'

export function CoreSkillsNotice({ page, error, selectedSkill }: { page: CoreSkillsPage | null; error: string; selectedSkill?: string }) {
  const paused = coreSkillsNeedingAttention(page)
  if (!paused.length && !error) return null
  return <div role="status" className="mx-3 mb-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
    {error ? <p>Core Skill availability could not be checked. <AssistantSettingsAnchor coreSkills className="font-medium underline">Check Assistant settings</AssistantSettingsAnchor>.</p>
      : <>
        <p className="font-medium">{paused.length === 1 ? '1 core Skill is paused' : `${paused.length} core Skills are paused`}</p>
        {paused.length === 1 ? <p className="mt-1"><span className="font-medium">{paused[0].title ?? 'Skill no longer available'}:</span>{' '}{paused[0].status === 'changed' ? 'Updated instructions need your review.' : paused[0].problem}</p>
          : <details className="mt-1">
            <summary className="cursor-pointer underline">See paused Skills</summary>
            <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto">
              {paused.map(skill => <li key={skill.uuid}>
                <span className="font-medium">{skill.title ?? 'Skill no longer available'}:</span>{' '}
                {skill.status === 'changed' ? 'Updated instructions need your review.' : skill.problem}
              </li>)}
            </ul>
          </details>}
        {selectedSkill && <p className="mt-1">This conversation uses {selectedSkill} instead of core Skills.</p>}
        <AssistantSettingsAnchor coreSkills className="mt-1 inline-block font-medium underline">{paused.some(skill => skill.status === 'changed') ? 'Review in Assistant settings' : 'Manage core Skills'}</AssistantSettingsAnchor>
      </>}
  </div>
}
