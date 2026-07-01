import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle, FileText, Layers, Lock, Pause, RefreshCw, ShieldCheck, Tag, Trash2,
} from 'lucide-react'

import {
  getClassificationDashboard,
  getRetentionDashboard,
  type ClassificationDashboard,
  type ClassificationLevel,
  type RetentionDashboard,
  type RetentionPolicy,
} from '../../api/admin'

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = iso.endsWith('Z') || iso.includes('+') ? new Date(iso) : new Date(iso + 'Z')
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatRetention(days?: number): string {
  if (!days) return '—'
  if (days >= 365) {
    const years = days / 365
    return Number.isInteger(years) ? `${years} yr` : `${years.toFixed(1)} yr`
  }
  return `${days} days`
}

function ClassificationChip({ name, levels }: { name: string; levels: ClassificationLevel[] }) {
  const level = levels.find(l => l.name === name)
  const color = level?.color ?? '#9ca3af'
  const label = level?.label ?? name
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '2px 10px', borderRadius: 9999,
      fontSize: 12, fontWeight: 600,
      backgroundColor: `${color}1a`, color,
      border: `1px solid ${color}66`,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: 9999, backgroundColor: color }} />
      {label}
    </span>
  )
}

function StatCard({ icon: Icon, label, value, color }: {
  icon: typeof Tag
  label: string
  value: string | number
  color: string
}) {
  return (
    <div style={{
      flex: 1, minWidth: 160,
      backgroundColor: '#fff', border: '1px solid #e5e7eb',
      borderRadius: 8, padding: 16,
      display: 'flex', flexDirection: 'column', gap: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#6b7280', fontSize: 13 }}>
        <Icon size={16} color={color} />
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color: '#111827' }}>{value}</div>
    </div>
  )
}

export function ComplianceTab() {
  const [classification, setClassification] = useState<ClassificationDashboard | null>(null)
  const [retention, setRetention] = useState<RetentionDashboard | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [c, r] = await Promise.all([getClassificationDashboard(), getRetentionDashboard()])
      setClassification(c)
      setRetention(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load compliance data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void reload() }, [reload])

  if (loading && !classification && !retention) {
    return <div style={{ padding: 24, color: '#6b7280' }}>Loading…</div>
  }
  if (error) {
    return (
      <div style={{ padding: 16, backgroundColor: '#fef2f2', border: '1px solid #fecaca',
                    borderRadius: 8, color: '#991b1b' }}>
        {error}
      </div>
    )
  }
  if (!classification || !retention) return null

  const levels = classification.config.levels
  const totalDocs = Object.values(retention.document_counts).reduce((a, b) => a + b, 0)

  return (
    <div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 24,
      }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Compliance</h2>
          <p style={{ fontSize: 14, color: '#6b7280' }}>
            Document classification (FERPA / CUI / ITAR) and retention policy enforcement.
          </p>
        </div>
        <button
          onClick={() => void reload()}
          disabled={loading}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '8px 14px', borderRadius: 6,
            backgroundColor: '#fff', color: '#374151',
            border: '1px solid #d1d5db', fontWeight: 500, cursor: 'pointer',
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Top-line stats */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 28 }}>
        <StatCard icon={FileText} label="Total documents" value={totalDocs.toLocaleString()} color="#3b82f6" />
        <StatCard icon={Trash2} label="Pending deletions" value={retention.pending_deletions} color="#f59e0b" />
        <StatCard icon={Layers} label="Soft-deleted" value={retention.soft_deleted} color="#6b7280" />
        <StatCard icon={Pause} label="Retention holds" value={retention.retention_holds} color="#8b5cf6" />
      </div>

      {/* Classification section */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Tag size={18} color="#3b82f6" />
          <h3 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>Classification</h3>
          <span style={{
            fontSize: 12, padding: '2px 8px', borderRadius: 9999,
            backgroundColor: classification.config.enabled ? '#dcfce7' : '#f3f4f6',
            color: classification.config.enabled ? '#166534' : '#6b7280',
            fontWeight: 600,
          }}>
            {classification.config.enabled ? 'Enabled' : 'Disabled'}
          </span>
          {classification.config.auto_classify_on_upload && (
            <span style={{ fontSize: 12, color: '#6b7280' }}>
              · Auto-classify on upload
            </span>
          )}
        </div>

        <div style={{
          backgroundColor: '#fff', border: '1px solid #e5e7eb',
          borderRadius: 8, padding: 16, marginBottom: 16,
        }}>
          <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 12, fontWeight: 600 }}>
            Documents by classification
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {levels.map(level => {
              const count = classification.counts[level.name] ?? 0
              return (
                <div key={level.name} style={{
                  flex: '1 1 140px', minWidth: 140,
                  padding: 12, borderRadius: 6,
                  backgroundColor: `${level.color}0d`,
                  borderLeft: `3px solid ${level.color}`,
                }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: level.color, marginBottom: 4 }}>
                    {level.label}
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 700 }}>{count.toLocaleString()}</div>
                </div>
              )
            })}
            {classification.counts['unclassified'] !== undefined && (
              <div style={{
                flex: '1 1 140px', minWidth: 140,
                padding: 12, borderRadius: 6,
                backgroundColor: '#f9fafb', borderLeft: '3px solid #6b7280',
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>
                  Unclassified
                </div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>
                  {classification.counts['unclassified'].toLocaleString()}
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{
          backgroundColor: '#fff', border: '1px solid #e5e7eb',
          borderRadius: 8, overflow: 'hidden',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '12px 16px', borderBottom: '1px solid #e5e7eb', fontSize: 13, fontWeight: 600,
          }}>
            <span>Recent classifications</span>
            <span style={{ color: '#6b7280', fontWeight: 400 }}>
              {classification.recent_classifications.length} shown
            </span>
          </div>
          {classification.recent_classifications.length === 0 ? (
            <div style={{ padding: 24, fontSize: 13, color: '#6b7280', textAlign: 'center' }}>
              No documents have been classified yet.
            </div>
          ) : (
            <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: '#f9fafb', color: '#6b7280', textAlign: 'left' }}>
                  <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Title</th>
                  <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Classification</th>
                  <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Confidence</th>
                  <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>When</th>
                  <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>By</th>
                </tr>
              </thead>
              <tbody>
                {classification.recent_classifications.map(row => (
                  <tr key={row.uuid} style={{ borderTop: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '10px 16px', maxWidth: 320, overflow: 'hidden',
                                 textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.title || <span style={{ color: '#6b7280' }}>Untitled</span>}
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      {row.classification
                        ? <ClassificationChip name={row.classification} levels={levels} />
                        : <span style={{ color: '#6b7280' }}>—</span>}
                    </td>
                    <td style={{ padding: '10px 16px', color: '#6b7280' }}>
                      {row.confidence != null ? `${Math.round(row.confidence * 100)}%` : '—'}
                    </td>
                    <td style={{ padding: '10px 16px', color: '#6b7280' }}>
                      {formatDateTime(row.classified_at)}
                    </td>
                    <td style={{ padding: '10px 16px', color: '#6b7280' }}>
                      {row.classified_by || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Retention section */}
      <section>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <ShieldCheck size={18} color="#22c55e" />
          <h3 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>Retention</h3>
          <span style={{
            fontSize: 12, padding: '2px 8px', borderRadius: 9999,
            backgroundColor: retention.retention_config.enabled ? '#dcfce7' : '#fef3c7',
            color: retention.retention_config.enabled ? '#166534' : '#92400e',
            fontWeight: 600,
          }}>
            {retention.retention_config.enabled ? 'Enforcement on' : 'Enforcement paused'}
          </span>
        </div>

        {!retention.retention_config.enabled && (
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: 10,
            backgroundColor: '#fffbeb', border: '1px solid #fde68a',
            borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 13, color: '#92400e',
          }}>
            <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              Retention enforcement is currently off. Documents will not be auto-scheduled for
              deletion. Turn it on under <strong>Config → System Config → Document Retention
              Policy</strong>.
            </div>
          </div>
        )}

        <div style={{
          backgroundColor: '#fff', border: '1px solid #e5e7eb',
          borderRadius: 8, overflow: 'hidden', marginBottom: 16,
        }}>
          <div style={{
            padding: '12px 16px', borderBottom: '1px solid #e5e7eb',
            fontSize: 13, fontWeight: 600,
          }}>
            Per-classification retention policies
          </div>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#f9fafb', color: '#6b7280', textAlign: 'left' }}>
                <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Tier</th>
                <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Retention period</th>
                <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Grace before purge</th>
                <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Documents</th>
              </tr>
            </thead>
            <tbody>
              {levels.map(level => {
                const policy: RetentionPolicy =
                  retention.retention_config.policies[level.name] ?? {}
                const count = retention.document_counts[level.name] ?? 0
                return (
                  <tr key={level.name} style={{ borderTop: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '10px 16px' }}>
                      <ClassificationChip name={level.name} levels={levels} />
                    </td>
                    <td style={{ padding: '10px 16px' }}>{formatRetention(policy.retention_days)}</td>
                    <td style={{ padding: '10px 16px', color: '#6b7280' }}>
                      {policy.soft_delete_grace_days
                        ? `${policy.soft_delete_grace_days} days`
                        : '—'}
                    </td>
                    <td style={{ padding: '10px 16px', color: '#6b7280' }}>
                      {count.toLocaleString()}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div style={{
          backgroundColor: '#fff', border: '1px solid #e5e7eb',
          borderRadius: 8, padding: 16,
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>
            Other retention windows
          </div>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 13 }}>
            <div>
              <div style={{ color: '#6b7280', marginBottom: 2 }}>Activity logs</div>
              <div style={{ fontWeight: 600 }}>
                {formatRetention(retention.retention_config.activity_retention_days)}
              </div>
            </div>
            <div>
              <div style={{ color: '#6b7280', marginBottom: 2 }}>Chat conversations</div>
              <div style={{ fontWeight: 600 }}>
                {formatRetention(retention.retention_config.chat_retention_days)}
              </div>
            </div>
            <div>
              <div style={{ color: '#6b7280', marginBottom: 2 }}>Workflow results</div>
              <div style={{ fontWeight: 600 }}>
                {formatRetention(retention.retention_config.workflow_result_retention_days)}
              </div>
            </div>
            <div>
              <div style={{ color: '#6b7280', marginBottom: 2 }}>Stale activity threshold</div>
              <div style={{ fontWeight: 600 }}>
                {retention.retention_config.activity_stale_threshold_minutes
                  ? `${retention.retention_config.activity_stale_threshold_minutes} min`
                  : '—'}
              </div>
            </div>
          </div>
        </div>

        <div style={{
          marginTop: 12, fontSize: 12, color: '#6b7280',
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <Lock size={12} />
          Edit retention windows under <strong style={{ marginLeft: 4 }}>Config → System Config → Document Retention Policy</strong>.
        </div>
      </section>
    </div>
  )
}
