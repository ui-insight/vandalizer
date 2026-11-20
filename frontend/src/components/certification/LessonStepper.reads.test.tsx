import { expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { LessonSection } from '../../types/certification'
import { LessonStepper } from './LessonStepper'
import { markLessonRead } from '../../api/certification'

vi.mock('../../api/certification', () => ({ markLessonRead: vi.fn(() => Promise.resolve({})) }))
vi.mock('../../api/certificationJourney', () => ({ observeCertificationJourney: vi.fn() }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { user_id: 'learner' } }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('./LessonContent', () => ({ LessonContent: ({ section }: { section: LessonSection }) => <h4>{section.title}</h4> }))

const lessons: LessonSection[] = [
  { id: 'module.first', revision: 1, title: 'First lesson', content: 'First body', variant: 'concept' },
  { id: 'module.second', revision: 1, title: 'Second lesson', content: 'Second body', variant: 'concept' },
]

it('records each lesson the panel shows, so chat and the panel agree on what is read', () => {
  render(<LessonStepper lessons={lessons} moduleId="module" enrollmentId={'a'.repeat(32)} onGoToChallenge={vi.fn()} />)
  expect(markLessonRead).toHaveBeenCalledWith('module', 'module.first', 'a'.repeat(32))
  fireEvent.click(screen.getByRole('button', { name: /next/i }))
  expect(markLessonRead).toHaveBeenCalledWith('module', 'module.second', 'a'.repeat(32))
})
