import { FolderKanban, FolderOpen, Settings, LogOut } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useProject } from '../../hooks/useProjects'
import { ProjectStateBadge } from '../projects/ProjectStateBadge'

export function ProjectContextBar({ onOpenManage, railWidth: fittedRailWidth }: { onOpenManage?: () => void; railWidth?: number }) {
  const { activeProjectUuid, activeProjectTitle, activeProjectRole, deactivateProject, railDocked, setWorkspaceMode } = useWorkspace()
  const { project, error, refresh } = useProject(activeProjectUuid ?? '')
  if (!activeProjectUuid) return null
  const railWidth = fittedRailWidth ?? (railDocked ? 64 : 320)
  return <div role="region" aria-label="Active project" className="project-context-bar project-header" style={{ marginRight: railWidth }}>
    <div className="project-header-identity">
      <span className="project-header-icon"><FolderKanban size={20} aria-hidden="true" /></span>
      <div className="min-w-0"><span className="project-eyebrow">Project{activeProjectRole === 'viewer' ? ' · Read only' : ''}</span><div className="project-header-name">{activeProjectTitle}</div></div>
      {project && <ProjectStateBadge state={project.state} />}
    </div>
    <div className="project-header-actions">
      {activeProjectRole !== 'viewer' && <button className="project-button" type="button" onClick={() => setWorkspaceMode('files')}><FolderOpen size={16} />Open files</button>}
      {onOpenManage && <button className="project-button" type="button" onClick={onOpenManage} title="View details, tools and sharing"><Settings size={16} />Manage project</button>}
      <button className="project-button project-button-quiet" type="button" onClick={deactivateProject} title="Exit project scope"><LogOut size={15} />Exit project</button>
    </div>
    {error && <p role="alert" className="w-full text-sm text-red-800">Project details unavailable. <button className="underline" onClick={() => void refresh()}>Retry project</button></p>}
  </div>
}
