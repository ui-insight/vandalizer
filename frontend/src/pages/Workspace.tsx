import { WorkspaceProvider } from '../contexts/WorkspaceContext'
import { WorkspaceLayout } from '../components/workspace/WorkspaceLayout'
import { CertificationPanel } from '../components/certification/CertificationPanel'
import { FirstRunTour } from '../components/workspace/FirstRunTour'

export function Workspace() {
  return (
    <WorkspaceProvider>
      <WorkspaceLayout />
      <CertificationPanel />
      <FirstRunTour />
    </WorkspaceProvider>
  )
}
