import type { VerifiedCatalogItem } from '../../types/library'

/**
 * The numbers that qualify a catalog score for someone deciding whether to
 * adopt: how many cases it was scored on, how consistent it was across runs,
 * and how many people already rely on it. Each renders only when the backend
 * actually measured it — an absent chip is "not measured", never "zero".
 */
type SignalItem = Pick<VerifiedCatalogItem, 'test_case_count' | 'consistency' | 'adoption_count' | 'quality_asserted' | 'starter' | 'last_validated_at'>

export function catalogSignals(item: SignalItem): string[] {
  const out: string[] = []
  if (item.starter) out.push('Starter example')
  if (!item.quality_asserted && item.test_case_count && item.test_case_count > 0) {
    out.push(`on ${item.test_case_count} case${item.test_case_count === 1 ? '' : 's'}`)
  }
  if (!item.quality_asserted && item.consistency != null) {
    out.push(`same answer ${Math.round(item.consistency * 100)}% of the time`)
  }
  if (item.adoption_count && item.adoption_count > 0) {
    out.push(item.adoption_count === 1 ? '1 person uses it' : `${item.adoption_count} people use it`)
  }
  const date = validationDate(item.last_validated_at)
  if (date) out.push(`Validated ${date}`)
  return out
}

export function CatalogSignals({ item, className, style }: {
  item: SignalItem
  className?: string
  style?: React.CSSProperties
}) {
  const signals = catalogSignals(item)
  if (signals.length === 0) return null
  return (
    <>
      {signals.map(s => (
        <span key={s} className={className} style={style}>{s}</span>
      ))}
    </>
  )
}

/** Dates are calendar dates to avoid implying live monitoring or relative freshness. */
export function validationDate(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' })
}

export function CatalogEvidence({ item }: { item: VerifiedCatalogItem }) {
  const measured = !item.quality_asserted && item.quality_score != null
  const date = validationDate(item.last_validated_at)
  return (
    <section aria-label="Validation evidence" className="mb-5 rounded-xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
      <h3 className="mb-3 font-semibold text-gray-900">Validation evidence</h3>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div><dt className="font-medium">Rating origin</dt><dd>{item.quality_asserted ? 'Author-provided rating; not measured here' : measured ? 'Recorded validation score' : 'No measured score available'}</dd></div>
        <div><dt className="font-medium">Last validation</dt><dd>{date || 'Not recorded'}</dd></div>
        <div><dt className="font-medium">Sample size</dt><dd>{measured && item.test_case_count != null ? `${item.test_case_count} test cases` : 'Not recorded for a measured score'}</dd></div>
        <div><dt className="font-medium">Recorded runs</dt><dd>{item.validation_run_count ?? 'Not recorded'}</dd></div>
      </dl>
      <p className="mt-3">{item.regression_pending_review ? 'A regression is awaiting review; the previous rating should not be treated as current.' : measured ? 'This score describes the recorded test cases. It does not establish performance on your documents or questions.' : 'Missing measurements are not a low score. Validate this item before relying on its rating.'}</p>
    </section>
  )
}
