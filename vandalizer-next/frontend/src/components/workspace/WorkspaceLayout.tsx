import { useEffect } from 'react'
import { useSearch, useNavigate } from '@tanstack/react-router'
import { Header } from '../layout/Header'
import { ActivityRail } from './ActivityRail'
import { PanelResizer } from './PanelResizer'
import { LeftPanel } from './LeftPanel'
import { RightPanel } from './RightPanel'
import { useWorkspace } from '../../contexts/WorkspaceContext'

export function WorkspaceLayout() {
  const { railDocked, panelSplit, openWorkflow, openExtraction } = useWorkspace()
  const search = useSearch({ from: '/' })
  const navigate = useNavigate()

  // Handle deep-link query params (e.g. /?openWorkflow=123)
  useEffect(() => {
    if (search.openWorkflow) {
      openWorkflow(search.openWorkflow)
      navigate({ to: '/', search: {}, replace: true })
    } else if (search.openExtraction) {
      openExtraction(search.openExtraction)
      navigate({ to: '/', search: {}, replace: true })
    }
  }, [search, navigate, openWorkflow, openExtraction])
  const railWidth = railDocked ? 64 : 220

  // Layout matches Flask: [LeftPanel] [Resizer] [RightPanel] [ActivityRail(right)]
  // Left panel width: panelSplit% of space remaining after rail
  // Right panel: margin-right accommodates the fixed-width rail
  return (
    <div className="flex h-screen flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <div
          className="flex flex-1 overflow-hidden"
          style={{
            marginRight: `${railWidth}px`,
            transition: 'margin-right 0.3s ease',
          }}
        >
          <div
            className="overflow-hidden"
            style={{
              width: `${panelSplit}%`,
              transition: 'width 0.3s ease',
            }}
          >
            <LeftPanel />
          </div>
          <PanelResizer />
          <div
            className="overflow-hidden flex-1"
          >
            <RightPanel />
          </div>
        </div>
        <div
          className="shrink-0"
          style={{
            position: 'fixed',
            top: 69,
            right: 0,
            bottom: 0,
            width: railDocked ? 64 : 'var(--rail-w)',
            zIndex: 650,
            transition: 'width 0.3s ease',
          }}
        >
          <ActivityRail />
        </div>
      </div>
    </div>
  )
}
