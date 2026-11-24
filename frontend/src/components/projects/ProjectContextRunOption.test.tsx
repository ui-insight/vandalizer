import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ProjectContextRunOption } from './ProjectContextRunOption'
vi.mock('../../hooks/useProjects', () => ({ useProject: () => ({ project: { context: 'Write for reviewers' } }) }))
it('requires an explicit selection and locks it while the run is active', () => {
  const change = vi.fn()
  const view = render(<ProjectContextRunOption projectUuid="p1" checked={false} onChange={change} />)
  const checkbox = screen.getByRole('checkbox', { name: 'Use project context for this run' })
  expect(checkbox).not.toBeChecked()
  expect(change).not.toHaveBeenCalled()
  fireEvent.click(checkbox)
  expect(change).toHaveBeenCalledWith(true)
  view.rerender(<ProjectContextRunOption projectUuid="p1" checked onChange={change} disabled />)
  expect(checkbox).toBeChecked()
  expect(checkbox).toBeDisabled()
})
