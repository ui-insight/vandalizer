import { PROJECT_STATES } from '../../types/project'
import type { Project, ProjectState } from '../../types/project'

export type ProjectSort = 'updated' | 'created' | 'name' | 'stage'

export const PROJECT_SORT_LABELS: Record<ProjectSort, string> = {
  updated: 'Recently updated',
  created: 'Newest first',
  name: 'Name (A–Z)',
  stage: 'Stage',
}

export interface ProjectListView {
  query: string
  stage: ProjectState | 'all'
  sort: ProjectSort
}

const time = (iso: string) => {
  const t = new Date(iso).getTime()
  return Number.isNaN(t) ? 0 : t
}

const byName = (a: Project, b: Project) =>
  a.title.localeCompare(b.title, undefined, { sensitivity: 'base', numeric: true })

/** Projects per stage, for the filter pills. */
export function countByStage(projects: Project[]): Record<ProjectState, number> {
  const counts = Object.fromEntries(PROJECT_STATES.map(s => [s, 0])) as Record<ProjectState, number>
  for (const p of projects) counts[p.state] = (counts[p.state] ?? 0) + 1
  return counts
}

/** The projects to show: matching the search (title or description) and
 *  stage, in the chosen order. Ties fall back to name so the order is stable. */
export function applyProjectListView(projects: Project[], view: ProjectListView): Project[] {
  const q = view.query.trim().toLowerCase()
  const shown = projects.filter(p =>
    (view.stage === 'all' || p.state === view.stage)
    && (!q || p.title.toLowerCase().includes(q) || (p.description ?? '').toLowerCase().includes(q)),
  )
  const compare: Record<ProjectSort, (a: Project, b: Project) => number> = {
    updated: (a, b) => time(b.updated_at) - time(a.updated_at) || byName(a, b),
    created: (a, b) => time(b.created_at) - time(a.created_at) || byName(a, b),
    name: byName,
    // Lifecycle order (draft → archived), most recently updated first within a stage.
    stage: (a, b) =>
      PROJECT_STATES.indexOf(a.state) - PROJECT_STATES.indexOf(b.state)
      || time(b.updated_at) - time(a.updated_at)
      || byName(a, b),
  }
  return [...shown].sort(compare[view.sort])
}
