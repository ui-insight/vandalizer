import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RightPanel } from './RightPanel'

// Mutable workspace state the mocked context reads from.
const h = vi.hoisted(() => ({ tab: 'assistant' as 'assistant' | 'library' }))

vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    activeRightTab: h.tab,
    setActiveRightTab: (t: 'assistant' | 'library') => { h.tab = t },
    openWorkflowId: null,
    openExtractionId: null,
    openAutomationId: null,
  }),
}))

// Light stand-ins so we can track whether the Assistant subtree is torn down.
vi.mock('./AssistantTab', () => ({ AssistantTab: () => <div data-testid="assistant-marker" /> }))
vi.mock('./LibraryTab', () => ({ LibraryTab: () => <div data-testid="library-marker" /> }))
vi.mock('./WorkflowEditorPanel', () => ({ WorkflowEditorPanel: () => <div /> }))
vi.mock('./ExtractionEditorPanel', () => ({ ExtractionEditorPanel: () => <div /> }))
vi.mock('./AutomationEditorPanel', () => ({ AutomationEditorPanel: () => <div /> }))

describe('RightPanel tab switching', () => {
  beforeEach(() => { h.tab = 'assistant' })

  it('shows only the Assistant on the assistant tab', () => {
    h.tab = 'assistant'
    render(<RightPanel />)
    expect(screen.getByTestId('assistant-marker')).toBeInTheDocument()
    expect(screen.queryByTestId('library-marker')).not.toBeInTheDocument()
  })

  it('keeps the Assistant mounted (hidden) when the Library tab is active', () => {
    h.tab = 'library'
    render(<RightPanel />)
    // The bug was the Assistant being unmounted here, discarding its
    // conversation state. It must stay in the DOM, just hidden.
    const assistant = screen.getByTestId('assistant-marker')
    expect(assistant).toBeInTheDocument()
    expect(assistant.closest('div.hidden')).not.toBeNull()
    expect(screen.getByTestId('library-marker')).toBeInTheDocument()
  })

  it('does not remount the Assistant across an assistant→library→assistant round trip', () => {
    h.tab = 'assistant'
    const { rerender } = render(<RightPanel />)
    const original = screen.getByTestId('assistant-marker')

    h.tab = 'library'
    rerender(<RightPanel />)
    // Same node, still present — proves it was hidden, not torn down.
    expect(screen.getByTestId('assistant-marker')).toBe(original)

    h.tab = 'assistant'
    rerender(<RightPanel />)
    // Still the very same node → never unmounted, so useChat state survives.
    expect(screen.getByTestId('assistant-marker')).toBe(original)
  })
})
