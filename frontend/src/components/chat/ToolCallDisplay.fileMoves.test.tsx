import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ToolStatusLine } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

it('shows the move destination and files before requesting approval', () => {
  const onConfirm = vi.fn()
  render(<ToolStatusLine
    call={{ tool_name: 'move_documents_to_project', tool_call_id: 'move', args: { project_uuid: 'project', document_uuids: ['award'] } }}
    result={{ tool_name: 'move_documents_to_project', tool_call_id: 'move', quality: null, content: { needs_confirmation: true, preview: 'Move Subaward.pdf into Subaward project. It leaves its current folder.' } }}
    onConfirm={onConfirm}
  />)
  expect(screen.getByRole('region', { name: 'Review proposed action' })).toHaveTextContent('Move Subaward.pdf into Subaward project. It leaves its current folder.')
  expect(onConfirm).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Move files' }))
  expect(onConfirm).toHaveBeenCalledWith('Yes, go ahead')
  expect(screen.getByRole('status')).toHaveTextContent('Approval requested')
})

it('does not label a partial move as completed', () => {
  render(<ToolStatusLine result={{ tool_name: 'move_documents_to_project', tool_call_id: 'move', quality: null, content: {
    status: 'partial', moved_documents: [{ uuid: 'award' }], failed_documents: [{ uuid: 'budget' }], message: 'Moved 1 of 2 files. Budget.pdf could not be moved.',
  } }} />)
  expect(screen.getByRole('status')).not.toHaveTextContent('Completed')
  expect(screen.getByText('Moved 1 of 2 files. Budget.pdf could not be moved.')).toBeInTheDocument()
})
