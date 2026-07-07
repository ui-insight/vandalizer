/**
 * Cross-Field Violations panel — rendered alongside extraction validation
 * results. Shows pass/fail/unparseable counts at a glance and lists each
 * failure with a "Mark as false alarm" affordance that calls back into the
 * FP-tracking endpoint.
 *
 * Marking enough false positives auto-disables the rule on the backend so it
 * stops dragging the optimizer score down until a human fixes it.
 */
import { useState } from 'react'
import { AlertTriangle, CheckCircle, HelpCircle } from 'lucide-react'
import {
  markRuleFalsePositive,
  type CrossFieldRuleResult,
  type CrossFieldSummary,
} from '../../api/extractions'
import { describeRule } from './CrossFieldRulesSection'
import { useToast } from '../../contexts/ToastContext'

interface Props {
  searchSetUuid: string
  canManage: boolean
  summary: CrossFieldSummary | null | undefined
  results: CrossFieldRuleResult[] | null | undefined
}

export function CrossFieldViolationsPanel({ searchSetUuid, canManage, summary, results }: Props) {
  const { toast } = useToast()
  const [markedIds, setMarkedIds] = useState<Set<string>>(new Set())
  const [busyId, setBusyId] = useState<string | null>(null)

  if (!summary || summary.total === 0) return null

  const failures = (results ?? []).filter(r => r.status === 'fail')
  const unparseables = (results ?? []).filter(r => r.status === 'unparseable')

  const handleMark = async (result: CrossFieldRuleResult) => {
    const ruleId = result.rule_id || result.rule.id
    if (!ruleId) return
    setBusyId(ruleId)
    try {
      const res = await markRuleFalsePositive(searchSetUuid, ruleId)
      setMarkedIds(prev => new Set(prev).add(ruleId))
      if (res.rule.auto_disabled) {
        toast(
          `Rule auto-disabled after ${res.rule.fp_count} false alarms. Fix or re-enable it on the Rules card.`,
          'info',
        )
      } else {
        toast('Marked as false alarm. The rule will be auto-disabled if this happens repeatedly.', 'info')
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast(`Could not mark as false alarm: ${msg}`, 'error')
    } finally {
      setBusyId(null)
    }
  }

  const passRate = summary.pass_rate != null ? Math.round(summary.pass_rate * 100) : null

  return (
    <div
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        padding: '12px 16px',
        backgroundColor: '#fff',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>Cross-Field Rules</div>
        {passRate != null && (
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: passRate >= 90 ? '#059669' : passRate >= 70 ? '#d97706' : '#dc2626',
            }}
          >
            {passRate}% pass rate
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 12, fontSize: 12, marginBottom: failures.length > 0 || unparseables.length > 0 ? 12 : 0 }}>
        <Stat icon={<CheckCircle size={12} color="#059669" />} label="Pass" value={summary.pass} color="#059669" />
        <Stat icon={<AlertTriangle size={12} color="#dc2626" />} label="Fail" value={summary.fail} color="#dc2626" />
        {summary.unparseable > 0 && (
          <Stat
            icon={<HelpCircle size={12} color="#6b7280" />}
            label="Unparseable"
            value={summary.unparseable}
            color="#6b7280"
            tooltip="The validator couldn't evaluate these rules against the extracted data. They don't count for or against the score."
          />
        )}
      </div>

      {failures.length > 0 && (
        <div style={{ marginBottom: unparseables.length > 0 ? 12 : 0 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', marginBottom: 4, textTransform: 'uppercase' }}>
            Violations
          </div>
          <ul style={{ display: 'flex', flexDirection: 'column', gap: 4, listStyle: 'none', padding: 0, margin: 0 }}>
            {failures.map((r, i) => {
              const ruleId = r.rule_id || r.rule.id
              const marked = ruleId ? markedIds.has(ruleId) : false
              return (
                <li
                  key={`${ruleId}-${i}`}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: 8,
                    fontSize: 12,
                    padding: '6px 8px',
                    backgroundColor: '#fef2f2',
                    border: '1px solid #fecaca',
                    borderRadius: 6,
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: 'ui-monospace, monospace', color: '#991b1b', wordBreak: 'break-word' }}>
                      {describeRule(r.rule)}
                    </div>
                    <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{r.message}</div>
                    {(r.test_case_label || r.source_label) && (
                      <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                        on {r.test_case_label || r.source_label}
                      </div>
                    )}
                  </div>
                  {canManage && ruleId && (
                    <button
                      onClick={() => handleMark(r)}
                      disabled={busyId === ruleId || marked}
                      style={{
                        padding: '3px 8px',
                        fontSize: 11,
                        fontWeight: 600,
                        backgroundColor: marked ? '#e5e7eb' : '#fff',
                        color: marked ? '#6b7280' : '#dc2626',
                        border: `1px solid ${marked ? '#d1d5db' : '#fca5a5'}`,
                        borderRadius: 4,
                        cursor: marked || busyId === ruleId ? 'default' : 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                      title={marked ? 'Already marked' : 'Mark as false alarm: increments the rule\'s FP counter'}
                    >
                      {marked ? 'Marked' : busyId === ruleId ? '…' : 'False alarm'}
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {unparseables.length > 0 && (
        <details style={{ fontSize: 12, color: '#6b7280' }}>
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
            {unparseables.length} rule{unparseables.length === 1 ? '' : 's'} couldn't be evaluated
          </summary>
          <ul style={{ marginTop: 6, paddingLeft: 16, listStyle: 'disc' }}>
            {unparseables.map((r, i) => (
              <li key={i} style={{ marginBottom: 2 }}>
                <code>{describeRule(r.rule)}</code>: {r.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function Stat({
  icon,
  label,
  value,
  color,
  tooltip,
}: {
  icon: React.ReactNode
  label: string
  value: number
  color: string
  tooltip?: string
}) {
  return (
    <div
      style={{ display: 'flex', alignItems: 'center', gap: 4 }}
      title={tooltip}
    >
      {icon}
      <span style={{ color }}>{value}</span>
      <span style={{ color: '#6b7280' }}>{label}</span>
    </div>
  )
}
