import type { ReactNode } from 'react'

/** Shared heading/action order; controls below it wrap with the pane width. */
export function WorkspaceSectionHeader({ title, help, actions, description, children, dark = false }: {
  title: string
  help?: ReactNode
  actions?: ReactNode
  description?: ReactNode
  children?: ReactNode
  dark?: boolean
}) {
  return <header className="workspace-section-header" data-dark={dark}>
    <div className="workspace-section-heading">
      <div className="workspace-section-title"><h2>{title}</h2>{help}</div>
      {actions && <div className="workspace-section-actions">{actions}</div>}
    </div>
    {description && <p className="workspace-section-description">{description}</p>}
    {children && <div className="workspace-section-controls">{children}</div>}
  </header>
}
