import { useState } from 'react'
import { useCourseDraft, draftStrings } from '../../hooks/useCourseDraft'
import { CourseDraftNotice } from './CourseDraftNotice'
import type { BudgetCalculation, BudgetCalculationRecord, BudgetList, BudgetOperand, BudgetRequest, CalculationId } from '../../types/budgetWorkflow'
import { EvidenceText, connectedButton as button, connectedControl as control } from './ConnectedWorkflowEvidence'

export const calculationLabels: Record<CalculationId, string> = { equipment_subtotal: 'Equipment subtotal', listed_direct_subtotal: 'Seven listed direct categories', listed_summary_total: 'Listed summary including estimated indirect cost' }
export function BudgetCalculationEvidence({ calculation }: { calculation: BudgetCalculation }) {
  return <section aria-label="Saved budget calculations" className="min-w-0 space-y-3 text-sm text-gray-900">
    <h5 className="text-base font-semibold">{calculation.checks.all_arithmetic_supported ? 'Source additions supported' : 'Calculation corrections or clarification needed'}</h5>
    <p>{calculation.checks.notice}</p>
    {calculation.checks.checks.map(check => <div key={check.id} className="min-w-0 space-y-2 rounded-lg border border-gray-200 p-3">
      <h6 className="font-semibold">{calculationLabels[check.id]}</h6><p>{check.state === 'supported' ? 'Addition and named source inputs agree' : check.state === 'unresolved' ? 'Unresolved input or result' : 'Review the source inputs and addition'}</p>
      <p className="break-words">{check.expression}</p>
      <dl className="grid grid-cols-1 gap-1 sm:grid-cols-2"><div><dt>Your saved result (USD)</dt><dd className="font-semibold">{check.recorded_value ?? 'Unresolved'}</dd></div><div><dt>Recomputed from your inputs (USD)</dt><dd className="font-semibold">{check.computed_value ?? 'Unresolved'}</dd></div></dl>
      <p>Source agreement: {check.source_matches ? 'Named values and citations agree' : 'Check the values, pages and quotations'}</p><p>{check.interpretation}</p>
      <details><summary className="min-h-11 cursor-pointer py-2">Inspect saved calculation inputs</summary><EvidenceText label={`${calculationLabels[check.id]} saved inputs`} value={calculation.request.records.find(record => record.id === check.id)} /></details>
    </div>)}
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Read original saved budget</summary><EvidenceText label="Saved budget source text" value={calculation.document.text} /></details>
  </section>
}

export function BudgetCalculationForm({ listing, original, locked, onSave }: { listing: BudgetList; original: BudgetCalculation | null; locked: boolean; onSave: (request: BudgetRequest) => void }) {
  const fields = [...new Map(listing.calculation_fields.flatMap(calculation => calculation.inputs).map(input => [input.id, input])).values()]
  const [selection, setSelection] = useCourseDraft(['budget-calculation-source', listing.enrollment_id, listing.manifest_sha256, listing.case.case_sha256, original?.uuid || null],
    { documentId: original?.document.document_id || (listing.assigned_sources.length === 1 ? listing.assigned_sources[0].document_id : '') }, draftStrings(['documentId'], 100))
  const documentId = original?.document.document_id || selection.documentId
  const source = original?.document || listing.assigned_sources.find(item => item.document_id === documentId)
  type Draft = { operands: Record<string, BudgetOperand>; results: Partial<Record<CalculationId, string>>; method: BudgetCalculationRecord['method']; interpretation: string }
  const [draft, setDraft, status] = useCourseDraft<Draft>(['budget-calculations', listing.enrollment_id, listing.manifest_sha256, listing.case.case_sha256,
    listing.case.source_sha256, documentId, original?.uuid || null, original?.calculation_snapshot_sha256 || null], {
    operands: Object.fromEntries(fields.map(field => {
      const saved = original?.request.records.flatMap(record => record.inputs).find(input => input.id === field.id)
      return [field.id, saved || { id: field.id, value: null, unit: 'USD', source_page: field.source_page, source_quote: '', status: 'supported', explanation: '' }]
    })),
    results: Object.fromEntries(original?.request.records.map(record => [record.id, record.result || '']) || []),
    method: original?.request.records[0].method || 'explicit_learner_arithmetic', interpretation: original?.request.records[0].interpretation || '',
  }, (value): value is Draft => {
    if (!value || typeof value !== 'object') return false
    const saved = value as Draft
    return !!saved.operands && typeof saved.operands === 'object' && Object.keys(saved.operands).length === fields.length
      && fields.every(field => {
        const operand = saved.operands[field.id]
        return !!operand && operand.id === field.id && operand.unit === 'USD'
          && (operand.value === null || typeof operand.value === 'string' && operand.value.length <= 100)
          && Number.isFinite(operand.source_page) && ['supported', 'unresolved'].includes(operand.status)
          && typeof operand.source_quote === 'string' && operand.source_quote.length <= 2000
          && typeof operand.explanation === 'string' && operand.explanation.length <= 2000
      }) && !!saved.results && typeof saved.results === 'object' && !Array.isArray(saved.results)
      && Object.entries(saved.results).every(([id, result]) => listing.calculation_fields.some(field => field.id === id) && typeof result === 'string' && result.length <= 100)
      && ['explicit_learner_arithmetic', 'recorded_deterministic_arithmetic'].includes(saved.method)
      && typeof saved.interpretation === 'string' && saved.interpretation.length <= 4000
  })
  const { operands, results, method, interpretation } = draft
  const [error, setError] = useState('')
  function edit(id: string, change: Partial<BudgetOperand>) { setDraft(current => ({ ...current, operands: { ...current.operands, [id]: { ...current.operands[id], ...change } } })) }
  return <form aria-label="Record budget calculations" className="min-w-0 space-y-4 rounded-lg border border-gray-300 p-3" onSubmit={event => {
    event.preventDefault(); setError('')
    const records = listing.calculation_fields.map(field => ({ id: field.id, operation: field.operation, unit: field.unit,
      inputs: field.inputs.map(input => operands[input.id]), method, result: results[field.id] || null, interpretation }))
    if (!documentId || !interpretation.trim() || fields.some(field => !operands[field.id].explanation.trim())) { setError('Choose the assigned source and explain each source check and the limits of your calculations.'); return }
    onSave({ action: 'calculation', body: { request_id: crypto.randomUUID().replaceAll('-', ''), case_sha256: listing.case.case_sha256,
      document_id: documentId, records, previous_snapshot_id: original?.uuid || null, consent: 'save_source_bound_budget_calculations' } })
  }}>
    <h5 className="text-base font-semibold text-gray-900">{original ? 'Revise your saved calculations' : '1. Record and check the source amounts'}</h5>
    <p className="text-sm text-gray-700">Use USD amounts with two decimal places and no commas. Source rows shared by several sums are entered once. Unknown values or totals may stay unresolved. Saving checks addition; it does not assess interpretation or award credit.</p>
    {original ? <p className="text-sm text-gray-700">Your original answers stay preserved. This creates a linked revision.</p> : <label className="block text-sm">Assigned source<select required className={control} disabled={locked} value={documentId} onChange={event => setSelection({ documentId: event.target.value })}><option value="">Choose your assigned budget</option>{listing.assigned_sources.map(doc => <option key={doc.document_id} value={doc.document_id} disabled={doc.processing}>{doc.title}{doc.processing ? ' · still processing' : ''}</option>)}</select></label>}
    {source && <details><summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold">Read budget while recording amounts</summary><EvidenceText label="Budget for calculation entry" value={source.text} /></details>}
    {!source && <p className="text-sm text-gray-700">Provision the assigned budget in your certification lab, then refresh the saved-work list.</p>}
    <label className="block text-sm">Arithmetic method<select className={control} value={method} disabled={locked} onChange={event => setDraft(current => ({ ...current, method: event.target.value as typeof method }))}><option value="explicit_learner_arithmetic">Explicit learner arithmetic</option><option value="recorded_deterministic_arithmetic">Recorded deterministic arithmetic</option></select></label>
    {fields.map(field => { const value = operands[field.id]; return <fieldset key={field.id} className="min-w-0 space-y-2 rounded-lg border border-gray-200 p-3 text-sm">
      <legend className="max-w-full px-1 font-semibold text-gray-900">{field.label}</legend>
      <label className="block">{field.label} amount (USD)<input className={control} inputMode="decimal" pattern="(0|[1-9][0-9]{0,8})\.[0-9]{2}" placeholder="0.00" required={value.status === 'supported'} disabled={locked} value={value.value || ''} onChange={event => edit(field.id, { value: event.target.value || null })} /></label>
      <label className="flex min-h-11 items-center gap-2"><input type="checkbox" className="size-6 shrink-0" disabled={locked} checked={value.status === 'unresolved'} onChange={event => edit(field.id, { status: event.target.checked ? 'unresolved' : 'supported' })} />This input remains unresolved</label>
      <label className="block">Source page for {field.label}<input type="number" className={control} min={1} step={1} required disabled={locked} value={value.source_page} onChange={event => edit(field.id, { source_page: Number(event.target.value) })} /></label>
      <label className="block">Source quotation for {field.label}<textarea className={control} rows={3} required={value.status === 'supported'} maxLength={2000} disabled={locked} value={value.source_quote} onChange={event => edit(field.id, { source_quote: event.target.value })} /></label>
      <label className="block">Explain your check of {field.label}<textarea className={control} rows={2} required minLength={10} maxLength={2000} disabled={locked} value={value.explanation} onChange={event => edit(field.id, { explanation: event.target.value })} /></label>
    </fieldset> })}
    {listing.calculation_fields.map(field => <label className="block text-sm" key={field.id}>{calculationLabels[field.id]} result (USD; leave blank if unresolved)<input className={control} inputMode="decimal" pattern="(0|[1-9][0-9]{0,8})\.[0-9]{2}" placeholder="0.00" disabled={locked} value={results[field.id] || ''} onChange={event => setDraft(current => ({ ...current, results: { ...current.results, [field.id]: event.target.value } }))} /></label>)}
    <label className="block text-sm">Explain what these additions establish and what remains unresolved<textarea className={`${control} min-h-32`} required minLength={20} maxLength={4000} disabled={locked} value={interpretation} onChange={event => setDraft(current => ({ ...current, interpretation: event.target.value }))} /></label>
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    <CourseDraftNotice status={status} /><button className={button} disabled={locked || !source}>Save source-bound calculations</button>
  </form>
}
