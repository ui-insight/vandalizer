import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PlanChecklist } from './PlanChecklist'
import type { PlanTask } from '../../types/chat'

const tasks: PlanTask[] = [
  { content: 'Run extraction', active_form: 'Running extraction', status: 'completed' },
  { content: 'Check compliance', active_form: 'Checking compliance', status: 'in_progress' },
  { content: 'Save summary', active_form: 'Saving summary', status: 'pending' },
]

describe('PlanChecklist', () => {
  it('renders nothing for an empty plan', () => {
    const { container } = render(<PlanChecklist tasks={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows progress count and per-status forms', () => {
    render(<PlanChecklist tasks={tasks} />)
    expect(screen.getByText('Plan · 1/3 done')).toBeInTheDocument()
    // Completed and pending show the imperative content…
    expect(screen.getByText('Run extraction')).toBeInTheDocument()
    expect(screen.getByText('Save summary')).toBeInTheDocument()
    // …the in-progress task shows its active form.
    expect(screen.getByText('Checking compliance')).toBeInTheDocument()
    expect(screen.queryByText('Check compliance')).not.toBeInTheDocument()
  })

  it('collapses to a done line when everything is completed', () => {
    render(
      <PlanChecklist
        tasks={tasks.map((t) => ({ ...t, status: 'completed' as const }))}
      />,
    )
    expect(screen.getByText('All 3 steps completed')).toBeInTheDocument()
    expect(screen.queryByText(/Plan ·/)).not.toBeInTheDocument()
  })
})
