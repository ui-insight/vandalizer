import type { TemplateCheck } from '../../api/pageTemplates'

export function TemplateFillCheck({ check }: { check: TemplateCheck }) {
  return <div className="page-revision-note" role="status">
    <strong>{check.filled} values filled from {check.source_title} · {check.retained} kept from the template.</strong>
    <p>{check.missing ? `${check.missing} fields show “Not in this file”.` : 'Every template field has a source value.'} Values were matched to quotes in the selected file; review their placement before saving.</p>
  </div>
}
