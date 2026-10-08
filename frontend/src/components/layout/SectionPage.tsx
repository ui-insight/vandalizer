import { Fragment, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

type Section<T extends string> = { key: T; label: string; icon: LucideIcon; group?: string }

/** Shared navigation for administration and examiner work. The same sections
 * become a labeled selector on small screens without replacing the task. */
export function SectionPage<T extends string>({ title, icon: Icon, label, sections, active, onSelect, children }: {
  title: string
  icon: LucideIcon
  label: string
  sections: Section<T>[]
  active: T
  onSelect: (section: T) => void
  children: ReactNode
}) {
  return (
    <div className="section-page">
      <nav aria-label={label} className="section-page__nav">
        <h1><Icon size={20} aria-hidden="true" />{title}</h1>
        <label className="section-page__selector">
          Section
          <select aria-label="Section" value={active} onChange={e => onSelect(e.target.value as T)}>
            {sections.map(section => <option key={section.key} value={section.key}>{section.label}</option>)}
          </select>
        </label>
        <div className="section-page__links">
          {sections.map(({ key, label: sectionLabel, icon: SectionIcon, group }, index) => (
            <Fragment key={key}>
            {group && group !== sections[index - 1]?.group && <p className="admin-nav-group">{group}</p>}
            <button type="button" key={key} aria-current={active === key ? 'page' : undefined} onClick={() => onSelect(key)}>
              <SectionIcon size={18} aria-hidden="true" />{sectionLabel}
            </button>
            </Fragment>
          ))}
        </div>
      </nav>
      <div className="section-page__content">{children}</div>
    </div>
  )
}
