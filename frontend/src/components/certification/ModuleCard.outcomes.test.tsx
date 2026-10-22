import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ModuleCard } from './ModuleCard'
import { MODULES } from './modules'
import type { ModuleDefinition } from '../../types/certification'

const legacy = MODULES.find(module => module.id === 'foundations')!
const props = { completed: false, stars: 0, locked: false, active: false, onClick: vi.fn() }
it('uses required-outcome language for competency modules while preserving earned legacy stars', () => {
  const draft = { ...legacy, decisionPrompts: [{ id: 'required' }] } as unknown as ModuleDefinition
  const view = render(<ModuleCard {...props} module={draft} />)
  expect(screen.getByText('Required outcomes')).toBeInTheDocument()
  expect(screen.queryByRole('img', { name: /stars/ })).not.toBeInTheDocument()
  view.rerender(<ModuleCard {...props} module={legacy} completed stars={2} />)
  expect(screen.getByText('Completed')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: '2 of 3 stars' })).toBeInTheDocument()
})

it('shows the full XP a module can award before it is completed (ticket)', () => {
  render(<ModuleCard {...props} module={legacy} maxXp={175} starBonusXp={25} />)
  const xp = screen.getByText('100–175 XP')
  expect(xp).toHaveAttribute('title', expect.stringContaining('plus 25 XP for each star'))
})
