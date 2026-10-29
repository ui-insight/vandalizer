import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ToolStatusLine } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

it('uses a plain Create project button and sends approval once', () => {
  const onConfirm = vi.fn()
  render(<ToolStatusLine
    call={{ tool_name: 'create_project', tool_call_id: 'project', args: { title: 'Award' } }}
    result={{ tool_name: 'create_project', tool_call_id: 'project', quality: null,
      content: { needs_confirmation: true, preview: 'Create project "Award".' } }}
    onConfirm={onConfirm}
  />)
  expect(screen.queryByRole('button', { name: 'Approve create project' })).not.toBeInTheDocument()
  expect(onConfirm).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Create project' }))
  expect(onConfirm).toHaveBeenCalledExactlyOnceWith('Yes, go ahead')
  expect(screen.queryByRole('button', { name: 'Create project' })).not.toBeInTheDocument()
})
