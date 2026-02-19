import { useEffect, useState } from 'react'
import {
  Zap,
  FolderSearch,
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  Workflow,
  TrendingUp,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { getAutomationStats } from '../api/config'
import { listWorkflows } from '../api/workflows'
import type { AutomationStats } from '../api/config'
import type { Workflow as WorkflowType } from '../types/workflow'

function statusBadge(status: string) {
  switch (status) {
    case 'completed':
      return { icon: CheckCircle, className: 'text-green-600', label: 'Completed' }
    case 'running':
      return { icon: Activity, className: 'text-blue-600', label: 'Running' }
    case 'error':
    case 'failed':
      return { icon: XCircle, className: 'text-red-600', label: 'Failed' }
    default:
      return { icon: Clock, className: 'text-gray-500', label: status }
  }
}

export default function Automation() {
  const [stats, setStats] = useState<AutomationStats | null>(null)
  const [workflows, setWorkflows] = useState<WorkflowType[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([getAutomationStats(), listWorkflows()])
      .then(([s, w]) => {
        setStats(s)
        setWorkflows(w)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <PageLayout>
        <div className="mx-auto max-w-5xl py-12 text-center text-sm text-gray-500">
          Loading automation dashboard...
        </div>
      </PageLayout>
    )
  }

  return (
    <PageLayout>
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-gray-400" />
          <h2 className="text-xl font-semibold text-gray-900">Automation Dashboard</h2>
        </div>

        {/* Stats cards */}
        {stats && (
          <div className="grid grid-cols-4 gap-4">
            <StatCard
              icon={Workflow}
              label="Total Workflows"
              value={stats.total_workflows}
              color="blue"
            />
            <StatCard
              icon={Zap}
              label="Passive Workflows"
              value={stats.passive_workflows}
              color="purple"
            />
            <StatCard
              icon={FolderSearch}
              label="Watched Folders"
              value={stats.watched_folders}
              color="yellow"
            />
            <StatCard
              icon={TrendingUp}
              label="Runs This Week"
              value={stats.runs_this_week}
              color="green"
            />
          </div>
        )}

        {/* Today's summary */}
        {stats && (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Today</h3>
            <div className="flex items-center gap-6 text-sm">
              <span className="text-gray-600">
                {stats.runs_today} run{stats.runs_today !== 1 ? 's' : ''}
              </span>
              <span className="flex items-center gap-1 text-green-600">
                <CheckCircle className="h-3.5 w-3.5" />
                {stats.runs_today_success} succeeded
              </span>
              <span className="flex items-center gap-1 text-red-600">
                <XCircle className="h-3.5 w-3.5" />
                {stats.runs_today_failed} failed
              </span>
            </div>
          </div>
        )}

        {/* Workflows with automation status */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
            <Workflow className="h-4 w-4 text-gray-400" />
            <h3 className="font-medium text-gray-900">Workflows</h3>
          </div>
          <div className="divide-y divide-gray-100">
            {workflows.length === 0 ? (
              <div className="p-6 text-center text-sm text-gray-500">
                No workflows found.
              </div>
            ) : (
              workflows.map((wf) => {
                const inputConfig = (wf as WorkflowType & { input_config?: Record<string, unknown> })
                  .input_config as Record<string, unknown> | undefined
                const folderWatch = inputConfig?.folder_watch as
                  | { enabled?: boolean; folders?: string[] }
                  | undefined
                const isPassive = folderWatch?.enabled === true

                return (
                  <div key={wf.id} className="flex items-center justify-between px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-gray-900">{wf.name}</div>
                      {wf.description && (
                        <div className="text-xs text-gray-500 truncate mt-0.5">
                          {wf.description}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-3 shrink-0 ml-4">
                      <span className="text-xs text-gray-400">
                        {wf.num_executions} run{wf.num_executions !== 1 ? 's' : ''}
                      </span>
                      {isPassive ? (
                        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                          <Zap className="h-3 w-3" />
                          Passive
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-500 border border-gray-200">
                          Manual
                        </span>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Recent runs */}
        {stats && stats.recent_runs.length > 0 && (
          <div className="rounded-lg border border-gray-200 bg-white">
            <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3">
              <Activity className="h-4 w-4 text-gray-400" />
              <h3 className="font-medium text-gray-900">Recent Runs</h3>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100 text-left">
                  <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">
                    Status
                  </th>
                  <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">
                    Trigger
                  </th>
                  <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">
                    Progress
                  </th>
                  <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">
                    Started
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {stats.recent_runs.map((run) => {
                  const badge = statusBadge(run.status)
                  const Icon = badge.icon
                  return (
                    <tr key={run.id}>
                      <td className="px-4 py-3">
                        <span className={`flex items-center gap-1.5 text-sm ${badge.className}`}>
                          <Icon className="h-3.5 w-3.5" />
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`text-xs px-2 py-0.5 rounded border ${
                            run.is_passive
                              ? 'bg-purple-50 text-purple-700 border-purple-200'
                              : 'bg-gray-50 text-gray-600 border-gray-200'
                          }`}
                        >
                          {run.trigger_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {run.steps_completed}/{run.steps_total} steps
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500">
                        {run.started_at
                          ? new Date(run.started_at).toLocaleString()
                          : 'Unknown'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageLayout>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: typeof Workflow
  label: string
  value: number
  color: 'blue' | 'purple' | 'yellow' | 'green'
}) {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-700',
    purple: 'bg-purple-50 text-purple-700',
    yellow: 'bg-yellow-50 text-yellow-700',
    green: 'bg-green-50 text-green-700',
  }
  const iconColor = {
    blue: 'text-blue-400',
    purple: 'text-purple-400',
    yellow: 'text-yellow-400',
    green: 'text-green-400',
  }

  return (
    <div className={`rounded-lg p-4 ${colorMap[color]}`}>
      <div className="flex items-center justify-between mb-2">
        <Icon className={`h-5 w-5 ${iconColor[color]}`} />
      </div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs mt-0.5 opacity-80">{label}</div>
    </div>
  )
}
