import { WorkspaceProvider } from '../contexts/WorkspaceContext'
import { WorkspaceLayout } from '../components/workspace/WorkspaceLayout'
import { FirstRunTour } from '../components/workspace/FirstRunTour'

export function Workspace() {
  return (
    <WorkspaceProvider>
      <WorkspaceLayout />
      <FirstRunTour />
    </WorkspaceProvider>
  )
}
