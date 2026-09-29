import type { VerifiedCatalogItem } from '../../types/library'

export function CatalogUsage({ item, compact = false, dark = false }: { item: VerifiedCatalogItem; compact?: boolean; dark?: boolean }) {
  const usage = item.usage
  return (
    <section aria-label="Inputs and output" className={compact ? 'mb-3' : 'mb-5 rounded-xl border border-gray-200 bg-gray-50 p-4'} style={{ color: dark ? '#d1d5db' : '#374151', fontSize: compact ? 12 : 14, lineHeight: 1.5, overflowWrap: 'anywhere' }}>
      {!compact && <h3 className="mb-3 font-semibold text-gray-900">Using this item</h3>}
      <dl className="grid gap-2">
        <div><dt className="font-semibold">Input</dt><dd>{usage?.input || 'Input requirements are not described. Open the item to review its setup.'}</dd></div>
        <div><dt className="font-semibold">Output</dt><dd>{usage?.output || 'Expected output is not described.'}</dd></div>
      </dl>
      {!!usage?.output_names.length && <p className="mt-2"><span className="font-semibold">{compact ? 'Output steps: ' : 'Configured output steps: '}</span>{(compact ? usage.output_names.slice(0, 2) : usage.output_names).join(' · ')}{compact && usage.output_names.length > 2 ? ` · +${usage.output_names.length - 2} more` : ''}</p>}
      {(compact ? usage?.notes.slice(0, 1) : usage?.notes)?.map(note => <p className="mt-2" key={note}>{note}</p>)}
    </section>
  )
}
