import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { FirstRunTour } from '../components/workspace/FirstRunTour'

const WorkspaceTourContext = createContext<(() => void) | null>(null)

export function WorkspaceTourProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const start = useCallback(() => setOpen(true), [])
  return <WorkspaceTourContext.Provider value={start}>
    {children}
    {open && <FirstRunTour onDismiss={() => setOpen(false)} />}
  </WorkspaceTourContext.Provider>
}

export function useWorkspaceTour() { return useContext(WorkspaceTourContext) }
