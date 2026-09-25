import type { VerifiedCatalogItem } from '../../types/library'

/**
 * The numbers that qualify a catalog score for someone deciding whether to
 * adopt: how many cases it was scored on, how consistent it was across runs,
 * and how many people already rely on it. Each renders only when the backend
 * actually measured it — an absent chip is "not measured", never "zero".
 */
type SignalItem = Pick<VerifiedCatalogItem, 'test_case_count' | 'consistency' | 'adoption_count' | 'quality_asserted' | 'starter'>

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
