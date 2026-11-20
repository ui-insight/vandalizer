import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { PlanChecklist, planSummary } from './PlanChecklist'
import type { PlanTask } from '../../types/chat'

// Support ticket: "✓ All 4 steps completed" while four approval cards waited.
const task = (content: string, status: PlanTask['status']): PlanTask => ({ content, active_form: `${content}…`, status })

it('shows steps waiting for approval instead of calling the plan complete', () => {
  const tasks = [task('Create project', 'completed'), task('Add deadlines', 'awaiting_approval'), task('Extract details', 'completed'), task('Make page', 'awaiting_approval')]
  render(<PlanChecklist tasks={tasks} isStreaming={false} />)
  expect(screen.queryByText(/All 4 steps completed/)).not.toBeInTheDocument()
  expect(screen.getByText('Plan · 2 of 4 done · 2 waiting for your approval')).toBeInTheDocument()
  expect(screen.getAllByText('Waiting for your approval')).toHaveLength(2)
})

it('never shows "All completed" while the reply left cards waiting', () => {
  const done = [task('A', 'completed'), task('B', 'completed'), task('C', 'completed'), task('D', 'completed')]
  render(<PlanChecklist tasks={done} isStreaming={false} waitingApprovals={3} />)
  expect(screen.queryByText(/All 4 steps completed/)).not.toBeInTheDocument()
  expect(screen.getByText(/4 of 4 done · 3 waiting for your approval/)).toBeInTheDocument()
})

it('is complete only when every step is done and nothing waits', () => {
  render(<PlanChecklist tasks={[task('A', 'completed'), task('B', 'completed')]} isStreaming={false} />)
  expect(screen.getByText('All 2 steps completed')).toBeInTheDocument()
  expect(planSummary([task('A', 'completed'), task('B', 'pending')])).toBe('1 of 2 done')
})
