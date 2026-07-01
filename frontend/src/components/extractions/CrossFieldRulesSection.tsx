/**
 * Cross-Field Rules editor — rendered inside the Validate tab.
 *
 * Users define rules that span multiple extracted fields (e.g. "Direct +
 * Indirect = Total Budget"). The optimizer treats violation rate as a 20%
 * weight in the trial score, so cross-field rules are an in-loop signal —
 * not a parallel report.
 *
 * Per-rule counters (eval/pass/fail/fp) come back from the backend; rules
 * the user marks as false positive often enough get auto-disabled there.
 * This component surfaces those states so users know which rules are pulling
 * their weight.
 */
import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import { AlertCircle, Check, Lightbulb, Plus, Trash2, X } from 'lucide-react'
import {
  getCrossFieldRules,
  suggestCrossFieldRules,
  updateCrossFieldRules,
  type CrossFieldRule,
  type CrossFieldRuleType,
} from '../../api/extractions'
import { useToast } from '../../contexts/ToastContext'

interface Props {
  searchSetUuid: string
  canManage: boolean
  fieldNames: string[]
}

const RULE_TYPE_LABELS: Record<CrossFieldRuleType, string> = {
  sum_equals: 'Sum equals',
  conditional_required: 'Conditional required',
  range_check: 'Range check',
  cross_reference: 'Cross reference',
  date_order: 'Date order',
  custom_expression: 'Custom expression',
}

export function CrossFieldRulesSection({ searchSetUuid, canManage, fieldNames }: Props) {
  const { toast } = useToast()
  const [rules, setRules] = useState<CrossFieldRule[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [suggestions, setSuggestions] = useState<CrossFieldRule[] | null>(null)
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [editing, setEditing] = useState<CrossFieldRule | null>(null)
  const [showAddMenu, setShowAddMenu] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getCrossFieldRules(searchSetUuid)
      setRules(res.rules)
    } catch (err) {
      console.error('Failed to load cross-field rules', err)
    } finally {
      setLoading(false)
    }
  }, [searchSetUuid])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const persistRules = async (next: CrossFieldRule[]) => {
    setSaving(true)
    try {
      const res = await updateCrossFieldRules(searchSetUuid, next)
      setRules(res.rules)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast(`Could not save rules: ${msg}`, 'error')
      throw err
    } finally {
      setSaving(false)
    }
  }

  const handleToggleEnabled = async (rule: CrossFieldRule) => {
    const next = rules.map(r =>
      r.id === rule.id ? { ...r, enabled: !(r.enabled ?? true), auto_disabled: false } : r,
    )
    await persistRules(next)
  }

  const handleDelete = async (rule: CrossFieldRule) => {
    const next = rules.filter(r => r.id !== rule.id)
    await persistRules(next)
  }

  const handleSaveEdit = async (rule: CrossFieldRule) => {
    const next = rule.id
      ? rules.map(r => (r.id === rule.id ? rule : r))
      : [...rules, rule]
    await persistRules(next)
    setEditing(null)
  }

  const handleSuggest = async () => {
    setLoadingSuggestions(true)
    try {
      const res = await suggestCrossFieldRules(searchSetUuid)
      setSuggestions(res.suggestions)
      if (res.suggestions.length === 0) {
        toast('No new rule suggestions for these fields.', 'info')
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast(`Could not get suggestions: ${msg}`, 'error')
    } finally {
      setLoadingSuggestions(false)
    }
  }

  const acceptSuggestion = async (suggestion: CrossFieldRule) => {
    const next = [...rules, suggestion]
    await persistRules(next)
    setSuggestions(prev => prev?.filter(s => s !== suggestion) ?? null)
  }

  const dismissSuggestion = (suggestion: CrossFieldRule) => {
    setSuggestions(prev => prev?.filter(s => s !== suggestion) ?? null)
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-medium text-gray-900">Cross-Field Rules</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Constraints that span fields — e.g. "Direct + Indirect = Total". The optimizer treats
            violation rate as part of the score, so good rules push it toward configs that satisfy them.
          </p>
        </div>
        {canManage && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSuggest}
              disabled={loadingSuggestions || loading}
              className="flex items-center gap-1 px-2.5 py-1.5 border border-gray-300 rounded text-xs hover:bg-gray-50 disabled:opacity-50"
              title="Propose rules from your field names"
            >
              <Lightbulb size={12} aria-hidden="true" />
              {loadingSuggestions ? 'Thinking…' : 'Suggest'}
            </button>
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowAddMenu(v => !v)}
                disabled={saving}
                aria-haspopup="menu"
                aria-expanded={showAddMenu}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-highlight text-highlight-text rounded text-xs font-bold hover:brightness-90 disabled:opacity-50"
              >
                <Plus size={12} aria-hidden="true" />
                Add rule
              </button>
              {showAddMenu && (
                <div role="menu" className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded shadow-lg z-10 min-w-[180px]">
                  {(Object.keys(RULE_TYPE_LABELS) as CrossFieldRuleType[]).map(t => (
                    <button
                      key={t}
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setShowAddMenu(false)
                        setEditing(blankRule(t))
                      }}
                      className="block w-full text-left px-3 py-2 text-xs hover:bg-gray-50"
                    >
                      {RULE_TYPE_LABELS[t]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {suggestions && suggestions.length > 0 && (
        <div className="mb-3 border border-amber-200 bg-amber-50 rounded p-3">
          <div className="text-xs font-medium text-amber-900 mb-2">Suggested rules</div>
          <ul className="space-y-1.5">
            {suggestions.map((s, i) => (
              <li key={i} className="flex items-center justify-between gap-2 text-xs">
                <span className="text-gray-800">{describeRule(s)}</span>
                {canManage && (
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => acceptSuggestion(s)}
                      className="px-2 py-0.5 bg-amber-600 text-white rounded text-xs hover:bg-amber-700"
                    >
                      Accept
                    </button>
                    <button
                      type="button"
                      onClick={() => dismissSuggestion(s)}
                      className="px-2 py-0.5 border border-gray-300 rounded text-xs hover:bg-gray-50"
                    >
                      Dismiss
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {loading ? (
        <div className="text-sm text-gray-500">Loading rules…</div>
      ) : rules.length === 0 ? (
        <div className="text-sm text-gray-500 py-4 text-center border border-dashed border-gray-200 rounded">
          No cross-field rules defined yet.
          {canManage && ' Use "Suggest" to get started, or "Add rule" to create one manually.'}
        </div>
      ) : (
        <ul className="space-y-1.5">
          {rules.map(rule => (
            <RuleRow
              key={rule.id}
              rule={rule}
              canManage={canManage}
              onEdit={() => setEditing(rule)}
              onToggleEnabled={() => handleToggleEnabled(rule)}
              onDelete={() => handleDelete(rule)}
            />
          ))}
        </ul>
      )}

      {editing && (
        <RuleEditModal
          rule={editing}
          fieldNames={fieldNames}
          onSave={handleSaveEdit}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// RuleRow
// ---------------------------------------------------------------------------

function RuleRow({
  rule,
  canManage,
  onEdit,
  onToggleEnabled,
  onDelete,
}: {
  rule: CrossFieldRule
  canManage: boolean
  onEdit: () => void
  onToggleEnabled: () => void
  onDelete: () => void
}) {
  const evals = rule.eval_count ?? 0
  const passes = rule.pass_count ?? 0
  const fails = rule.fail_count ?? 0
  const fps = rule.fp_count ?? 0
  const disabled = rule.enabled === false || rule.auto_disabled

  return (
    <li
      className={`flex items-start justify-between gap-3 py-2 px-3 rounded text-sm border ${
        disabled ? 'bg-gray-50 border-gray-200 text-gray-500' : 'bg-white border-gray-200'
      }`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-xs uppercase tracking-wide text-gray-500">
            {RULE_TYPE_LABELS[rule.type]}
          </span>
          {rule.auto_disabled && (
            <span
              className="inline-flex items-center gap-0.5 text-[10px] font-medium text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded"
              title={rule.auto_disabled_reason ?? undefined}
            >
              <AlertCircle size={10} aria-hidden="true" /> Auto-disabled
            </span>
          )}
          {rule.source === 'suggested' && (
            <span className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
              Suggested
            </span>
          )}
        </div>
        <div className="text-gray-800 mt-0.5 break-words">{describeRule(rule)}</div>
        {evals > 0 && (
          <div className="text-[11px] text-gray-500 mt-1">
            {passes} pass · {fails} fail · {fps > 0 ? `${fps} marked false alarm · ` : ''}
            {evals} total
          </div>
        )}
      </div>
      {canManage && (
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            role="switch"
            aria-checked={!disabled}
            onClick={onToggleEnabled}
            className="p-1 text-gray-500 hover:text-gray-700 text-xs"
            title={disabled ? 'Enable' : 'Disable'}
            aria-label={disabled ? 'Enable rule' : 'Disable rule'}
          >
            {disabled ? <Check size={14} aria-hidden="true" /> : <X size={14} aria-hidden="true" />}
          </button>
          <button
            type="button"
            onClick={onEdit}
            className="text-xs text-blue-600 hover:underline px-1"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="p-1 text-gray-500 hover:text-red-500"
            title="Delete"
            aria-label="Delete rule"
          >
            <Trash2 size={14} aria-hidden="true" />
          </button>
        </div>
      )}
    </li>
  )
}

// ---------------------------------------------------------------------------
// Edit modal
// ---------------------------------------------------------------------------

function RuleEditModal({
  rule,
  fieldNames,
  onSave,
  onCancel,
}: {
  rule: CrossFieldRule
  fieldNames: string[]
  onSave: (rule: CrossFieldRule) => Promise<void>
  onCancel: () => void
}) {
  const [draft, setDraft] = useState<CrossFieldRule>(rule)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const validationError = useMemo(() => {
    return validateDraft(draft)
  }, [draft])

  const handleSave = async () => {
    if (validationError) {
      setError(validationError)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(draft)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save rule')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h3 className="font-medium text-gray-900">
            {rule.id ? 'Edit rule' : 'New rule'} · {RULE_TYPE_LABELS[draft.type]}
          </h3>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="text-gray-500 hover:text-gray-600"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <RuleEditFields draft={draft} setDraft={setDraft} fieldNames={fieldNames} />
          {error && (
            <div role="alert" className="text-xs text-red-600">
              {error}
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200 bg-gray-50">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-white"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !!validationError}
            className="px-3 py-1.5 text-sm bg-highlight text-highlight-text rounded font-bold hover:brightness-90 disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

function RuleEditFields({
  draft,
  setDraft,
  fieldNames,
}: {
  draft: CrossFieldRule
  setDraft: (r: CrossFieldRule) => void
  fieldNames: string[]
}) {
  const update = (patch: Partial<CrossFieldRule>) => setDraft({ ...draft, ...patch })

  switch (draft.type) {
    case 'sum_equals':
      return (
        <>
          <MultiFieldPicker
            label="Source fields (summed)"
            value={draft.source_fields ?? []}
            options={fieldNames}
            onChange={v => update({ source_fields: v })}
          />
          <FieldPicker
            label="Target field (expected sum)"
            value={draft.target_field ?? ''}
            options={fieldNames}
            onChange={v => update({ target_field: v })}
          />
          <NumberInput
            label="Tolerance"
            value={draft.tolerance ?? 0.01}
            onChange={v => update({ tolerance: v ?? undefined })}
            step={0.01}
          />
        </>
      )
    case 'conditional_required':
      return (
        <>
          <FieldPicker
            label="Condition field"
            value={draft.condition_field ?? ''}
            options={fieldNames}
            onChange={v => update({ condition_field: v })}
          />
          <TextInput
            label="Condition value (case-insensitive)"
            value={draft.condition_value ?? ''}
            onChange={v => update({ condition_value: v })}
          />
          <FieldPicker
            label="Required field (when condition matches)"
            value={draft.required_field ?? ''}
            options={fieldNames}
            onChange={v => update({ required_field: v })}
          />
        </>
      )
    case 'range_check':
      return (
        <>
          <FieldPicker
            label="Field"
            value={draft.field ?? ''}
            options={fieldNames}
            onChange={v => update({ field: v })}
          />
          <div className="flex gap-2">
            <NumberInput
              label="Min"
              value={draft.min ?? null}
              onChange={v => update({ min: v })}
              nullable
            />
            <NumberInput
              label="Max"
              value={draft.max ?? null}
              onChange={v => update({ max: v })}
              nullable
            />
          </div>
        </>
      )
    case 'cross_reference':
      return (
        <>
          <FieldPicker
            label="Field A"
            value={draft.field_a ?? ''}
            options={fieldNames}
            onChange={v => update({ field_a: v })}
          />
          <FieldPicker
            label="Field B"
            value={draft.field_b ?? ''}
            options={fieldNames}
            onChange={v => update({ field_b: v })}
          />
          <Select
            label="Match type"
            value={draft.match_type ?? 'contains'}
            options={[
              { value: 'contains', label: 'Contains (either direction)' },
              { value: 'equals', label: 'Equals (after normalization)' },
            ]}
            onChange={v => update({ match_type: v as 'contains' | 'equals' })}
          />
        </>
      )
    case 'date_order':
      return (
        <>
          <FieldPicker
            label="Earlier date field"
            value={draft.field_a ?? ''}
            options={fieldNames}
            onChange={v => update({ field_a: v })}
          />
          <FieldPicker
            label="Later date field"
            value={draft.field_b ?? ''}
            options={fieldNames}
            onChange={v => update({ field_b: v })}
          />
        </>
      )
    case 'custom_expression':
      return (
        <>
          <p className="text-xs text-gray-600">
            Python expression — field names become variables with non-identifier characters replaced
            by underscores. Evaluated in a sandbox; numeric values are pre-converted.
          </p>
          <TextInput
            label="Expression"
            value={draft.expression ?? ''}
            onChange={v => update({ expression: v })}
            placeholder="Total_Budget >= 0 and Total_Budget < 10_000_000"
          />
        </>
      )
  }
}

// ---------------------------------------------------------------------------
// Small inputs
// ---------------------------------------------------------------------------

function FieldPicker({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-700 mb-1">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded"
      >
        <option value="">Select…</option>
        {options.map(opt => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  )
}

function MultiFieldPicker({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string[]
  options: string[]
  onChange: (v: string[]) => void
}) {
  const labelId = useId()
  const toggle = (opt: string) => {
    if (value.includes(opt)) onChange(value.filter(v => v !== opt))
    else onChange([...value, opt])
  }
  return (
    <div role="group" aria-labelledby={labelId}>
      <span id={labelId} className="block text-xs font-medium text-gray-700 mb-1">
        {label}
      </span>
      <div className="border border-gray-300 rounded p-2 max-h-32 overflow-y-auto space-y-1">
        {options.length === 0 ? (
          <div className="text-xs text-gray-500">No extraction fields available</div>
        ) : (
          options.map(opt => (
            <label key={opt} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={value.includes(opt)}
                onChange={() => toggle(opt)}
              />
              <span>{opt}</span>
            </label>
          ))
        )}
      </div>
    </div>
  )
}

function TextInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-700 mb-1">
        {label}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded font-mono"
      />
    </div>
  )
}

function NumberInput({
  label,
  value,
  onChange,
  step,
  nullable,
}: {
  label: string
  value: number | null
  onChange: (v: number | null) => void
  step?: number
  nullable?: boolean
}) {
  const id = useId()
  return (
    <div className="flex-1">
      <label htmlFor={id} className="block text-xs font-medium text-gray-700 mb-1">
        {label}
      </label>
      <input
        id={id}
        type="number"
        value={value ?? ''}
        onChange={e => {
          const s = e.target.value
          if (s === '' && nullable) onChange(null)
          else if (s === '') onChange(null)
          else onChange(Number(s))
        }}
        step={step}
        className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded"
      />
    </div>
  )
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (v: string) => void
}) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-700 mb-1">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded"
      >
        {options.map(o => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function blankRule(type: CrossFieldRuleType): CrossFieldRule {
  const base: CrossFieldRule = { type, enabled: true, source: 'user' }
  if (type === 'sum_equals') return { ...base, source_fields: [], target_field: '', tolerance: 0.01 }
  if (type === 'conditional_required') return { ...base, condition_field: '', condition_value: '', required_field: '' }
  if (type === 'range_check') return { ...base, field: '', min: null, max: null }
  if (type === 'cross_reference') return { ...base, field_a: '', field_b: '', match_type: 'contains' }
  if (type === 'date_order') return { ...base, field_a: '', field_b: '' }
  return { ...base, expression: '' }
}

function validateDraft(rule: CrossFieldRule): string | null {
  switch (rule.type) {
    case 'sum_equals':
      if (!rule.source_fields || rule.source_fields.length < 2) return 'Pick at least two source fields'
      if (!rule.target_field) return 'Pick a target field'
      return null
    case 'conditional_required':
      if (!rule.condition_field || !rule.required_field) return 'Pick both fields'
      return null
    case 'range_check':
      if (!rule.field) return 'Pick a field'
      if (rule.min == null && rule.max == null) return 'Set at least min or max'
      return null
    case 'cross_reference':
    case 'date_order':
      if (!rule.field_a || !rule.field_b) return 'Pick both fields'
      return null
    case 'custom_expression':
      if (!rule.expression?.trim()) return 'Enter an expression'
      return null
  }
}

export function describeRule(rule: CrossFieldRule): string {
  switch (rule.type) {
    case 'sum_equals':
      return `${(rule.source_fields ?? []).join(' + ') || '?'} = ${rule.target_field || '?'}`
    case 'conditional_required':
      return `When "${rule.condition_field}" = "${rule.condition_value}", "${rule.required_field}" must be present`
    case 'range_check':
      return `${rule.field} ∈ [${rule.min ?? '−∞'}, ${rule.max ?? '+∞'}]`
    case 'cross_reference':
      return `"${rule.field_a}" ${rule.match_type === 'equals' ? '==' : '⊇'} "${rule.field_b}"`
    case 'date_order':
      return `"${rule.field_a}" ≤ "${rule.field_b}"`
    case 'custom_expression':
      return rule.expression ?? '(empty)'
  }
}
