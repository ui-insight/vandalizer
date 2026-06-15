import { useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Search, FolderKanban, Users } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { ProjectStateBadge } from '../components/projects/ProjectStateBadge'
import { useProjects } from '../hooks/useProjects'

export default function Projects() {
  const navigate = useNavigate()
  const { projects, loading, create } = useProjects()
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState('')

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
          <div className="text-gray-500 text-sm text-center py-12">
            {search
              ? 'No projects match your search.'
              : 'No projects yet. Create one above to get started.'}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {filtered.map(p => (
              <button
                key={p.uuid}
                onClick={() => navigate({ to: '/', search: { mode: 'files', tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: p.uuid, workflow_share_token: undefined } })}
                className="flex flex-col items-start rounded-lg border border-gray-200 bg-white p-4 text-left hover:border-highlight transition-colors"
              >
                <div className="flex w-full items-center justify-between gap-2">
                  <span className="font-medium text-gray-900 truncate">{p.title}</span>
                  <ProjectStateBadge state={p.state} />
                </div>
                {p.description && (
                  <span className="mt-1 text-sm text-gray-500 line-clamp-2">{p.description}</span>
                )}
                <div className="mt-3 flex items-center gap-3 text-xs text-gray-400">
                  {p.team_id && (
                    <span className="inline-flex items-center gap-1">
                      <Users size={12} /> Team
                    </span>
                  )}
                  <span>Updated {new Date(p.updated_at).toLocaleDateString()}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </PageLayout>
  )
}
