import { WorkspaceProvider } from '../contexts/WorkspaceContext'
import { WorkspaceLayout } from '../components/workspace/WorkspaceLayout'
import { WorkspaceTourProvider } from '../contexts/WorkspaceTourContext'

export function Workspace() {
  return (
    <WorkspaceProvider>
      <WorkspaceTourProvider>
        <WorkspaceLayout />
      </WorkspaceTourProvider>
    </WorkspaceProvider>
  )
}
