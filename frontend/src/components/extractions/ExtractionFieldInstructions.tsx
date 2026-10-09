import { useEffect, useId, useRef, useState } from 'react'

export function ExtractionFieldInstructions({ fieldName, instruction, onSave }: {
  fieldName: string; instruction: string; onSave: (value: string) => Promise<unknown> | void
}) {
  const id = useId()
  const [draft, setDraft] = useState(instruction)
  const [baseline, setBaseline] = useState(instruction)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const pending = useRef(false)
  const changedElsewhere = instruction !== baseline && draft !== baseline && instruction !== draft
  useEffect(() => {
    if (instruction !== baseline && (draft === baseline || draft === instruction)) {
      setDraft(instruction)
      setBaseline(instruction)
    }
  }, [instruction, baseline, draft])
  const value = draft.trim()
  return <form aria-label={`Extraction instructions for ${fieldName}`} className="min-w-0 space-y-2 border-t border-gray-300 pt-3 text-sm text-gray-900" onSubmit={async event => {
    event.preventDefault()
    if (pending.current || changedElsewhere || !value || value === baseline || saved === value) return
    pending.current = true
    setDraft(value)
    setSaving(true); setError(false); setSaved(null)
    try { await onSave(value); setSaved(value) }
    catch { setError(true) }
    finally { pending.current = false; setSaving(false) }
  }}>
    <label htmlFor={id} className="block font-semibold">Extraction instructions</label>
    <p id={`${id}-help`} className="text-gray-700">Describe what to extract for {fieldName}. Saving these instructions keeps the field name, optional setting and allowed values. Existing run history is unchanged.</p>
    <textarea id={id} aria-describedby={`${id}-help`} className="min-h-32 w-full rounded-lg border border-gray-400 bg-white p-2 text-gray-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" rows={5}
      required value={draft} disabled={saving} onChange={event => { setDraft(event.target.value); setSaved(null); setError(false) }} />
    {changedElsewhere && <p role="alert">Saved instructions changed while you were editing. Your draft is retained. Use the latest saved instructions before making another change.</p>}
    {error && <p role="alert">Saving was not confirmed. Your draft is retained; retry to save these same instructions.</p>}
    {saved === value && <p role="status">Instructions saved. Existing run history is unchanged.</p>}
    <div className="flex flex-wrap gap-2">
      <button type="submit" className="min-h-11 rounded-lg border border-gray-400 bg-white px-3 py-2 font-semibold disabled:opacity-50" disabled={saving || changedElsewhere || !value || value === baseline || saved === value}>{saving ? 'Saving instructions…' : 'Save instructions'}</button>
      <button type="button" className="min-h-11 rounded-lg border border-gray-300 bg-white px-3 py-2 disabled:opacity-50" disabled={saving || draft === instruction} onClick={() => { setDraft(instruction); setBaseline(instruction); setSaved(null); setError(false) }}>{changedElsewhere ? 'Use latest saved instructions' : 'Discard instruction changes'}</button>
    </div>
  </form>
}
