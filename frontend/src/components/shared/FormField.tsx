import type { LabelHTMLAttributes, ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'

/** Visible requirement markers accompany the control's native/ARIA requirement. */
export function FieldLabel({ required, optional, children, className = '', ...props }: LabelHTMLAttributes<HTMLLabelElement> & { required?: boolean; optional?: boolean }) {
  return <div className={`workspace-field-label ${className}`}>
    <label {...props}>{children}</label>{(required || optional) && <span className="workspace-field-requirement" aria-hidden="true">{required ? 'Required' : 'Optional'}</span>}
  </div>
}

export function FieldMessage({ id, error = false, children }: { id: string; error?: boolean; children: ReactNode }) {
  return <p id={id} className="workspace-field-message" data-error={error || undefined} role={error ? 'alert' : undefined}>
    {error && <AlertCircle size={16} aria-hidden="true" />}<span>{children}</span>
  </p>
}
