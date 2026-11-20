import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { JourneyMap } from './JourneyMap'
import { MODULES } from './modules'
import type { CertificationProgress } from '../../types/certification'

it('renders the selected course tier membership and order instead of legacy grouping', () => {
  const open = vi.fn()
  render(<JourneyMap modules={MODULES.slice(0, 2)} tiers={[{ name: 'Selected-course stage', theme: 'Review and supervise', narrative: 'The enrolled sequence', moduleIds: ['foundations', 'ai_literacy'], celebration: 'Stage complete' }]} progress={null} activeModule={null} isModuleLocked={() => false} onModuleClick={open} />)
  expect(screen.getByText('Selected-course stage')).toBeInTheDocument()
  expect(screen.queryByText('Practitioner')).not.toBeInTheDocument()
  const buttons = screen.getAllByRole('button')
  expect(buttons[0]).toHaveTextContent('Foundations')
  expect(buttons[1]).toHaveTextContent('AI Literacy')
  fireEvent.click(buttons[0])
  expect(open).toHaveBeenCalledWith('foundations')
})

it('keeps locked module identities readable and explains actual course prerequisites', () => {
  const modules = MODULES.filter(module => ['ai_literacy', 'foundations', 'process_mapping'].includes(module.id))
  render(<JourneyMap modules={modules} tiers={[{ name: 'Course stage', theme: 'Supervision', narrative: 'Course order', moduleIds: modules.map(module => module.id), celebration: 'Done' }]} progress={null} activeModule={null} isModuleLocked={id => id === 'process_mapping'} onModuleClick={vi.fn()} prerequisites={{ ai_literacy: [], foundations: [], process_mapping: ['ai_literacy'] }} />)
  const locked = screen.getByRole('button', { name: /Thinking in Workflows/ })
  expect(locked).toBeDisabled()
  expect(locked).toHaveTextContent('Locked. Complete AI Literacy to unlock.')
  expect(locked).not.toHaveTextContent('Complete Foundations')
  expect(screen.getByText('Thinking in Workflows')).toBeVisible()
})

it('names completion and star counts and omits empty stages rather than a zero-range progress bar', () => {
  const progress: CertificationProgress = { id: 'p', user_id: 'u', modules: { ai_literacy: { completed: true, stars: 2, completed_at: null, attempts: 1, xp_earned: 50 } }, total_xp: 50, level: 'novice', certified: false, certified_at: null, last_activity_date: null }
  render(<JourneyMap modules={[MODULES[0]]} tiers={[{ name: 'Completed stage', theme: 'Reading', narrative: 'Course order', moduleIds: ['ai_literacy'], celebration: 'Done' }, { name: 'Unavailable stage', theme: 'Absent', narrative: 'No modules', moduleIds: ['absent'], celebration: 'Done' }]} progress={progress} activeModule="ai_literacy" isModuleLocked={() => false} onModuleClick={vi.fn()} />)
  const bar = screen.getByRole('progressbar', { name: 'Completed stage modules completed' })
  expect(bar).toHaveAttribute('aria-valuetext', '1 of 1 modules complete')
  expect(screen.queryByText('Unavailable stage')).not.toBeInTheDocument()
  expect(screen.getByRole('img', { name: '2 of 3 stars' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /AI Literacy/ })).toHaveAttribute('aria-current', 'step')
  expect(screen.getByText('Completed')).toBeInTheDocument()
})
