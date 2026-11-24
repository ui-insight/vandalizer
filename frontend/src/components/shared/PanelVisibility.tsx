import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

const PanelVisibilityContext = createContext(true)

export function usePanelVisible() {
  return useContext(PanelVisibilityContext)
}

/** Keep visited workspace content alive, including drafts and in-flight work. */
export function RetainedPanel({ active, children, eager = false }: { active: boolean; children: ReactNode; eager?: boolean }) {
  const parentVisible = usePanelVisible()
  const [visited, setVisited] = useState(active || eager)
  useEffect(() => { if (active) setVisited(true) }, [active])
  const visible = parentVisible && active
  if (!active && !visited) return null
  return (
    <PanelVisibilityContext.Provider value={visible}>
      <div className={active ? 'h-full min-h-0' : 'hidden'} hidden={!active} inert={!visible}>
        {children}
      </div>
    </PanelVisibilityContext.Provider>
  )
}

/** Portals do not inherit the source panel's DOM visibility. */
export function PanelPortalVisibility({ children }: { children: ReactNode }) {
  const visible = usePanelVisible()
  return <div className="workspace-portal" hidden={!visible} inert={!visible} style={{ display: visible ? 'contents' : 'none' }}>{children}</div>
}
