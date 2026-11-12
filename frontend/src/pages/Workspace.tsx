import { useAuth } from '../hooks/useAuth'
import { WorkspaceProvider } from '../contexts/WorkspaceContext'
import { WorkspaceLayout } from '../components/workspace/WorkspaceLayout'
import { WorkspaceTourProvider } from '../contexts/WorkspaceTourContext'

export function Workspace() {
  const { user } = useAuth()
  return (
    <WorkspaceProvider key={user?.id ?? 'signed-out'}>
      <WorkspaceTourProvider>
        <WorkspaceLayout key={user?.current_team ?? 'personal'} />
      </WorkspaceTourProvider>
    </WorkspaceProvider>
  )
}
