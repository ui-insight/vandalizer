import { useNavigate, useParams } from '@tanstack/react-router'
import {
  ChevronRight,
  FileText,
  Sparkles,
  Workflow,
  FileSearch,
  Zap,
  Users,
  MessageSquare,
  Trash2,
  BookOpen,
  Link2,
  UserMinus,
  Pencil,
} from 'lucide-react'
import { useCallback, useEffect, useState, type ComponentType } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { PageLayout } from '../components/layout/PageLayout'
import { ProjectStateBadge } from '../components/projects/ProjectStateBadge'
import { ProjectPinsSection } from '../components/projects/ProjectPinsSection'
import { useProject } from '../hooks/useProjects'
import { useAuth } from '../hooks/useAuth'
import { useTeams } from '../hooks/useTeams'
import { useToast } from '../contexts/ToastContext'
import { useConfirm } from '../components/shared/useConfirm'
import {
  deleteProject,
  shareProjectWithTeam,
  createProjectInviteLink,
  listProjectMembers,
  removeProjectMember,
} from '../api/projects'
import { PROJECT_STATES, type ProjectState, type ProjectMember } from '../types/project'

type ScopedMode = 'files' | 'chat' | 'automations' | 'knowledge'

interface CapabilityTile {
  key: string
  icon: ComponentType<{ size?: number; className?: string }>
  label: string
  detail: string
  hint: string
  mode?: ScopedMode // when set, the tile enters the scoped workspace in this mode
}

export default function ProjectDetail() {
  const { uuid } = useParams({ strict: false }) as { uuid: string }
  const navigate = useNavigate()
  const { project, loading, update } = useProject(uuid)
  const { user } = useAuth()
  const { currentTeam } = useTeams()
  const { toast } = useToast()
  const confirm = useConfirm()
  const qc = useQueryClient()

  const [members, setMembers] = useState<ProjectMember[]>([])
  const [inviteUrl, setInviteUrl] = useState<string | null>(null)
  const [creatingLink, setCreatingLink] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [editingDesc, setEditingDesc] = useState(false)
  const [descDraft, setDescDraft] = useState('')
  const [sharing, setSharing] = useState(false)

  const loadMembers = useCallback(() => {
    if (!uuid) return
    listProjectMembers(uuid).then(setMembers).catch(() => {})
  }, [uuid])
  useEffect(() => { loadMembers() }, [loadMembers])

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

  if (loading) {
    return (
      <PageLayout>
        <div className="p-6 text-sm text-gray-500">Loading project...</div>
      </PageLayout>
    )
  }

  if (!project) {
    return (
      <PageLayout>
        <div className="p-6 max-w-3xl mx-auto text-center">
          <p className="text-gray-600">Project not found.</p>
          <button
            onClick={() => navigate({ to: '/projects' })}
            className="mt-3 text-sm text-highlight hover:underline"
          >
            Back to all projects
          </button>
        </div>
      </PageLayout>
    )
  }

  const isOwner = project.owner_user_id === user?.user_id
  const canManage = project.role === 'owner' || project.role === 'editor'
  const caps = project.capabilities

  // Enter the real workspace, scoped to this project, in the given mode.
  // The workspace reuses its existing Files/Chat/Automations/Knowledge UIs —
  // this page never re-implements them.
  const enterProject = (mode: ScopedMode) =>
    navigate({
      to: '/',
      search: {
        mode,
        tab: undefined,
        workflow: undefined,
        extraction: undefined,
        automation: undefined,
        kb: undefined,
        project: project.uuid,
        workflow_share_token: undefined,
      },
    })

  const tiles: CapabilityTile[] = [
    {
      key: 'files',
      icon: FileText,
      label: 'Files',
      detail: `${caps.files.count} file${caps.files.count === 1 ? '' : 's'} · ${caps.files.folders} folder${caps.files.folders === 1 ? '' : 's'}`,
      hint: 'Upload & organize in the file browser',
      mode: 'files',
    },
    {
      key: 'knowledge',
      icon: Sparkles,
      label: 'Knowledge base',
      detail: caps.knowledge.ready
        ? `${caps.knowledge.documents} document${caps.knowledge.documents === 1 ? '' : 's'} indexed`
        : 'Building as you add files',
      hint: 'Auto-built from your files — chat just works',
    },
    {
      key: 'automations',
      icon: Zap,
      label: 'Automations',
      detail: `${caps.automations.count} pinned`,
      hint: 'Run actions when files arrive',
    },
    {
      key: 'workflows',
      icon: Workflow,
      label: 'Workflows',
      detail: `${caps.workflows.count} pinned`,
      hint: 'Multi-step tasks for this project',
    },
    {
      key: 'extractions',
      icon: FileSearch,
      label: 'Extractions',
      detail: `${caps.extractions.count} pinned`,
      hint: 'Pull structured data into the project',
    },
    {
      key: 'members',
      icon: Users,
      label: 'Members',
      detail: `${caps.members.count} member${caps.members.count === 1 ? '' : 's'}`,
      hint: 'Share with PIs to ask questions',
    },
  ]

  const saveTitle = async () => {
    const t = titleDraft.trim()
    if (t && t !== project.title) await update({ title: t })
    setEditingTitle(false)
  }

  const saveDesc = async () => {
    await update({ description: descDraft })
    setEditingDesc(false)
  }

  const handleShareWithTeam = async () => {
    setSharing(true)
    try {
      await shareProjectWithTeam(project.uuid)
      qc.invalidateQueries({ queryKey: ['project', project.uuid] })
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast('Shared with your team', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to share with team', 'error')
    } finally {
      setSharing(false)
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
      await deleteProject(project.uuid)
      toast('Project deleted', 'success')
      navigate({ to: '/projects' })
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to delete', 'error')
    }
  }

  return (
    <PageLayout>
      <div className="p-6 max-w-5xl mx-auto">
        {/* Breadcrumb */}
        <div className="mb-4 flex items-center gap-1 text-sm text-gray-500">
          <button onClick={() => navigate({ to: '/projects' })} className="hover:text-gray-700">
            Projects
          </button>
          <ChevronRight size={14} className="text-gray-300" />
          <span className="font-medium text-gray-700">{project.title}</span>
        </div>

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              {editingTitle ? (
                <input
                  autoFocus
                  value={titleDraft}
                  onChange={e => setTitleDraft(e.target.value)}
                  onBlur={saveTitle}
                  onKeyDown={e => {
                    if (e.key === 'Enter') saveTitle()
                    if (e.key === 'Escape') setEditingTitle(false)
                  }}
                  className="flex-1 border-b border-gray-300 bg-transparent text-2xl font-semibold text-gray-900 outline-none focus:border-highlight"
                />
              ) : (
                <>
                  <h1 className="truncate text-2xl font-semibold text-gray-900">{project.title}</h1>
                  {canManage && (
                    <button
                      onClick={() => { setTitleDraft(project.title); setEditingTitle(true) }}
                      className="p-1 text-gray-300 hover:text-gray-600"
                      title="Rename project"
                    >
                      <Pencil size={14} />
                    </button>
                  )}
                </>
              )}
              <ProjectStateBadge state={project.state} />
            </div>

            {editingDesc ? (
              <div className="mt-2">
                <textarea
                  autoFocus
                  value={descDraft}
                  onChange={e => setDescDraft(e.target.value)}
                  rows={2}
                  placeholder="Describe this project…"
                  className="w-full rounded-md border border-gray-300 p-2 text-sm text-gray-600 outline-none focus:border-highlight"
                />
                <div className="mt-1 flex gap-3">
                  <button onClick={saveDesc} className="text-xs font-medium text-highlight">Save</button>
                  <button onClick={() => setEditingDesc(false)} className="text-xs text-gray-400">Cancel</button>
                </div>
              </div>
            ) : project.description ? (
              <p className="mt-1 inline-flex items-center gap-1.5 text-sm text-gray-500">
                {project.description}
                {canManage && (
                  <button
                    onClick={() => { setDescDraft(project.description || ''); setEditingDesc(true) }}
                    className="text-gray-300 hover:text-gray-600"
                    title="Edit description"
                  >
                    <Pencil size={12} />
                  </button>
                )}
              </p>
            ) : canManage ? (
              <button
                onClick={() => { setDescDraft(''); setEditingDesc(true) }}
                className="mt-1 text-sm text-gray-400 hover:text-gray-600"
              >
                + Add description
              </button>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {project.team_id ? (
              <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                <Users size={13} /> Shared with team
              </span>
            ) : isOwner && currentTeam ? (
              <button
                onClick={handleShareWithTeam}
                disabled={sharing}
                title={`Share with ${currentTeam.name}`}
                className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                <Users size={15} />
                {sharing ? 'Sharing…' : 'Share with team'}
              </button>
            ) : null}
            <select
              value={project.state}
              onChange={e => update({ state: e.target.value as ProjectState })}
              className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-highlight"
              title="Project status"
            >
              {PROJECT_STATES.map(s => (
                <option key={s} value={s} className="capitalize">
                  {s}
                </option>
              ))}
            </select>
            {isOwner && (
              <button
                onClick={handleDelete}
                className="rounded-lg p-2 text-gray-400 hover:text-red-500"
                title="Delete project"
              >
                <Trash2 size={16} />
              </button>
            )}
          </div>
        </div>

        {/* Chat hero — the headline capability */}
        <button
          onClick={() => enterProject('chat')}
          className="mt-6 flex w-full items-center gap-4 rounded-xl border border-highlight/30 bg-highlight/5 p-5 text-left hover:bg-highlight/10 transition-colors"
        >
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-highlight text-highlight-text">
            <MessageSquare size={20} />
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-gray-900">Chat with this project</div>
            <div className="text-sm text-gray-500">
              Ask questions across every file in the project — no setup needed.
            </div>
          </div>
        </button>

        {/* Capability grid — each tile that maps to a workspace mode opens the
            real, scoped workspace; the rest are at-a-glance status. */}
        <h2 className="mt-8 mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
          In this project
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {tiles.map(({ key, icon: Icon, label, detail, hint, mode }) => {
            const inner = (
              <>
                <div className="flex items-center gap-2 text-gray-900">
                  <Icon size={18} className="text-gray-400" />
                  <span className="font-medium">{label}</span>
                </div>
                <div className="mt-2 text-lg font-semibold text-gray-900">{detail}</div>
                <div className="mt-0.5 text-xs text-gray-400">{hint}</div>
              </>
            )
            return mode ? (
              <button
                key={key}
                onClick={() => enterProject(mode)}
                className="rounded-lg border border-gray-200 bg-white p-4 text-left hover:border-highlight transition-colors"
              >
                {inner}
              </button>
            ) : (
              <div key={key} className="rounded-lg border border-gray-200 bg-white p-4">
                {inner}
              </div>
            )
          })}
        </div>

        {/* Pinned tools — quick access to the workflows/extractions for this project */}
        {canManage && (
          <ProjectPinsSection
            projectUuid={project.uuid}
            onChange={() => qc.invalidateQueries({ queryKey: ['project', uuid] })}
          />
        )}

        {/* Share — invite PIs to view & chat with the project (read-only) */}
        {canManage && (
          <div className="mt-8">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
              Share
            </h2>
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm text-gray-600">
                  Invite a PI to view and chat with this project (read-only).
                </div>
                <button
                  onClick={handleCreateLink}
                  disabled={creatingLink}
                  className="flex shrink-0 items-center gap-1.5 rounded-lg bg-highlight px-3 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50"
                >
                  <Link2 size={15} />
                  {creatingLink ? 'Creating…' : 'Create invite link'}
                </button>
              </div>
              {inviteUrl && (
                <div className="mt-3 flex items-center gap-2 rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
                  <input
                    readOnly
                    value={inviteUrl}
                    onFocus={e => e.currentTarget.select()}
                    className="flex-1 bg-transparent text-xs text-gray-600 outline-none"
                  />
                  <button
                    onClick={() => { navigator.clipboard.writeText(inviteUrl); toast('Copied', 'success') }}
                    className="text-xs font-medium text-highlight"
                  >
                    Copy
                  </button>
                </div>
              )}
              <div className="mt-4">
                <div className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-gray-400">
                  <Users size={13} /> Members
                </div>
                <ul className="divide-y divide-gray-100">
                  {members.map(m => (
                    <li key={m.user_id} className="flex items-center justify-between py-2">
                      <span className="min-w-0">
                        <span className="text-sm text-gray-800">{m.name || m.email || m.user_id}</span>
                        <span className="ml-2 text-xs capitalize text-gray-400">{m.role}</span>
                      </span>
                      {m.role !== 'owner' && (
                        <button
                          onClick={() => handleRemoveMember(m.user_id)}
                          title="Remove member"
                          className="p-1 text-gray-400 hover:text-red-500"
                        >
                          <UserMinus size={15} />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {caps.external_kbs.count > 0 && (
          <div className="mt-3 inline-flex items-center gap-1.5 text-xs text-gray-500">
            <BookOpen size={13} />
            {caps.external_kbs.count} external knowledge base
            {caps.external_kbs.count === 1 ? '' : 's'} attached
          </div>
        )}
      </div>
    </PageLayout>
  )
}
