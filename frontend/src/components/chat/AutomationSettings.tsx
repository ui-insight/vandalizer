import { Fragment } from 'react'

/** Server-resolved settings shown before approval and retained on the receipt. */
export function AutomationSettings({ settings }: { settings: unknown }) {
  if (!Array.isArray(settings)) return null
  const rows = settings.filter((row): row is { label: string; value: string } =>
    !!row && typeof row === 'object' && typeof row.label === 'string' && typeof row.value === 'string')
  if (!rows.length) return null
  return <dl aria-label="Automation settings" className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
    {rows.map(row => <Fragment key={row.label}>
      <dt className="font-medium">{row.label}</dt><dd className="break-words">{row.value}</dd>
    </Fragment>)}
  </dl>
}
