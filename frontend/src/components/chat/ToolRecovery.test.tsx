import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToolCallDisplay, recoveredCallIds } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ openWorkflow: vi.fn() }) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../api/workflows', () => ({ getWorkflowStatus: vi.fn() }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => ({ refresh: vi.fn() }) }))

const call = (id: string, tool_name = 'create_workflow') => ({ tool_name, tool_call_id: id, args: { name: 'Subaward review' } })
const result = (id: string, content: unknown, tool_name = 'create_workflow') => ({ tool_name, tool_call_id: id, content, quality: null })
const FAILED = { error: 'KB not found' }
const PREVIEW = { needs_confirmation: true, preview: 'Create "Subaward review" with 3 steps.' }

describe('a failed step the Assistant fixed itself', () => {
  it('shows as retried, with no red failure or recovery button', () => {
    render(<ToolCallDisplay
      toolCalls={[call('a'), call('b')]}
      toolResults={[result('a', FAILED), result('b', PREVIEW)]}
      isStreaming={false}
      onConfirm={vi.fn()}
    />)
    expect(screen.getByText('Building workflow · Retried')).toBeInTheDocument()
    expect(screen.queryByText('Building workflow · Failed')).not.toBeInTheDocument()
    expect(screen.queryByText(/KB not found/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Review recovery options' })).not.toBeInTheDocument()
  })

  it('still shows a failure nothing fixed', () => {
    render(<ToolCallDisplay toolCalls={[call('a')]} toolResults={[result('a', FAILED)]} isStreaming={false} onConfirm={vi.fn()} />)
    expect(screen.getByRole('status')).toHaveTextContent('Building workflow · Failed')
    expect(screen.getByRole('button', { name: 'Review recovery options' })).toBeInTheDocument()
  })

  it('counts only a later success of the same tool', () => {
    const results = new Map([
      ['a', result('a', FAILED)],
      ['b', result('b', { title: 'Lesson 1' }, 'get_certification_progress')],
      ['c', result('c', FAILED)],
      ['d', result('d', PREVIEW)],
    ])
    expect([...recoveredCallIds(['a', 'b', 'c', 'd'], results)]).toEqual(['a', 'c'])
    expect([...recoveredCallIds(['d', 'a'], results)]).toEqual([])
  })
})
