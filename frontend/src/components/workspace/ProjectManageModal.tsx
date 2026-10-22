import { usePanelEffect } from '../shared/usePanelEffect'
import { useCallback, useEffect, useRef, useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { X, Users, Trash2, Link2, UserMinus, LogOut, Pencil } from 'lucide-react'
import { useProject } from '../../hooks/useProjects'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useAuth } from '../../hooks/useAuth'
import { useTeams } from '../../hooks/useTeams'
import { useToast } from '../../contexts/ToastContext'
import { useConfirm } from '../shared/useConfirm'
import { ProjectSummaryStats } from '../projects/ProjectSummaryStats'
import { ProjectStateBadge } from '../projects/ProjectStateBadge'
import { ProjectPinsSection } from '../projects/ProjectPinsSection'
import {
  deleteProject,
  shareProjectWithTeam,
  makeProjectPersonal,
  leaveProject,
  createProjectInviteLink,
  listProjectMembers,
  removeProjectMember,
} from '../../api/projects'
import { PROJECT_STATES, type ProjectState, type ProjectMember } from '../../types/project'

/**
 * The single surface for managing the active project — opened from the project
 * context bar while a project scope is active. Replaces the old standalone
 * /projects/$uuid page so projects live entirely inside the workspace.
 */
export function ProjectManageModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { activeProjectUuid, deactivateProject, refreshActiveProject, setWorkspaceMode } = useWorkspace()
  const uuid = activeProjectUuid ?? ''
  const { project, loading, error: loadError, refresh, update } = useProject(uuid)
  const { user } = useAuth()
  const { currentTeam } = useTeams()
  const { toast } = useToast()
  const confirm = useConfirm()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [members, setMembers] = useState<ProjectMember[]>([])
  const [inviteUrl, setInviteUrl] = useState<string | null>(null)
  const [creatingLink, setCreatingLink] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [editingDesc, setEditingDesc] = useState(false)
  const [descDraft, setDescDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [stateDraft, setStateDraft] = useState<ProjectState | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const savePending = useRef(false)
  const [membersError, setMembersError] = useState(false)
  const [membersLoading, setMembersLoading] = useState(false)
  const memberRequest = useRef(0)

  const loadMembers = useCallback(() => {
    if (!uuid || !project || !['owner', 'editor'].includes(project.role)) return
    const request = ++memberRequest.current
    setMembersLoading(true)
    setMembersError(false)
    listProjectMembers(uuid).then(result => {
      if (memberRequest.current === request) setMembers(result)
    }).catch(() => {
      if (memberRequest.current === request) setMembersError(true)
    }).finally(() => {
      if (memberRequest.current === request) setMembersLoading(false)
    })
  }, [uuid, project])
  useEffect(() => {
    if (open) loadMembers()
    return () => { memberRequest.current += 1 }
  }, [open, loadMembers])

  usePanelEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented || savePending.current) return
      if (editingTitle) setEditingTitle(false)
      else if (editingDesc) setEditingDesc(false)
      else onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, editingTitle, editingDesc])

  if (!open) return null
  if (!project) return (
    <div className="fixed inset-0 z-[1000] flex justify-end bg-black/40">
      <FocusTrap focusTrapOptions={{ escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div role="dialog" aria-modal="true" aria-label="Manage project" className="h-full w-full max-w-md bg-white p-5">
          <button onClick={onClose} className="mb-6 rounded border px-3 py-2">Close</button>
          {loading ? <p role="status">Loading project…</p> : <div role="alert">
            <p>This project could not be loaded. It may be unavailable or no longer shared with you.</p>
            <button onClick={() => refresh()} className="mt-3 rounded border px-3 py-2">Retry project</button>
          </div>}
        </div>
      </FocusTrap>
    </div>
  )

  const isOwner = project.owner_user_id === user?.user_id
  const canManage = project.role === 'owner' || project.role === 'editor'

  const synced = () => {
    qc.invalidateQueries({ queryKey: ['project', uuid] })
    qc.invalidateQueries({ queryKey: ['projects'] })
    refreshActiveProject()
  }

  const saveChange = async (change: Parameters<typeof update>[0], done?: () => void) => {
    if (savePending.current) return
    savePending.current = true
    setSaving(true)
    setSaveError(null)
    try {
      await update(change)
      done?.()
      synced()
    } catch (error) {
      setSaveError(`${error instanceof Error ? error.message : 'Could not save project'}. Your edit is preserved; retry saving.`)
    } finally {
      savePending.current = false
      setSaving(false)
    }
  }

  const saveTitle = () => {
    const title = titleDraft.trim()
    if (!title) { setSaveError('Enter a project title.'); return }
    return saveChange({ title }, () => setEditingTitle(false))
  }
  const saveDesc = () => saveChange({ description: descDraft }, () => setEditingDesc(false))
  const setState = (state: ProjectState) => {
    setStateDraft(state)
    return saveChange({ state }, () => setStateDraft(null))
  }

  const handleShareWithTeam = async () => {
    setBusy(true)
    try {
      await shareProjectWithTeam(uuid)
      synced()
      toast('Shared with your team', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to share with team', 'error')
    } finally {
      setBusy(false)
    }
  }

  const handleMakePersonal = async () => {
    const ok = await confirm({
      title: 'Make project personal?',
      message: (
        <>
          Stop sharing <strong>{project.title}</strong> with your team? Its files
          and knowledge base return to you alone. Anyone invited by link keeps
          their access.
        </>
      ),
      confirmLabel: 'Make personal',
    })
    if (!ok) return
    setBusy(true)
    try {
      await makeProjectPersonal(uuid)
      synced()
      toast('Project is now personal', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to make personal', 'error')
    } finally {
      setBusy(false)
    }
  }

  const handleLeave = async () => {
    const ok = await confirm({
      title: 'Leave project?',
      message: (
        <>
          Leave <strong>{project.title}</strong>? You'll lose access until you're
          invited again. The project and its files are unaffected.
        </>
      ),
      confirmLabel: 'Leave project',
      destructive: true,
    })
    if (!ok) return
    try {
      await leaveProject(uuid)
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast('You left the project', 'success')
      deactivateProject()
      onClose()
      navigate({ to: '/', search: { mode: 'projects', tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined } })
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to leave', 'error')
    }
  }

  const handleDelete = async () => {
    const ok = await confirm({
      title: 'Delete project?',
      message: (
        <>
          Delete <strong>{project.title}</strong>? This removes the project and
          its sharing. Your files and folders are kept.
        </>
      ),
      confirmLabel: 'Delete project',
      destructive: true,
    })
    if (!ok) return
    try {
      await deleteProject(uuid)
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast('Project deleted', 'success')
      deactivateProject()
      onClose()
      navigate({ to: '/', search: { mode: 'projects', tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined } })
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to delete', 'error')
    }
  }

  const handleCreateLink = async () => {
    setCreatingLink(true)
    try {
      const link = await createProjectInviteLink(uuid, { role: 'viewer' })
      const url = `${window.location.origin}/join-project?token=${link.token}`
      setInviteUrl(url)
      try {
        await navigator.clipboard.writeText(url)
        toast('Invite link copied. Share it with a PI.', 'success')
      } catch {
        toast('Link created. Copy it from the field below.', 'info')
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to create link', 'error')
    } finally {
      setCreatingLink(false)
    }
  }

  const handleRemoveMember = async (memberUserId: string) => {
    try {
      await removeProjectMember(uuid, memberUserId)
      loadMembers()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to remove member', 'error')
    }
  }

  return (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.4)' }}
      onClick={() => { if (!savePending.current) onClose() }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        className="flex h-full w-full max-w-md flex-col overflow-y-auto bg-white shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-label="Manage project"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-gray-100 p-5">
          <div className="min-w-0 flex-1">
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-600">Manage project</div>
            <div className="flex flex-wrap items-center gap-2">
              {editingTitle ? (
                <div className="w-full">
                <input
                  autoFocus
                  disabled={saving}
                  aria-label="Project title"
                  value={titleDraft}
                  onChange={e => setTitleDraft(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); void saveTitle() } }}
                  className="w-full min-w-0 border-b border-gray-300 bg-transparent text-lg font-semibold text-gray-900 outline-none focus:border-highlight"
                />
                <div className="mt-2 flex gap-3 text-sm">
                  <button onClick={saveTitle} disabled={saving} className="rounded border px-2 py-1">{saving ? 'Saving…' : 'Save title'}</button>
                  <button onClick={() => { setEditingTitle(false); setSaveError(null) }} disabled={saving}>Cancel title</button>
                </div>
                </div>
              ) : (
                <>
                  <h2 className="min-w-0 break-words text-lg font-semibold text-gray-900">{project.title}</h2>
                  {canManage && (
                    <button onClick={() => { setTitleDraft(project.title); setEditingTitle(true) }} disabled={saving} className="p-1 text-gray-600 hover:text-gray-800" title="Rename project">
                      <Pencil size={14} />
                    </button>
                  )}
                </>
              )}
              <ProjectStateBadge state={project.state} />
            </div>
          </div>
          <button onClick={onClose} disabled={saving} className="p-1 text-gray-400 hover:text-gray-700" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-6 p-5">
          {loadError && <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">Project details could not refresh. <button onClick={() => refresh()} className="underline">Retry project</button></div>}
          {saveError && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{saveError}</p>}
          <section aria-label="Project contents" className="rounded-lg border border-gray-200 bg-gray-50 p-3">
            <h3 className="font-semibold text-gray-900">What belongs here</h3>
            <p className="mt-1 text-sm text-gray-600">Keep this project's source files, knowledge and reusable tools together.</p>
            <ProjectSummaryStats capabilities={project.capabilities} className="mt-3" />
            <p className="mt-3 text-sm text-gray-600">{canManage
              ? project.capabilities.files.count === 0 ? 'Start by adding the files your project needs.' : 'Review the source files or ask a question about this project.'
              : 'You have read-only access. Ask questions about shared project content; an owner or editor manages files and tools.'}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {canManage && <button onClick={() => { setWorkspaceMode('files'); onClose() }} className="rounded border border-gray-300 bg-white px-3 py-2 text-sm">{project.capabilities.files.count ? 'Open project files' : 'Add project files'}</button>}
              <button onClick={() => { setWorkspaceMode('chat'); onClose() }} className="rounded border border-gray-300 bg-white px-3 py-2 text-sm">Open project chat</button>
            </div>
          </section>
          <section aria-label="Project access" className="rounded-lg border border-gray-200 p-3 text-sm text-gray-600">
            <h3 className="font-semibold text-gray-900">Your access: {project.role}</h3>
            <p className="mt-1">{canManage ? 'You can update this project’s files and tools. Viewers can ask questions about shared content without changing it.' : 'You can view this project and ask questions about its shared content. An owner or editor changes its files and tools.'}</p>
            {project.team_id ? <p className="mt-2">Members of the shared team have editor access to this project.</p> : isOwner && currentTeam ? <p className="mt-2">Share with team gives members of {currentTeam.name} editor access. A PI invite link gives read-only access instead.</p> : null}
          </section>
          {/* Description */}
          <div>
            {editingDesc ? (
              <>
                <textarea
                  autoFocus
                  aria-label="Project description"
                  disabled={saving}
                  value={descDraft}
                  onChange={e => setDescDraft(e.target.value)}
                  rows={2}
                  placeholder="Describe this project…"
                  className="w-full rounded-md border border-gray-300 p-2 text-sm text-gray-600 outline-none focus:border-highlight"
                />
                <div className="mt-1 flex gap-3">
                  <button onClick={saveDesc} disabled={saving} className="rounded border px-2 py-1 text-sm">{saving ? 'Saving…' : 'Save description'}</button>
                  <button disabled={saving} onClick={() => { setEditingDesc(false); setSaveError(null) }} className="text-xs text-gray-500">Cancel</button>
                </div>
              </>
            ) : project.description ? (
              <p className="break-words text-sm text-gray-600">
                {project.description}
                {canManage && (
                  <button onClick={() => { setDescDraft(project.description || ''); setEditingDesc(true) }} disabled={saving} className="ml-2 inline-flex text-gray-600 hover:text-gray-800" title="Edit description">
                    <Pencil size={12} />
                  </button>
                )}
              </p>
            ) : canManage ? (
              <button onClick={() => { setDescDraft(''); setEditingDesc(true) }} className="text-sm text-gray-500 hover:text-gray-600">
                + Add description
              </button>
            ) : null}
          </div>

          {/* Status + sharing */}
          {canManage && (
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={stateDraft ?? project.state}
                disabled={saving}
                onChange={e => setState(e.target.value as ProjectState)}
                className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-highlight"
                title="Project status"
                aria-label="Project status"
              >
                {PROJECT_STATES.map(s => <option key={s} value={s} className="capitalize">{s}</option>)}
              </select>
              {stateDraft && saveError && <button onClick={() => setState(stateDraft)} disabled={saving} className="rounded border px-3 py-1.5 text-sm">Retry status</button>}
              {project.team_id ? (
                isOwner && (
                  <button onClick={handleMakePersonal} disabled={busy} className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                    <Users size={15} /> {busy ? 'Updating…' : 'Shared with team · Make personal'}
                  </button>
                )
              ) : isOwner && currentTeam ? (
                <button onClick={handleShareWithTeam} disabled={busy} className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                  <Users size={15} /> {busy ? 'Sharing…' : 'Share with team'}
                </button>
              ) : project.team_id && (
                <span className="inline-flex items-center gap-1 text-xs text-gray-500"><Users size={13} /> Shared with team</span>
              )}
            </div>
          )}

          {/* Pinned tools */}
          {canManage && (
            <ProjectPinsSection projectUuid={uuid} onChange={() => qc.invalidateQueries({ queryKey: ['project', uuid] })} onOpen={onClose} />
          )}

          {/* Share — invite links + members */}
          {canManage && (
            <div>
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-600">Share</div>
              <div className="rounded-lg border border-gray-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm text-gray-600">Invite a PI to view & chat (read-only).</div>
                  <button onClick={handleCreateLink} disabled={creatingLink} className="flex shrink-0 items-center gap-1.5 rounded-lg bg-highlight px-3 py-1.5 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50">
                    <Link2 size={14} /> {creatingLink ? 'Creating…' : 'Invite link'}
                  </button>
                </div>
                {inviteUrl && (
                  <div className="mt-2 flex items-center gap-2 rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
                    <input aria-label="Project invite link" readOnly value={inviteUrl} onFocus={e => e.currentTarget.select()} className="min-w-0 flex-1 bg-transparent text-xs text-gray-600 outline-none" />
                    <button onClick={() => { navigator.clipboard.writeText(inviteUrl).then(() => toast('Copied', 'success')).catch(() => toast('Could not copy. Select the link and copy it manually.', 'error')) }} className="text-xs font-medium text-gray-700">Copy</button>
                  </div>
                )}
                {membersLoading && <p role="status" className="mt-3 text-sm text-gray-600">Loading members…</p>}
                {membersError && <p role="alert" className="mt-3 text-sm text-red-800">Members could not be loaded. <button onClick={loadMembers} className="underline">Retry members</button></p>}
                <ul className="mt-3 divide-y divide-gray-100">
                  {members.map(m => (
                    <li key={m.user_id} className="flex items-center justify-between py-2">
                      <span className="min-w-0">
                        <span className="break-words text-sm text-gray-800">{m.name || m.email || m.user_id}</span>
                        <span className="ml-2 text-xs capitalize text-gray-500">{m.role}</span>
                      </span>
                      {m.role !== 'owner' && (
                        <button onClick={() => handleRemoveMember(m.user_id)} title="Remove member" className="p-1 text-gray-400 hover:text-red-500">
                          <UserMinus size={15} />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Danger zone — leave / delete */}
          <div className="flex flex-wrap gap-2 border-t border-gray-100 pt-4">
            {project.can_leave && (
              <button onClick={handleLeave} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-700 hover:text-red-500">
                <LogOut size={15} /> Leave project
              </button>
            )}
            {isOwner && (
              <button onClick={handleDelete} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-700 hover:text-red-500">
                <Trash2 size={15} /> Delete project
              </button>
            )}
          </div>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
