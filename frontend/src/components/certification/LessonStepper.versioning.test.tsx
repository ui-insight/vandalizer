import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { LessonSection } from '../../types/certification'
import { LessonStepper } from './LessonStepper'

vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { user_id: 'learner' } }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('./LessonContent', () => ({ LessonContent: ({ section }: { section: LessonSection }) => <h4>{section.title}</h4> }))
const lessons: LessonSection[] = [
  { id: 'module.first', revision: 1, title: 'First lesson', content: 'First body', variant: 'concept' },
  { id: 'module.second', revision: 1, title: 'Second lesson', content: 'Second body', variant: 'concept' },
]
beforeEach(() => { localStorage.clear() })

it('preserves a lesson identity across reordering and isolates another enrollment', () => {
  localStorage.setItem('cert-lesson:learner:module', '1')
  const props = { lessons, moduleId: 'module', onGoToChallenge: vi.fn() }
  const view = render(<LessonStepper {...props} enrollmentId="course-a" />)
  expect(screen.getByRole('heading', { name: 'First lesson' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(screen.getByRole('heading', { name: 'Second lesson' })).toBeInTheDocument()
  view.rerender(<LessonStepper {...props} lessons={[...lessons].reverse()} enrollmentId="course-a" />)
  expect(screen.getByRole('heading', { name: 'Second lesson' })).toBeInTheDocument()
  view.rerender(<LessonStepper {...props} enrollmentId="course-b" />)
  expect(screen.getByRole('heading', { name: 'First lesson' })).toBeInTheDocument()
  expect(localStorage.getItem('cert-lesson:learner:course-a:module')).toBe('module.second')
  expect(localStorage.getItem('cert-lesson:learner:module')).toBe('1')
})

it('retains existing numeric resume behavior before the versioning rollout', () => {
  localStorage.setItem('cert-lesson:learner:module', '1')
  render(<LessonStepper lessons={lessons} moduleId="module" onGoToChallenge={vi.fn()} />)
  expect(screen.getByRole('heading', { name: 'Second lesson' })).toBeInTheDocument()
})


it('restores the server identity without writing, then saves deliberate navigation', async () => {
  localStorage.setItem('cert-lesson:learner:course-a:module', 'module.first')
  const save = vi.fn().mockResolvedValue(undefined)
  render(<LessonStepper lessons={lessons} moduleId="module" enrollmentId="course-a" savedLessonId="module.second" onSavePosition={save} onGoToChallenge={vi.fn()} />)
  expect(screen.getByRole('heading', { name: 'Second lesson' })).toBeInTheDocument()
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Place saved across devices'))
  expect(save).toHaveBeenCalledExactlyOnceWith('module.first')
})

it('keeps an unsaved place visible and refreshes without repeating its failed write', async () => {
  const save = vi.fn().mockRejectedValue(new Error('Conflict'))
  const refresh = vi.fn().mockResolvedValue(undefined)
  render(<LessonStepper lessons={lessons} moduleId="module" enrollmentId="course-a" onSavePosition={save} onReloadPosition={refresh} onGoToChallenge={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('could not be saved'))
  expect(screen.getByRole('heading', { name: 'Second lesson' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh progress' }))
  expect(refresh).toHaveBeenCalledTimes(1)
  expect(save).toHaveBeenCalledTimes(1)
})
