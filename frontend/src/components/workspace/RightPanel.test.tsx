import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RightPanel } from './RightPanel'

// Mutable workspace state the mocked context reads from.
const h = vi.hoisted(() => ({
  tab: 'assistant' as 'assistant' | 'library',
  workflowId: null as string | null,
  extractionId: null as string | null,
  automationId: null as string | null,
}))

vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    activeRightTab: h.tab,
    setActiveRightTab: (t: 'assistant' | 'library') => { h.tab = t },
    openWorkflowId: h.workflowId,
    openExtractionId: h.extractionId,
    openAutomationId: h.automationId,
  }),
}))

// Light stand-ins so we can track whether the Assistant subtree is torn down.
vi.mock('./AssistantTab', () => ({ AssistantTab: () => <div data-testid="assistant-marker" /> }))
vi.mock('./LibraryTab', () => ({ LibraryTab: () => <div data-testid="library-marker" /> }))
vi.mock('./WorkflowEditorPanel', () => ({ WorkflowEditorPanel: () => <div data-testid="workflow-editor-marker" /> }))
vi.mock('./ExtractionEditorPanel', () => ({ ExtractionEditorPanel: () => <div data-testid="extraction-editor-marker" /> }))
vi.mock('./AutomationEditorPanel', () => ({ AutomationEditorPanel: () => <div data-testid="automation-editor-marker" /> }))

describe('RightPanel tab switching', () => {
  beforeEach(() => {
    h.tab = 'assistant'
    h.workflowId = null
    h.extractionId = null
    h.automationId = null
  })

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

  it('keeps the Assistant mounted (hidden) while an editor is open', () => {
    h.workflowId = 'wf-1'
    render(<RightPanel />)
    expect(screen.getByTestId('workflow-editor-marker')).toBeInTheDocument()
    const assistant = screen.getByTestId('assistant-marker')
    expect(assistant).toBeInTheDocument()
    expect(assistant.closest('div.hidden')).not.toBeNull()
    // Editors take over the whole panel — no tab bar alongside them.
    expect(screen.queryByRole('button', { name: /assistant/i })).not.toBeInTheDocument()
  })

  it('does not remount the Assistant across an editor open→close round trip', () => {
    const { rerender } = render(<RightPanel />)
    const original = screen.getByTestId('assistant-marker')

    // Mid-conversation, the user opens a workflow editor (e.g. to build a
    // certification module's workflow)...
    h.workflowId = 'wf-1'
    rerender(<RightPanel />)
    expect(screen.getByTestId('assistant-marker')).toBe(original)

    // ...then an extraction editor, then closes back to chat.
    h.workflowId = null
    h.extractionId = 'ex-1'
    rerender(<RightPanel />)
    expect(screen.getByTestId('assistant-marker')).toBe(original)

    h.extractionId = null
    rerender(<RightPanel />)
    // Same node the whole way → the conversation was never torn down.
    expect(screen.getByTestId('assistant-marker')).toBe(original)
    expect(screen.getByTestId('assistant-marker').closest('div.hidden')).toBeNull()
  })
})
