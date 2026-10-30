import { useId } from 'react'

export function CourseEditorLink({ kind, artifactId, title, disabled = false }: {
  kind: 'extraction' | 'workflow'; artifactId: string; title: string; disabled?: boolean
}) {
  const description = useId()
  const query = new URLSearchParams({ mode: 'files', tab: 'library', [kind]: artifactId, courseEditor: '1' })
  const label = `Open selected ${kind} in a new tab`
  const classes = 'inline-flex min-h-11 max-w-full items-center rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-gray-900 [overflow-wrap:anywhere] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2'
  return <div className="min-w-0 space-y-2">
    {disabled ? <button type="button" className={`${classes} opacity-50`} disabled>{label}</button>
      : <a onClick={event => event.currentTarget.focus({ preventScroll: true })} onAuxClick={event => { if (event.button === 1) event.currentTarget.focus({ preventScroll: true }) }} className={classes} href={`/?${query}`} target="_blank" rel="noopener noreferrer" aria-describedby={description}>{label}</a>}
    <p id={description} className="text-sm text-gray-700 [overflow-wrap:anywhere]">Use the editor to inspect or change {title}. This course tab stays open. Return here after saving; refresh the choices before capturing a new revision. Editing the workspace does not replace evidence already saved for an assessment.</p>
  </div>
}
