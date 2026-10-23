import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useProject } from '../../hooks/useProjects'
import { useProjectPins } from '../../hooks/useProjectPins'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { ProjectStateBadge } from './ProjectStateBadge'
import { ProjectSummaryStats } from './ProjectSummaryStats'
import type { ProjectPin } from '../../types/project'

/** Routine project work belongs beside the document/tool workspace. */
export function ProjectWorkOverview({ uuid }: { uuid: string }) {
  const { project, loading, error, refresh } = useProject(uuid)
  const { activeProjectRole, setWorkspaceMode, focusChat } = useWorkspace()
  const [expanded, setExpanded] = useState(false)
  const navigate = useNavigate()
  const viewer = activeProjectRole === 'viewer'
  const { pins, loading: pinsLoading, error: pinsError, refresh: refreshPins } = useProjectPins(viewer ? null : uuid)
  const openPin = (pin: ProjectPin) => {
    navigate({ to: '/', search: previous => ({ ...previous, project: uuid,
      mode: pin.pin_type === 'automation' ? 'automations' : pin.pin_type === 'knowledge_base' ? 'knowledge' : 'files',
      tab: 'library', workflow: pin.pin_type === 'workflow' ? pin.target_id : undefined,
      extraction: pin.pin_type === 'extraction' ? pin.target_id : undefined,
      automation: pin.pin_type === 'automation' ? pin.target_id : undefined,
      kb: pin.pin_type === 'knowledge_base' ? pin.target_id : undefined, workflow_share_token: undefined,
    }) })
  }
  return <div className="project-work-overview">
    <div className="project-work-overview__summary">
      {project && <><ProjectStateBadge state={project.state} /><ProjectSummaryStats capabilities={project.capabilities} /></>}
      {loading && <span role="status">Loading project overview…</span>}
      {error && <span role="alert">Project overview unavailable. <button type="button" onClick={() => void refresh()}>Retry</button></span>}
      <div className="project-work-overview__actions">
        {!viewer && <button type="button" onClick={() => setWorkspaceMode('files')}>Open files</button>}
        <button type="button" onClick={() => { setWorkspaceMode('chat'); focusChat() }}>Ask about project</button>
        {!viewer && <button type="button" aria-expanded={expanded} aria-controls="project-pinned-work" onClick={() => setExpanded(v => !v)}>Pinned tools{!pinsLoading && !pinsError ? ` (${pins.length})` : ''}</button>}
      </div>
    </div>
    {expanded && !viewer && <div id="project-pinned-work" className="project-work-overview__pins">
      <p>Pinned tools open with this project selected. Check their input before running; opening a tool does not run it.</p>
      {pinsLoading ? <span role="status">Loading pinned tools…</span> : pinsError ? <span role="alert">{pinsError} <button type="button" onClick={() => void refreshPins()}>Retry pinned tools</button></span> : pins.length ? <div className="project-work-overview__actions">{pins.map(pin => <button type="button" key={`${pin.pin_type}:${pin.target_id}`} onClick={() => openPin(pin)}>{pin.name} · {pin.pin_type.replaceAll('_', ' ')}</button>)}</div> : <p>No tools pinned yet. Use Manage project → Pinned tools to add a reusable tool.</p>}
    </div>}
  </div>
}
