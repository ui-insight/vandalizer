const CHECKS = [
  { name: 'PI Name extracted', value: '"Dr. Sarah Chen"', status: 'pass' },
  { name: 'Total Budget is numeric', value: '"$485,000"', status: 'pass' },
  { name: 'Project period format', value: '"5 years"', status: 'review' },
] as const

const STATUS_STYLES = {
  pass: 'bg-green-100 text-green-700',
  fail: 'bg-red-100 text-red-700',
  review: 'bg-amber-100 text-amber-700',
} as const

const STATUS_LABELS = {
  pass: '✓ Pass',
  fail: '✗ Fail',
  review: '⚠ Review',
} as const

export function ValidationPlanExample() {
  return (
    <div className="rounded-lg overflow-hidden border border-gray-200 text-xs mt-2">
      <table className="w-full">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className="px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-gray-500">Check</th>
            <th className="px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-gray-500">Extracted Value</th>
            <th className="px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-gray-500">Result</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {CHECKS.map((check, i) => (
            <tr key={i}>
              <td className="px-3 py-2 text-gray-700">{check.name}</td>
              <td className="px-3 py-2 font-mono text-gray-600 text-[10px]">{check.value}</td>
              <td className="px-3 py-2">
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold ${STATUS_STYLES[check.status]}`}>
                  {STATUS_LABELS[check.status]}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
