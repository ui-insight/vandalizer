import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { WorkspaceBriefing } from './WorkspaceBriefing'

it('reopens the selected recent activity by ID instead of sending its title as a prompt', () => {
  const onOpenActivity = vi.fn()
  const onSendMessage = vi.fn()
  render(<WorkspaceBriefing recentActivity={[
    { id: 'first', type: 'conversation', title: 'Designing Workflow For Recurring Document Task', status: 'completed', relative_time: 'yesterday' },
    { id: 'second', type: 'conversation', title: 'Designing Workflow For Recurring Document Task', status: 'completed', relative_time: 'today' },
  ]} activeAlerts={[]} maturityStage="architect" unprocessedDocCount={0} onOpenActivity={onOpenActivity} onSendMessage={onSendMessage} />)
  fireEvent.click(screen.getByRole('button', { name: 'Open Designing Workflow For Recurring Document Task, today' }))
  expect(onOpenActivity).toHaveBeenCalledWith('second')
  expect(onSendMessage).not.toHaveBeenCalled()
})
