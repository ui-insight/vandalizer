import { useCallback, useEffect, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { X, Users, Trash2, Link2, UserMinus, LogOut, Pencil } from 'lucide-react'
import { useProject } from '../../hooks/useProjects'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useAuth } from '../../hooks/useAuth'
import { useTeams } from '../../hooks/useTeams'
import { useToast } from '../../contexts/ToastContext'
import { useConfirm } from '../shared/useConfirm'
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
  const { activeProjectUuid, deactivateProject, refreshActiveProject } = useWorkspace()
  const uuid = activeProjectUuid ?? ''
  const { project, update } = useProject(uuid)
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

  const loadMembers = useCallback(() => {
    if (!uuid) return
    listProjectMembers(uuid).then(setMembers).catch(() => {})
  }, [uuid])
  useEffect(() => { if (open) loadMembers() }, [open, loadMembers])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || !project) return null

  const isOwner = project.owner_user_id === user?.user_id
  const canManage = project.role === 'owner' || project.role === 'editor'

  const synced = () => {
    qc.invalidateQueries({ queryKey: ['project', uuid] })
    qc.invalidateQueries({ queryKey: ['projects'] })
    refreshActiveProject()
  }

  const saveTitle = async () => {
    const t = titleDraft.trim()
    setEditingTitle(false)
    if (t && t !== project.title) {
      await update({ title: t })
      synced()
    }
  }

  const saveDesc = async () => {
    await update({ description: descDraft })
    setEditingDesc(false)
    synced()
  }

  const setState = async (state: ProjectState) => {
    await update({ state })
    synced()
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
          its sharing — your files and folders are kept.
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
      await navigator.clipboard.writeText(url).catch(() => {})
      toast('Invite link copied — share it with a PI', 'success')
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
      onClick={onClose}
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
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400">Manage project</div>
            <div className="flex items-center gap-2">
              {editingTitle ? (
                <input
                  autoFocus
                  aria-label="Project title"
                  value={titleDraft}
                  onChange={e => setTitleDraft(e.target.value)}
                  onBlur={saveTitle}
                  onKeyDown={e => { if (e.key === 'Enter') saveTitle(); if (e.key === 'Escape') setEditingTitle(false) }}
                  className="min-w-0 flex-1 border-b border-gray-300 bg-transparent text-lg font-semibold text-gray-900 outline-none focus:border-highlight"
                />
              ) : (
                <>
                  <h2 className="truncate text-lg font-semibold text-gray-900">{project.title}</h2>
                  {canManage && (
                    <button onClick={() => { setTitleDraft(project.title); setEditingTitle(true) }} className="p-1 text-gray-300 hover:text-gray-600" title="Rename project">
                      <Pencil size={14} />
                    </button>
                  )}
                </>
              )}
              <ProjectStateBadge state={project.state} />
            </div>
          </div>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-700" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-6 p-5">
          {/* Description */}
          <div>
            {editingDesc ? (
              <>
                <textarea
                  autoFocus
                  aria-label="Project description"
                  value={descDraft}
                  onChange={e => setDescDraft(e.target.value)}
                  rows={2}
                  placeholder="Describe this project…"
                  className="w-full rounded-md border border-gray-300 p-2 text-sm text-gray-600 outline-none focus:border-highlight"
                />
                <div className="mt-1 flex gap-3">
                  <button onClick={saveDesc} className="text-xs font-medium text-highlight">Save</button>
                  <button onClick={() => setEditingDesc(false)} className="text-xs text-gray-500">Cancel</button>
                </div>
              </>
            ) : project.description ? (
              <p className="inline-flex items-center gap-1.5 text-sm text-gray-600">
                {project.description}
                {canManage && (
                  <button onClick={() => { setDescDraft(project.description || ''); setEditingDesc(true) }} className="text-gray-300 hover:text-gray-600" title="Edit description">
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
                value={project.state}
                onChange={e => setState(e.target.value as ProjectState)}
                className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-highlight"
                title="Project status"
                aria-label="Project status"
              >
                {PROJECT_STATES.map(s => <option key={s} value={s} className="capitalize">{s}</option>)}
              </select>
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
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">Share</div>
              <div className="rounded-lg border border-gray-200 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm text-gray-600">Invite a PI to view & chat (read-only).</div>
                  <button onClick={handleCreateLink} disabled={creatingLink} className="flex shrink-0 items-center gap-1.5 rounded-lg bg-highlight px-3 py-1.5 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50">
                    <Link2 size={14} /> {creatingLink ? 'Creating…' : 'Invite link'}
                  </button>
                </div>
                {inviteUrl && (
                  <div className="mt-2 flex items-center gap-2 rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
                    <input readOnly value={inviteUrl} onFocus={e => e.currentTarget.select()} className="flex-1 bg-transparent text-xs text-gray-600 outline-none" />
                    <button onClick={() => { navigator.clipboard.writeText(inviteUrl); toast('Copied', 'success') }} className="text-xs font-medium text-highlight">Copy</button>
                  </div>
                )}
                <ul className="mt-3 divide-y divide-gray-100">
                  {members.map(m => (
                    <li key={m.user_id} className="flex items-center justify-between py-2">
                      <span className="min-w-0">
                        <span className="text-sm text-gray-800">{m.name || m.email || m.user_id}</span>
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
