import { useCallback, useEffect, useState } from 'react'
import {
  Cloud,
  Mail,
  FolderOpen,
  HardDrive,
  Plus,
  Power,
  PowerOff,
  Trash2,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  Shield,
  Eye,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import {
  getOfficeStatus,
  listIntakes,
  createIntake,
  updateIntake,
  deleteIntake,
  listWorkItems,
  approveWorkItem,
} from '../api/office'
import type { OfficeStatus, IntakeConfig, WorkItem } from '../api/office'

type Tab = 'intakes' | 'workitems'

const INTAKE_TYPES = [
  { value: 'outlook_shared', label: 'Shared Mailbox', icon: Mail },
  { value: 'outlook_folder', label: 'Outlook Folder', icon: FolderOpen },
  { value: 'onedrive_drop', label: 'OneDrive Drop Zone', icon: HardDrive },
] as const

function workItemStatusBadge(status: string) {
  switch (status) {
    case 'completed':
      return { icon: CheckCircle, className: 'bg-green-50 text-green-700 border-green-200' }
    case 'processing':
    case 'triaged':
      return { icon: Clock, className: 'bg-blue-50 text-blue-700 border-blue-200' }
    case 'awaiting_review':
      return { icon: Eye, className: 'bg-yellow-50 text-yellow-700 border-yellow-200' }
    case 'failed':
      return { icon: XCircle, className: 'bg-red-50 text-red-700 border-red-200' }
    case 'rejected':
      return { icon: XCircle, className: 'bg-gray-50 text-gray-500 border-gray-200' }
    default:
      return { icon: Clock, className: 'bg-gray-50 text-gray-600 border-gray-200' }
  }
}

export default function Office() {
  const [tab, setTab] = useState<Tab>('intakes')
  const [status, setStatus] = useState<OfficeStatus | null>(null)
  const [intakes, setIntakes] = useState<IntakeConfig[]>([])
  const [workItems, setWorkItems] = useState<WorkItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')

  // Create form state
  const [newName, setNewName] = useState('')
  const [newType, setNewType] = useState('outlook_shared')
  const [newMailbox, setNewMailbox] = useState('')
  const [newFolderPath, setNewFolderPath] = useState('')

  const refreshIntakes = useCallback(async () => {
    const data = await listIntakes()
    setIntakes(data.intakes)
  }, [])

  const refreshWorkItems = useCallback(async () => {
    const data = await listWorkItems(statusFilter || undefined)
    setWorkItems(data.items)
  }, [statusFilter])

  useEffect(() => {
    Promise.all([getOfficeStatus(), listIntakes(), listWorkItems()])
      .then(([s, i, w]) => {
        setStatus(s)
        setIntakes(i.intakes)
        setWorkItems(w.items)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!loading) refreshWorkItems()
  }, [statusFilter, refreshWorkItems, loading])

  const handleCreateIntake = async () => {
    if (!newName.trim()) return
    await createIntake({
      name: newName.trim(),
      intake_type: newType,
      mailbox_address: newType !== 'onedrive_drop' ? newMailbox.trim() || undefined : undefined,
      folder_path: newType === 'onedrive_drop' ? newFolderPath.trim() || undefined : undefined,
    })
    setNewName('')
    setNewMailbox('')
    setNewFolderPath('')
    setShowCreate(false)
    refreshIntakes()
  }

  const handleToggle = async (intake: IntakeConfig) => {
    await updateIntake(intake.uuid, { enabled: !intake.enabled })
    refreshIntakes()
  }

  const handleDelete = async (uuid: string) => {
    await deleteIntake(uuid)
    refreshIntakes()
  }

  const handleApprove = async (uuid: string) => {
    await approveWorkItem(uuid)
    refreshWorkItems()
  }

  if (loading) {
    return (
      <PageLayout>
        <div className="mx-auto max-w-5xl py-12 text-center text-sm text-gray-500">
          Loading Office integration...
        </div>
      </PageLayout>
    )
  }

  return (
    <PageLayout>
      <div className="mx-auto max-w-5xl space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cloud className="h-5 w-5 text-gray-400" />
            <h2 className="text-xl font-semibold text-gray-900">Office 365 Integration</h2>
          </div>
          <div className="flex items-center gap-2">
            {status?.connected ? (
              <span className="flex items-center gap-1.5 text-sm text-green-600">
                <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                Connected
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-sm text-gray-400">
                <span className="h-2 w-2 rounded-full bg-gray-300" />
                Not connected
              </span>
            )}
          </div>
        </div>

        {!status?.connected && (
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-700">
            Connect your Microsoft 365 account to enable email intake and OneDrive integration.
            Use the Flask admin panel at <code>/office/connect</code> to authorize.
          </div>
        )}

        {/* Tab bar */}
        <div className="flex gap-0 border-b border-gray-200">
          {(['intakes', 'workitems'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-3 text-sm font-semibold transition-colors ${
                tab === t
                  ? 'border-b-2 border-gray-900 text-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {t === 'intakes' ? 'Intake Configs' : 'Work Items'}
            </button>
          ))}
        </div>

        {/* Intakes tab */}
        {tab === 'intakes' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-500">
                {intakes.length} intake{intakes.length !== 1 ? 's' : ''} configured
              </div>
              <button
                onClick={() => setShowCreate(!showCreate)}
                className="flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800"
              >
                <Plus className="h-3.5 w-3.5" />
                New Intake
              </button>
            </div>

            {/* Create form */}
            {showCreate && (
              <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
                    <input
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="My Intake"
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Type</label>
                    <select
                      value={newType}
                      onChange={(e) => setNewType(e.target.value)}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
                    >
                      {INTAKE_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
                {newType !== 'onedrive_drop' ? (
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Mailbox Address
                    </label>
                    <input
                      value={newMailbox}
                      onChange={(e) => setNewMailbox(e.target.value)}
                      placeholder="shared-mailbox@university.edu"
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
                    />
                  </div>
                ) : (
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      OneDrive Folder Path
                    </label>
                    <input
                      value={newFolderPath}
                      onChange={(e) => setNewFolderPath(e.target.value)}
                      placeholder="/Vandalizer/Intake"
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
                    />
                  </div>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={handleCreateIntake}
                    disabled={!newName.trim()}
                    className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
                  >
                    Create
                  </button>
                  <button
                    onClick={() => setShowCreate(false)}
                    className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Intakes list */}
            {intakes.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
                No intake configurations yet. Create one to start monitoring.
              </div>
            ) : (
              <div className="space-y-2">
                {intakes.map((intake) => {
                  const typeInfo = INTAKE_TYPES.find((t) => t.value === intake.intake_type)
                  const Icon = typeInfo?.icon || Mail
                  return (
                    <div
                      key={intake.uuid}
                      className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-4"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <Icon className="h-5 w-5 text-gray-400 shrink-0" />
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900">{intake.name}</div>
                          <div className="text-xs text-gray-500">
                            {typeInfo?.label || intake.intake_type}
                            {intake.mailbox_address && ` — ${intake.mailbox_address}`}
                            {intake.folder_path && ` — ${intake.folder_path}`}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => handleToggle(intake)}
                          className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${
                            intake.enabled
                              ? 'bg-green-50 text-green-700 hover:bg-green-100'
                              : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                          }`}
                        >
                          {intake.enabled ? (
                            <>
                              <Power className="h-3 w-3" /> Active
                            </>
                          ) : (
                            <>
                              <PowerOff className="h-3 w-3" /> Paused
                            </>
                          )}
                        </button>
                        <button
                          onClick={() => handleDelete(intake.uuid)}
                          className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* Work Items tab */}
        {tab === 'workitems' && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
              >
                <option value="">All statuses</option>
                <option value="received">Received</option>
                <option value="triaged">Triaged</option>
                <option value="processing">Processing</option>
                <option value="awaiting_review">Awaiting Review</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
              </select>
              <span className="text-sm text-gray-500">
                {workItems.length} item{workItems.length !== 1 ? 's' : ''}
              </span>
            </div>

            {workItems.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
                No work items found.
              </div>
            ) : (
              <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-100 text-left bg-gray-50">
                      <th className="px-4 py-2.5 text-xs font-medium uppercase text-gray-500">Status</th>
                      <th className="px-4 py-2.5 text-xs font-medium uppercase text-gray-500">Subject</th>
                      <th className="px-4 py-2.5 text-xs font-medium uppercase text-gray-500">Source</th>
                      <th className="px-4 py-2.5 text-xs font-medium uppercase text-gray-500">Category</th>
                      <th className="px-4 py-2.5 text-xs font-medium uppercase text-gray-500">Received</th>
                      <th className="px-4 py-2.5 text-xs font-medium uppercase text-gray-500">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {workItems.map((item) => {
                      const badge = workItemStatusBadge(item.status)
                      const Icon = badge.icon
                      return (
                        <tr key={item.uuid}>
                          <td className="px-4 py-3">
                            <span
                              className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border ${badge.className}`}
                            >
                              <Icon className="h-3 w-3" />
                              {item.status}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="text-sm text-gray-900 max-w-xs truncate">
                              {item.subject || 'No subject'}
                            </div>
                            {item.sender_name && (
                              <div className="text-xs text-gray-500">{item.sender_name}</div>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-600">{item.source}</td>
                          <td className="px-4 py-3">
                            {item.triage_category ? (
                              <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-700">
                                {item.triage_category}
                              </span>
                            ) : (
                              <span className="text-xs text-gray-400">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500">
                            {item.received_at
                              ? new Date(item.received_at).toLocaleDateString()
                              : item.created_at
                                ? new Date(item.created_at).toLocaleDateString()
                                : '—'}
                          </td>
                          <td className="px-4 py-3">
                            {item.status === 'awaiting_review' && (
                              <button
                                onClick={() => handleApprove(item.uuid)}
                                className="flex items-center gap-1 text-xs font-medium text-green-600 hover:text-green-700"
                              >
                                <CheckCircle className="h-3.5 w-3.5" />
                                Approve
                              </button>
                            )}
                            {item.sensitivity_flags.length > 0 && (
                              <span className="flex items-center gap-1 text-xs text-yellow-600" title={item.sensitivity_flags.join(', ')}>
                                <AlertTriangle className="h-3 w-3" />
                                {item.sensitivity_flags.length} flag{item.sensitivity_flags.length !== 1 ? 's' : ''}
                              </span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </PageLayout>
  )
}
