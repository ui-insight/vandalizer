import { WorkspaceProvider } from '../contexts/WorkspaceContext'
import { WorkspaceLayout } from '../components/workspace/WorkspaceLayout'
import { CertificationPanel } from '../components/certification/CertificationPanel'

export function Workspace() {
  return (
    <WorkspaceProvider>
      <WorkspaceLayout />
      <CertificationPanel />
    </WorkspaceProvider>
  )
}
