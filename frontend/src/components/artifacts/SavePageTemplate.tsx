import { useEffect, useRef, useState } from 'react'
import { preparePageTemplate, savePageTemplate, type TemplateDraft, type TemplateSource } from '../../api/pageTemplates'
import { PageDialog, PagePreview } from './PagePrimitives'

export function SavePageTemplate({ source, onClose }: { source: TemplateSource; onClose: () => void }) {
  const [draft, setDraft] = useState<TemplateDraft | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [guidance, setGuidance] = useState('')
  const [labels, setLabels] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const pending = useRef(false)
  const { artifact_uuid, revision, preview_id } = source
  useEffect(() => {
    let live = true
    setError(''); setDraft(null)
    preparePageTemplate({ artifact_uuid, revision, preview_id }).then(d => {
      if (live) { setDraft(d); setLabels(Object.fromEntries(d.fields.map(field => [field.id, field.label]))) }
    }).catch(e => { if (live) setError(e instanceof Error ? e.message : 'Could not prepare this design.') })
    return () => { live = false }
  }, [artifact_uuid, revision, preview_id, attempt])
  const save = async () => {
    if (!draft || pending.current || !name.trim()) return
    pending.current = true; setBusy(true); setError('')
    try { await savePageTemplate({ draft_id: draft.draft_id, name: name.trim(), description, guidance, field_labels: labels }); setSaved(true) }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save the template.') }
    finally { pending.current = false; setBusy(false) }
  }
  return <PageDialog title="Save as template" onClose={onClose} wide busy={busy}>
    <div className="p-5 sm:p-6 space-y-4">
    {saved ? <><p role="status">Template saved privately. It contains the design and empty fields.</p><a className="page-button page-button-primary" href="/?mode=files&files=templates">Open Templates</a><button className="page-button" onClick={onClose}>Done</button></> : <>
      <p>Review the reusable design. Original values, names, links, images and source-specific text are cleared. Standard section labels stay; chart bars are reset until a new file supplies their values.</p>
      {error && <p role="alert" className="page-alert">{error} {!draft && <button onClick={() => setAttempt(n => n + 1)}>Retry design</button>}</p>}
      {!draft && !error && <p role="status">Removing source data from the design…</p>}
      {draft && <div className="grid gap-6 lg:grid-cols-2 items-start">
        <PagePreview title="Template design" html={draft.preview_html} compact />
        <div className="space-y-4">
        <label className="block my-3">Template name<input className="block w-full border rounded p-2" maxLength={200} value={name} onChange={e => setName(e.target.value)} placeholder="NIH Budget Dashboard" disabled={busy} /></label>
        <label className="block my-3">Description<textarea className="block w-full border rounded p-2" maxLength={1000} value={description} onChange={e => setDescription(e.target.value)} disabled={busy} /></label>
        <label className="block my-3">Reusable guidance<textarea className="block w-full border rounded p-2" maxLength={4000} value={guidance} onChange={e => setGuidance(e.target.value)} placeholder="General instructions for readers, without award-specific facts or values" disabled={busy} /></label>
        <details><summary className="cursor-pointer">Review field meanings ({draft.fields.length})</summary><p>Help the Assistant match the new file to each empty field. Describe what belongs here; do not enter example values.</p><div className="max-h-64 overflow-auto p-1">{draft.fields.map((field, index) => <label className="block my-2" key={field.id}>Field {index + 1}{field.bar ? ' · chart value' : ''}<input className="block w-full border rounded p-2" maxLength={160} value={labels[field.id] || ''} disabled={busy} onChange={e => setLabels(previous => ({ ...previous, [field.id]: e.target.value }))} /></label>)}</div></details>
        <p className="my-3">New templates are private. Share with a team from the Templates tab.</p>
        <div className="page-actions"><button className="page-button page-button-primary" disabled={busy || !name.trim()} onClick={() => void save()}>{busy ? 'Saving template…' : 'Save template'}</button><button className="page-button" disabled={busy} onClick={onClose}>Cancel</button></div>
        </div>
      </div>}
    </>}
    </div>
  </PageDialog>
}
