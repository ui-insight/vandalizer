import { Cog } from 'lucide-react'
import { LEVEL_CONFIG } from './constants'

export function XpMilestones({ levels, totalXp }: { levels: { name: string; xp: number }[]; totalXp: number }) {
  return <details className="rounded-lg border border-gray-200 bg-white p-2 sm:p-4">
    <summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold text-gray-900">
      <Cog size={14} aria-hidden="true" className="mr-2 inline-block" />XP milestones
    </summary>
    <p className="mb-3 text-sm text-gray-700">XP milestones are separate from course completion. Certification requires completing the course’s required module checks.</p>
    <ul aria-label="XP milestones" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {levels.map(level => <li key={level.name} className="min-w-0 rounded-lg border border-gray-200 bg-gray-50 p-2 text-sm text-gray-900 [overflow-wrap:anywhere]">
        <span className="block font-semibold">{LEVEL_CONFIG[level.name]?.label || level.name}</span>
        <span className="mt-1 block text-xs text-gray-700">{level.xp.toLocaleString()} XP · {totalXp >= level.xp ? 'Reached' : 'Not reached'}</span>
      </li>)}
    </ul>
  </details>
}
