import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { CelebrationOverlay } from './CelebrationOverlay'
import type { CompletionResult } from '../../types/certification'

vi.mock('../shared/PanelFocusTrap', () => ({ FocusTrap: ({ children }: { children: React.ReactNode }) => children }))
const result: CompletionResult = { module_id: 'bridge', stars: 2, xp_earned: 100, total_xp: 300, level: 'novice', level_up: false, certified: true, validation: { passed: true, stars: 2, checks: [] } }

it('describes the completed course rather than the current eleven-module catalog', () => {
  const dismiss = vi.fn()
  render(<CelebrationOverlay result={{ ...result, course_title: 'Supervision bridge', modules_total: 3 }} onDismiss={dismiss} />)
  expect(screen.getByRole('heading', { name: 'Supervision bridge' })).toBeInTheDocument()
  expect(screen.getByText('You have completed all 3 modules in this course.')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: '2 of 3 stars' })).toBeInTheDocument()
  fireEvent.keyDown(screen.getByRole('dialog', { name: 'Course complete' }), { key: 'Escape' })
  expect(dismiss).toHaveBeenCalledOnce()
})

it('does not invent a module count for a historical completion without course identity', () => {
  render(<CelebrationOverlay result={result} onDismiss={() => {}} />)
  expect(screen.getByText('You have completed the requirements for this course.')).toBeInTheDocument()
  expect(screen.queryByText(/all 11 modules/)).not.toBeInTheDocument()
})

it('does not turn preserved tier celebration copy into a credential before course completion', () => {
  render(<CelebrationOverlay result={{ ...result, certified: false }} onDismiss={() => {}}
    tierCelebration={{ tierName: 'Architect', message: "You've earned your certification!" }} />)
  expect(screen.getByRole('dialog', { name: 'Module complete' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Architect Complete!' })).toBeInTheDocument()
  expect(screen.getByText(/Continue with the remaining course requirements/)).toBeInTheDocument()
  expect(screen.queryByText("You've earned your certification!")).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'View Certificate' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
})

it('shows outcome completion without legacy enrichment stars and preserves the pinned level name', () => {
  render(<CelebrationOverlay result={{ ...result, level: 'validated', level_up: true, validation: { ...result.validation, assessment_kind: 'selected_outcome_validation' } }} onDismiss={() => {}} />)
  expect(screen.queryByRole('img', { name: /stars/ })).toBeNull()
  expect(screen.getByText("Level Up! You're now validated")).toBeInTheDocument()
})
