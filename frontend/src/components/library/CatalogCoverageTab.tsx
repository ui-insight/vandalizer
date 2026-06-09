import { useCallback, useEffect, useState } from 'react'
import { ShieldCheck, AlertTriangle, Pin, Wrench, CheckCircle2, Filter } from 'lucide-react'
import { listCatalogCoverage } from '../../api/library'
import type { CatalogCoverageItem } from '../../types/library'
import { RetroactiveBaselineDialog } from './RetroactiveBaselineDialog'

type Coverage = '' | 'none' | 'snapshot_only' | 'pinned_baseline' | 'drift_checked'
type Kind = '' | 'workflow' | 'search_set' | 'knowledge_base'

const COVERAGE_LABEL: Record<string, string> = {
  none: 'No validation',
  snapshot_only: 'Snapshot only',
  pinned_baseline: 'Pinned baseline',
  drift_checked: 'Drift checked',
}
const COVERAGE_STYLE: Record<string, string> = {
  none: 'bg-red-50 text-red-700 border-red-200',
  snapshot_only: 'bg-amber-50 text-amber-700 border-amber-200',
  pinned_baseline: 'bg-blue-50 text-blue-700 border-blue-200',
  drift_checked: 'bg-green-50 text-green-700 border-green-200',
}
const COVERAGE_ICON: Record<string, typeof ShieldCheck> = {
  none: AlertTriangle,
  snapshot_only: ShieldCheck,
  pinned_baseline: Pin,
  drift_checked: CheckCircle2,
}

function kindLabel(k: string) {
  if (k === 'workflow') return 'Workflow'
  if (k === 'search_set') return 'Extraction'
  if (k === 'knowledge_base') return 'Knowledge Base'
  return k
}

export function CatalogCoverageTab() {
  const [items, setItems] = useState<CatalogCoverageItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [coverage, setCoverage] = useState<Coverage>('')
  const [kind, setKind] = useState<Kind>('')
  const [editing, setEditing] = useState<CatalogCoverageItem | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listCatalogCoverage({
        kind: kind || undefined,
        coverage: coverage || undefined,
        limit: 200,
      })
      setItems(data.items)
      setTotal(data.total)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [coverage, kind])

  useEffect(() => { refresh() }, [refresh])

  // Summary counts
  const counts = items.reduce<Record<string, number>>((acc, it) => {
    acc[it.coverage] = (acc[it.coverage] || 0) + 1
    return acc
  }, {})

  return (
    <div>
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-1">
          <h2 className="text-base font-semibold text-gray-900">Validation coverage</h2>
          <span className="text-xs text-gray-500">({total} verified items)</span>
        </div>
        <p className="text-xs text-gray-500">
          Verified catalog items by validation coverage. Items without a pinned baseline have no drift contract — clicking <strong>Establish baseline</strong> creates one retroactively.
        </p>
      </div>

      {/* Summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
        {(['none', 'snapshot_only', 'pinned_baseline', 'drift_checked'] as const).map(c => {
          const Icon = COVERAGE_ICON[c]
          const count = counts[c] || 0
          const active = coverage === c
          return (
            <button
              key={c}
              onClick={() => setCoverage(active ? '' : c)}
              className={`text-left p-3 rounded-lg border transition-all ${active ? 'ring-2 ring-gray-900' : ''} ${COVERAGE_STYLE[c]}`}
            >
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4" />
                <div className="text-xs font-semibold">{COVERAGE_LABEL[c]}</div>
              </div>
              <div className="text-2xl font-bold mt-1">{count}</div>
            </button>
          )
        })}
      </div>

      {/* Kind filter */}
      <div className="flex items-center gap-2 mb-3">
        <Filter className="h-3 w-3 text-gray-400" />
        {(['', 'workflow', 'search_set', 'knowledge_base'] as const).map(k => (
          <button
            key={k || 'all'}
            onClick={() => setKind(k)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium border ${kind === k ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'}`}
          >
            {k ? kindLabel(k) : 'All kinds'}
          </button>
        ))}
        {coverage && (
          <button onClick={() => setCoverage('')} className="ml-auto text-xs text-gray-500 underline">
            Clear coverage filter
          </button>
        )}
      </div>

      {loading ? (
        <div className="text-sm text-gray-500 py-8 text-center">Loading…</div>
      ) : items.length === 0 ? (
        <div className="text-sm text-gray-500 py-12 text-center">
          {coverage ? `No items with coverage "${COVERAGE_LABEL[coverage]}".` : 'No verified items.'}
        </div>
      ) : (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr className="text-left text-xs font-semibold text-gray-600">
                <th className="px-3 py-2">Item</th>
                <th className="px-3 py-2">Kind</th>
                <th className="px-3 py-2">Coverage</th>
                <th className="px-3 py-2">Current score</th>
                <th className="px-3 py-2">Pinned</th>
                <th className="px-3 py-2">Drift check</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => {
                const Icon = COVERAGE_ICON[it.coverage]
                const driftDelta =
                  it.official_baseline_score != null && it.last_drift_score != null
                    ? it.official_baseline_score - it.last_drift_score
                    : null
                return (
                  <tr key={`${it.item_kind}:${it.item_id}`} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-3 py-2 font-medium text-gray-900 truncate max-w-xs">{it.name}</td>
                    <td className="px-3 py-2 text-gray-600 text-xs">{kindLabel(it.item_kind)}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border ${COVERAGE_STYLE[it.coverage]}`}>
                        <Icon className="h-3 w-3" />
                        {COVERAGE_LABEL[it.coverage]}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-600">
                      {it.quality_score != null ? `${Math.round(it.quality_score)}%` : '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-600">
                      {it.official_baseline_score != null ? (
                        <div>
                          <div>{Math.round(it.official_baseline_score)}% pinned</div>
                          <div className="text-[10px] text-gray-400">{it.official_baseline_test_case_count} case(s)</div>
                        </div>
                      ) : '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-600">
                      {it.last_drift_check_at ? (
                        <div>
                          <div>{new Date(it.last_drift_check_at).toLocaleDateString()}</div>
                          {driftDelta != null && (
                            <div className={`text-[10px] ${driftDelta >= 10 ? 'text-red-600' : driftDelta >= 5 ? 'text-amber-600' : 'text-gray-400'}`}>
                              {driftDelta > 0 ? `-${driftDelta.toFixed(1)} pts` : 'stable'}
                            </div>
                          )}
                        </div>
                      ) : '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        onClick={() => setEditing(it)}
                        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                      >
                        <Wrench className="h-3 w-3" />
                        {it.official_baseline_pinned_at ? 'Update baseline' : 'Establish baseline'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <RetroactiveBaselineDialog
          item={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); refresh() }}
        />
      )}
    </div>
  )
}
