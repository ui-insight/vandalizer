import { ShieldCheck, Star, Target, X } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { ValidationResult } from '../../types/certification'

export function ValidationResults({ result, onDismiss, recheckState, onRecheck, recheckDisabled = false }: {
  result: ValidationResult; onDismiss: () => void; recheckState?: 'checking' | 'unavailable'
  onRecheck?: () => void; recheckDisabled?: boolean
}) {
  const allChecksPassed = result.checks.length > 0 && result.checks.every(check => check.passed)
  return (
    <section role={result.passed ? 'status' : 'alert'} aria-live={result.passed ? 'polite' : 'assertive'}
      className={cn('border-2 p-4 cert-slide-in', result.passed ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50')}
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
      {recheckState && <p role="status" className="mb-3 text-sm font-medium text-gray-900">{recheckState === 'checking'
        ? 'Previous check results — rechecking this module…'
        : 'Recheck unavailable. These are previous check results; your earlier feedback is preserved.'}</p>}
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {result.passed ? <ShieldCheck size={18} className="shrink-0 text-green-700" aria-hidden="true" /> : <Target size={18} className="shrink-0 text-amber-700" aria-hidden="true" />}
          <span className={cn('text-sm font-semibold', result.passed ? 'text-green-800' : 'text-amber-800')}>
            {result.passed ? (allChecksPassed ? 'All checks passed' : 'Module requirements met') : 'Some objectives remaining'}
          </span>
          {result.passed && <span role="img" className="flex shrink-0 gap-0.5" aria-label={`${result.stars} of 3 stars`}>
            {Array.from({ length: 3 }).map((_, index) => <Star key={index} size={14} aria-hidden="true" className={index < result.stars ? 'fill-amber-700 text-amber-700' : 'text-gray-600'} />)}
          </span>}
        </div>
        <button type="button" onClick={onDismiss} aria-label="Dismiss results" style={{ minHeight: 44, minWidth: 44 }} className="flex shrink-0 items-center justify-center rounded p-2 text-gray-600 hover:bg-white"><X size={16} aria-hidden="true" /></button>
      </div>
      {result.passed && result.checks.some(check => !check.passed) && <p className="mb-3 text-sm text-gray-700">{result.checks.filter(check => !check.passed).every(check => check.role === 'advisory') ? 'Required checks passed. Advisory suggestions do not block completion.' : 'Your course allows completion with this result. Review the checks marked not met.'}</p>}
      <ul className="space-y-3">
        {result.checks.map((check, index) => <li key={index} className="flex items-start gap-2 text-sm">
          <span aria-hidden="true" className={cn('shrink-0', check.passed ? 'text-green-700' : 'text-amber-800')}>{check.passed ? '✓' : '○'}</span>
          <div className="min-w-0 break-words">
            <p className={cn('font-medium', check.passed ? 'text-green-800' : 'text-amber-900')}>{check.name} <span className="font-normal">— {check.role === 'advisory' ? `Advisory: ${check.passed ? 'Met' : 'Suggestion'}` : `${check.role === 'required' ? 'Required: ' : ''}${check.passed ? 'Met' : 'Not met'}`}</span></p>
            {check.detail && <p className="mt-0.5 text-gray-700">{check.detail}</p>}
          </div>
        </li>)}
      </ul>
      {onRecheck && <button type="button" disabled={recheckDisabled} onClick={onRecheck} className="mt-4 min-h-11 rounded-lg border border-gray-500 bg-white px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50">Recheck this module</button>}
    </section>
  )
}
