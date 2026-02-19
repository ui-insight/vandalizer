import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Copy, Trash2 } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useWorkflows } from '../hooks/useWorkflows'

export default function Workflows() {
  const navigate = useNavigate()
  const { workflows, loading, create, remove, duplicate } = useWorkflows()
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const wf = await create(newName.trim())
      setNewName('')
      navigate({ to: '/workflows/$id', params: { id: wf.id } })
    } finally {
      setCreating(false)
    }
  }

  return (
    <PageLayout>
      <div className="p-6 max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">Workflows</h1>
        </div>

        {/* Create new */}
        <div className="flex gap-2 mb-6">
          <input
            type="text"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCreate()}
            placeholder="New workflow name..."
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

        {/* List */}
        {loading ? (
          <div className="text-gray-500 text-sm">Loading...</div>
        ) : workflows.length === 0 ? (
          <div className="text-gray-500 text-sm text-center py-12">
            No workflows yet. Create one above to get started.
          </div>
        ) : (
          <div className="grid gap-3">
            {workflows.map(wf => (
              <div
                key={wf.id}
                className="flex items-center justify-between p-4 bg-white rounded-lg border border-gray-200 hover:border-highlight cursor-pointer transition-colors"
                onClick={() => navigate({ to: '/workflows/$id', params: { id: wf.id } })}
              >
                <div className="min-w-0">
                  <div className="font-medium text-gray-900 truncate">{wf.name}</div>
                  {wf.description && (
                    <div className="text-sm text-gray-500 truncate">{wf.description}</div>
                  )}
                  <div className="text-xs text-gray-400 mt-1">
                    {wf.steps?.length || 0} steps &middot; {wf.num_executions} runs
                  </div>
                </div>
                <div className="flex items-center gap-1 ml-4 shrink-0">
                  <button
                    onClick={e => { e.stopPropagation(); duplicate(wf.id) }}
                    className="p-2 text-gray-400 hover:text-gray-600 rounded"
                    title="Duplicate"
                  >
                    <Copy size={16} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); remove(wf.id) }}
                    className="p-2 text-gray-400 hover:text-red-500 rounded"
                    title="Delete"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </PageLayout>
  )
}
