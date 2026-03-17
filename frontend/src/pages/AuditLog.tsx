import { useEffect, useState } from 'react'
import { FileText, Download, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import * as api from '../api/audit'
import type { AuditLogEntry } from '../api/audit'

const ACTION_COLORS: Record<string, string> = {
  'document.create': 'bg-green-100 text-green-700',
  'document.delete': 'bg-red-100 text-red-700',
  'document.classify': 'bg-amber-100 text-amber-700',
  'extraction.run': 'bg-blue-100 text-blue-700',
  'workflow.run': 'bg-purple-100 text-purple-700',
  'workflow.approve': 'bg-green-100 text-green-700',
  'workflow.reject': 'bg-red-100 text-red-700',
  'user.login': 'bg-gray-100 text-gray-700',
  'config.update': 'bg-orange-100 text-orange-700',
  'org.create': 'bg-blue-100 text-blue-700',
  'team.create': 'bg-indigo-100 text-indigo-700',
}

function formatTime(ts: string | null): string {
  if (!ts) return '—'
  const d = new Date(ts)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function AuditLog() {
  const { user } = useAuth()
  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [actionFilter, setActionFilter] = useState('')
  const [resourceTypeFilter, setResourceTypeFilter] = useState('')
  const limit = 25

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.queryAuditLog({
        action: actionFilter || undefined,
        resource_type: resourceTypeFilter || undefined,
        skip: page * limit,
        limit,
      })
      setEntries(data.entries)
      setTotal(data.total)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [page, actionFilter, resourceTypeFilter])

  if (!user?.is_admin) {
    return (
      <PageLayout>
        <div className="text-center text-gray-500">Admin access required</div>
      </PageLayout>
    )
  }

  const totalPages = Math.ceil(total / limit)

  return (
    <PageLayout>
      <div className="mx-auto max-w-6xl">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FileText className="h-6 w-6 text-gray-700" />
            <h1 className="text-2xl font-bold text-gray-900">Audit Log</h1>
            <span className="text-sm text-gray-500">({total} entries)</span>
          </div>
          <a
            href={api.exportAuditLog({ action: actionFilter, resource_type: resourceTypeFilter })}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            <Download className="h-4 w-4" />
            Export CSV
          </a>
        </div>

        {/* Filters */}
        <div className="mb-4 flex gap-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={actionFilter}
              onChange={(e) => {
                setActionFilter(e.target.value)
                setPage(0)
              }}
              className="rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm"
              placeholder="Filter by action..."
            />
          </div>
          <select
            value={resourceTypeFilter}
            onChange={(e) => {
              setResourceTypeFilter(e.target.value)
              setPage(0)
            }}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">All resources</option>
            <option value="document">Document</option>
            <option value="workflow">Workflow</option>
            <option value="extraction">Extraction</option>
            <option value="user">User</option>
            <option value="team">Team</option>
            <option value="config">Config</option>
            <option value="organization">Organization</option>
            <option value="approval">Approval</option>
          </select>
        </div>

        {/* Table */}
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Time</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Action</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Actor</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Resource</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                    Loading...
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                    No audit log entries found
                  </td>
                </tr>
              ) : (
                entries.map((entry) => (
                  <tr key={entry.uuid} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-600">
                      {formatTime(entry.timestamp)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${ACTION_COLORS[entry.action] || 'bg-gray-100 text-gray-700'}`}
                      >
                        {entry.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {entry.actor_user_id}
                      {entry.actor_type !== 'user' && (
                        <span className="ml-1 text-xs text-gray-400">({entry.actor_type})</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span className="text-gray-700">{entry.resource_name || entry.resource_id || '—'}</span>
                      <span className="ml-1 text-xs text-gray-400">{entry.resource_type}</span>
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 text-xs text-gray-500">
                      {Object.keys(entry.detail).length > 0
                        ? JSON.stringify(entry.detail).slice(0, 80)
                        : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between">
            <span className="text-sm text-gray-500">
              Page {page + 1} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-50"
              >
                <ChevronLeft className="h-4 w-4" /> Previous
              </button>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-50"
              >
                Next <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </PageLayout>
  )
}
