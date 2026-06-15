import { useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Search, FolderKanban } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { ProjectExplorerCard } from '../components/projects/ProjectExplorerCard'
import { ProjectsExplainer } from '../components/projects/ProjectsExplainer'
import { useProjects } from '../hooks/useProjects'
import { useToast } from '../contexts/ToastContext'
import { useConfirm } from '../components/shared/useConfirm'
import type { Project, ProjectState } from '../types/project'

export default function Projects() {
  const navigate = useNavigate()
  const { projects, loading, create, update, remove } = useProjects()
  const { toast } = useToast()
  const confirm = useConfirm()
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState('')

  const enterWorkspace = (uuid: string) =>
    navigate({ to: '/', search: { mode: 'files', tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: uuid, workflow_share_token: undefined } })

  const handleRename = async (uuid: string, title: string) => {
    try {
      await update(uuid, { title })
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to rename project', 'error')
    }
  }

  const handleSetState = async (uuid: string, state: ProjectState) => {
    try {
      await update(uuid, { state })
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to update status', 'error')
    }
  }

  const handleDelete = async (p: Project) => {
    const ok = await confirm({
      title: 'Delete project?',
      message: (
        <>
          Delete <strong>{p.title}</strong>? This removes the project and its
          sharing — your files and folders are kept.
        </>
      ),
      confirmLabel: 'Delete project',
      destructive: true,
    })
    if (!ok) return
    try {
      await remove(p.uuid)
      toast('Project deleted', 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to delete', 'error')
    }
  }

  const filtered = useMemo(() => {
    if (!search.trim()) return projects
    const q = search.toLowerCase()
    return projects.filter(
      p =>
        p.title.toLowerCase().includes(q) ||
        (p.description || '').toLowerCase().includes(q),
    )
  }, [projects, search])

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const project = await create(newName.trim())
      setNewName('')
      navigate({ to: '/projects/$uuid', params: { uuid: project.uuid } })
    } finally {
      setCreating(false)
    }
  }

  return (
    <PageLayout>
      <div className="p-6 max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-1">
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-gray-900">
            <FolderKanban className="h-6 w-6 text-gray-400" />
            Projects
          </h1>
          <span className="text-sm text-gray-400">{projects.length} total</span>
        </div>
        <p className="mb-6 text-sm text-gray-500">
          A project gathers everything for one piece of work — its files, a
          knowledge base you can chat with, and the workflows, extractions, and
          automations that act on it.
        </p>

        {/* Create new */}
        <div className="mb-5">
          <div className="flex gap-2">
            <input
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="New project name (e.g. NIH R01 — Smith Lab)..."
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
            />
            <button
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
              className="flex items-center gap-1 px-4 py-2 bg-highlight text-highlight-text rounded-lg text-sm font-bold hover:brightness-90 disabled:opacity-50"
            >
              <Plus size={16} />
              Create
            </button>
          </div>
        </div>

        {/* Search */}
        {projects.length > 0 && (
          <div className="relative mb-4">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search projects..."
              className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight bg-white"
            />
          </div>
        )}

        {/* List */}
        {loading ? (
          <div className="text-gray-500 text-sm">Loading...</div>
        ) : filtered.length === 0 ? (
          search ? (
            <div className="text-gray-500 text-sm text-center py-12">
              No projects match your search.
            </div>
          ) : (
            <ProjectsExplainer />
          )
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {filtered.map(p => (
              <ProjectExplorerCard
                key={p.uuid}
                project={p}
                canManage={p.role === 'owner' || p.role === 'editor'}
                canDelete={p.role === 'owner'}
                onOpen={() => enterWorkspace(p.uuid)}
                onOpenHome={() => navigate({ to: '/projects/$uuid', params: { uuid: p.uuid } })}
                onRename={title => handleRename(p.uuid, title)}
                onSetState={state => handleSetState(p.uuid, state)}
                onDelete={() => handleDelete(p)}
              />
            ))}
          </div>
        )}
      </div>
    </PageLayout>
  )
}
