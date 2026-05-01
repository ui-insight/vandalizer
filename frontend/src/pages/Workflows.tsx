import { useMemo, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Copy, Trash2, Search, ArrowUpDown } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useWorkflows } from '../hooks/useWorkflows'
import { useToast } from '../contexts/ToastContext'

type SortKey = 'name' | 'runs' | 'steps'

export default function Workflows() {
  const navigate = useNavigate()
  const { workflows, loading, create, remove, duplicate, importFromFile } = useWorkflows()
  const { toast } = useToast()
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [importing, setImporting] = useState(false)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<SortKey>('name')
  const [sortAsc, setSortAsc] = useState(true)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const filtered = useMemo(() => {
    let list = workflows
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(wf =>
        wf.name.toLowerCase().includes(q) ||
        (wf.description || '').toLowerCase().includes(q)
      )
    }
    return [...list].sort((a, b) => {
      let cmp = 0
      if (sortBy === 'name') cmp = a.name.localeCompare(b.name)
      else if (sortBy === 'runs') cmp = (a.num_executions || 0) - (b.num_executions || 0)
      else if (sortBy === 'steps') cmp = (a.steps?.length || 0) - (b.steps?.length || 0)
      return sortAsc ? cmp : -cmp
    })
  }, [workflows, search, sortBy, sortAsc])

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

  const handleImportFile = async (file: File) => {
    setImporting(true)
    try {
      const wf = await importFromFile(file)
      toast(`Imported "${wf.name}"`, 'success')
      navigate({ to: '/workflows/$id', params: { id: wf.id } })
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Import failed', 'error')
    } finally {
      setImporting(false)
    }
  }

  const toggleSort = (key: SortKey) => {
    if (sortBy === key) setSortAsc(!sortAsc)
    else { setSortBy(key); setSortAsc(true) }
  }

  return (
    <PageLayout>
      <div className="p-6 max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">Workflows</h1>
          <span className="text-sm text-gray-400">{workflows.length} total</span>
        </div>

        {/* Create new */}
        <div className="mb-4">
          <div className="flex gap-2">
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
          <div className="mt-1.5 text-xs text-gray-400">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={importing}
              className="hover:text-gray-600 hover:underline disabled:opacity-50"
            >
              {importing ? 'Importing...' : 'or import from JSON'}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={e => {
                const f = e.target.files?.[0]
                if (f) handleImportFile(f)
                e.target.value = ''
              }}
            />
          </div>
        </div>

        {/* Search & Sort */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search workflows..."
              className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight bg-white"
            />
          </div>
          <div className="flex gap-1">
            {(['name', 'runs', 'steps'] as SortKey[]).map(key => (
              <button
                key={key}
                onClick={() => toggleSort(key)}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border ${
                  sortBy === key
                    ? 'bg-gray-100 border-gray-300 text-gray-900'
                    : 'bg-white border-gray-200 text-gray-500 hover:bg-gray-50'
                }`}
              >
                {key === 'name' ? 'Name' : key === 'runs' ? 'Runs' : 'Steps'}
                {sortBy === key && <ArrowUpDown size={12} />}
              </button>
            ))}
          </div>
        </div>

        {/* List */}
        {loading ? (
          <div className="text-gray-500 text-sm">Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="text-gray-500 text-sm text-center py-12">
            {search ? 'No workflows match your search.' : 'No workflows yet. Create one above to get started.'}
          </div>
        ) : (
          <div className="grid gap-3">
            {filtered.map(wf => (
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
