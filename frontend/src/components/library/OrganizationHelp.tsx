import { useId, useState } from 'react'
import { createPortal } from 'react-dom'
import { FocusTrap } from 'focus-trap-react'
import { CircleHelp, Folder, Pin, Star, X } from 'lucide-react'

const ORGANIZATION_OPTIONS = [
  { icon: Star, title: 'Favorites', description: 'Mark useful tools so you can find them in the Favorites view.' },
  { icon: Pin, title: 'Pins', description: 'Keep tools at the top when sorting by recent use. Favorites follow pinned tools.' },
  { icon: Folder, title: 'Folders', description: 'Group tools in this library by topic or purpose.' },
]

export function OrganizationHelp() {
  const [open, setOpen] = useState(false)
  const titleId = useId()

  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
        className="mx-3 my-3 flex items-start gap-2 rounded-md border-0 bg-transparent p-1 text-left text-xs leading-5 text-gray-600 hover:text-gray-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-600"
      >
        <CircleHelp size={14} className="mt-0.5 shrink-0" />
        <span>How organization works</span>
      </button>
      {open && createPortal(
        <div
          className="fixed inset-0 flex items-center justify-center bg-black/40 p-4"
          style={{ zIndex: 2000 }}
          onClick={event => { if (event.target === event.currentTarget) setOpen(false) }}
          onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); setOpen(false) } }}
        >
          <FocusTrap focusTrapOptions={{ escapeDeactivates: false, allowOutsideClick: true, tabbableOptions: { displayCheck: 'none' } }}>
            <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="max-h-[calc(100dvh-2rem)] w-full max-w-sm overflow-y-auto rounded-xl border border-gray-200 bg-white p-5 text-gray-900 shadow-xl">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 id={titleId} className="text-base font-semibold">Organize your library</h2>
                  <p className="mt-1 text-sm leading-5 text-gray-600">Three ways to keep your tools within reach.</p>
                </div>
                <button type="button" aria-label="Close organization help" onClick={() => setOpen(false)} className="-mr-1 -mt-1 shrink-0 rounded-md p-2 text-gray-600 hover:bg-gray-100 focus-visible:outline-2 focus-visible:outline-gray-600">
                  <X size={18} />
                </button>
              </div>
              <dl className="mt-5 space-y-4">
                {ORGANIZATION_OPTIONS.map(({ icon: Icon, title, description }) => (
                  <div key={title} className="relative pl-11">
                    <dt className="text-sm font-semibold"><span className="absolute left-0 top-0 flex h-8 w-8 items-center justify-center rounded-lg bg-gray-100 text-gray-600"><Icon size={16} /></span>{title}</dt>
                    <dd className="mt-1 text-sm leading-5 text-gray-600">{description}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-5 border-t border-gray-200 pt-4 text-xs leading-5 text-gray-600">Project pins are managed inside each project. Organizing your library doesn’t add tools to a project.</p>
            </div>
          </FocusTrap>
        </div>,
        document.body,
      )}
    </>
  )
}
