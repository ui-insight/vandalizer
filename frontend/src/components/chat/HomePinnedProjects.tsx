import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { FolderOpen } from 'lucide-react'
import { listProjects } from '../../api/projects'
import { useHomePinnedProjects } from '../../hooks/useHomePinnedProjects'
import type { Project } from '../../types/project'

/**
 * Projects pinned to Home from the Projects drawer (#1014 item 58). Renders
 * nothing until something is pinned, and only pins that still match a
 * project the viewer can list.
 */
export function HomePinnedProjects({ disabled }: { disabled?: boolean }) {
  const navigate = useNavigate()
  const { pinned } = useHomePinnedProjects()
  // Same entry as the Projects drawer: the project search param scopes the workspace.
  const onOpen = (uuid: string) => {
    try { localStorage.setItem('workspace:mode', 'chat') } catch { /* URL navigation remains available. */ }
    navigate({ to: '/', search: { mode: 'chat', tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: uuid, workflow_share_token: undefined } })
  }
  const { data: projects = [] } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: () => listProjects(),
    enabled: pinned.length > 0,
  })
  const byUuid = new Map(projects.map(p => [p.uuid, p]))
  const shown = pinned.map(uuid => byUuid.get(uuid)).filter((p): p is Project => !!p)
  if (!shown.length) return null
  return (
    <section className="home-activity" aria-label="Pinned projects">
      <h3>Pinned projects</h3>
      <ul>
        {shown.map(p => (
          <li key={p.uuid}>
            <FolderOpen size={18} aria-hidden="true" />
            <div><strong>{p.title}</strong></div>
            <button type="button" className="home-text-action" disabled={disabled} onClick={() => onOpen(p.uuid)} aria-label={`Open project: ${p.title}`}>Open</button>
          </li>
        ))}
      </ul>
    </section>
  )
}
