import type { ButtonHTMLAttributes } from 'react'
import { Loader2 } from 'lucide-react'

export type ActionVariant = 'primary' | 'secondary' | 'quiet' | 'destructive'

/** Shared task action states; callers keep the action label visible while busy. */
export function ActionButton({ variant = 'secondary', loading = false, iconOnly = false, disabled, className = '', children, type = 'button', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ActionVariant
  loading?: boolean
  iconOnly?: boolean
}) {
  return <button {...props} type={type} disabled={disabled || loading} aria-busy={loading || props['aria-busy'] || undefined}
    data-variant={variant} data-icon-only={iconOnly || undefined} className={`workspace-action ${className}`}>
    {loading && <Loader2 size={16} aria-hidden="true" className="animate-spin" />}
    {children}
  </button>
}
