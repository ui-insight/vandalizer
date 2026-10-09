import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { CertificationProgress, ValidationResult, CompletionResult, CourseDefinition } from '../../types/certification'
import type { AssessmentDestination } from '../../contexts/CertificationPanelContext'
import { MODULES } from './modules'
import { ApiError } from '../../api/client'

const validate = vi.fn()
const complete = vi.fn()
const provision = vi.fn()
const submitAssessment = vi.fn()
const toast = vi.fn()
const panelState: { progress: CertificationProgress | null; userId: string | null; isOpen: boolean; course?: CourseDefinition; assessmentDestination?: AssessmentDestination } = { progress: null, userId: 'alice', isOpen: true }
const consumeAssessmentDestination = vi.fn()

vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanelOptional: () => null,
  useCertificationPanel: () => ({
    isOpen: panelState.isOpen,
    mode: 'fullscreen',
    closePanel: vi.fn(),
    setMode: vi.fn(),
    progress: panelState.progress,
    course: panelState.course,
    assessmentDestination: panelState.assessmentDestination,
    consumeAssessmentDestination,
    loading: false,
    refresh: vi.fn().mockResolvedValue(undefined),
    validate,
    complete,
    provision,
    getExercise: vi.fn().mockResolvedValue(null),
    submitAssessment,
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ user: panelState.userId ? { user_id: panelState.userId } : null }),
}))

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast }),
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

// The detail view is exercised elsewhere; here it only needs a Check Progress.
vi.mock('./ModuleDetail', () => ({
  ModuleDetail: ({ onValidate, onComplete, onProvision, onSubmitAssessment, openChallengeRequest }: { onValidate: () => void; onComplete: () => void; onProvision: () => void; onSubmitAssessment: (answers: Record<string, string>) => void; openChallengeRequest?: number }) => (
    <><button onClick={onValidate}>Check Progress</button><button onClick={onComplete}>Complete Module</button><button onClick={onProvision}>Set Up Lab</button><button onClick={() => onSubmitAssessment({ experience: 'Original' })}>Submit Reflection</button><output data-testid="assessment-request">{openChallengeRequest}</output></>
  ),
}))

vi.mock('./CelebrationOverlay', () => ({
  CelebrationOverlay: () => <div>Module Complete!</div>,
}))

vi.mock('../shared/PanelFocusTrap', () => ({ FocusTrap: ({ children }: { children: React.ReactNode }) => children }))

import { CertificationPanel } from './CertificationPanel'

function progressWith(stars: number, completed = true): CertificationProgress {
  return {
    id: 'p1',
    user_id: 'alice',
    modules: {
      foundations: { completed, stars, completed_at: null, attempts: 1, xp_earned: 150 },
    },
    total_xp: 150,
    level: 'novice',
    certified: false,
    certified_at: null,
    last_activity_date: null,
    unlocked: true,
  }
}

const threeStars: ValidationResult = {
  passed: true,
  stars: 3,
  checks: [{ name: 'Has extraction workflow', passed: true, detail: '' }],
}

beforeEach(() => {
  vi.clearAllMocks()
  panelState.userId = 'alice'
  panelState.isOpen = true
  panelState.course = undefined
  panelState.assessmentDestination = undefined
  localStorage.setItem('cert-active-module:alice', 'foundations')
  validate.mockResolvedValue(threeStars)
  complete.mockResolvedValue({ module_id: 'foundations', stars: 3, xp_earned: 25 } as CompletionResult)
})

it.each([
  ['Check Progress', validate], ['Complete Module', complete],
  ['Set Up Lab', provision], ['Submit Reflection', submitAssessment],
] as const)('handles rapid %s activation once and permits an explicit retry after failure', async (label, operation) => {
  panelState.progress = progressWith(0, false)
  let fail!: (error: Error) => void
  operation.mockImplementation(() => new Promise((_, reject) => { fail = reject }))
  render(<CertificationPanel />)
  const button = screen.getByRole('button', { name: label })
  fireEvent.click(button)
  fireEvent.click(button)
  const count = operation.mock.calls.length
  await act(async () => { fail(new Error('Synthetic response unavailable')) })
  expect(count).toBe(1)
  expect(toast).toHaveBeenCalledTimes(1)
  fireEvent.click(button)
  expect(operation).toHaveBeenCalledTimes(2)
  await act(async () => { fail(new Error('Synthetic response unavailable')) })
  expect(toast).toHaveBeenCalledTimes(2)
})

it('keeps a progress check locked through its star-upgrade save', async () => {
  panelState.progress = progressWith(1)
  let finish!: (result: CompletionResult) => void
  complete.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  render(<CertificationPanel />)
  fireEvent.click(screen.getByText('Check Progress'))
  await waitFor(() => expect(complete).toHaveBeenCalledTimes(1))
  fireEvent.click(screen.getByText('Check Progress'))
  expect(validate).toHaveBeenCalledTimes(1)
  await act(async () => { finish({ module_id: 'foundations', stars: 3, xp_earned: 25 } as CompletionResult) })
  expect(complete).toHaveBeenCalledTimes(1)
  expect(toast).toHaveBeenCalledTimes(1)
})

it('opens the explicitly requested assessment ahead of a saved lesson, then clears it for normal navigation', () => {
  const identity = { enrollment_id: 'selected', course_version: 'preview', manifest_sha256: 'hash' }
  panelState.progress = { ...progressWith(0, false), ...identity, learning_position: { module_id: 'ai_literacy', lesson_id: 'first', revision: 1, content_sha256: 'hash', saved_at: '2026-10-07' } }
  panelState.course = { ...identity, modules: MODULES, prerequisites: Object.fromEntries(MODULES.map(module => [module.id, []])) } as unknown as CourseDefinition
  panelState.isOpen = false
  const view = render(<CertificationPanel />)
  panelState.assessmentDestination = { nonce: 5, moduleId: 'foundations', enrollmentId: 'selected', manifestSha256: 'hash' }
  panelState.isOpen = true
  view.rerender(<CertificationPanel />)
  expect(screen.getByText('Module 1: Foundations')).toBeInTheDocument()
  expect(screen.getByTestId('assessment-request')).toHaveTextContent('5')
  expect(consumeAssessmentDestination).toHaveBeenCalledWith(5)
  panelState.assessmentDestination = undefined
  view.rerender(<CertificationPanel />)
  fireEvent.click(screen.getByRole('button', { name: 'Curriculum' }))
  fireEvent.click(screen.getByRole('button', { name: 'Continue: AI Literacy' }))
  expect(screen.getByTestId('assessment-request')).toBeEmptyDOMElement()
  expect(validate).not.toHaveBeenCalled()
  expect(complete).not.toHaveBeenCalled()
})

it('does not call an uncertain completion a failed assessment or silently regrade it', async () => {
  panelState.progress = progressWith(0, false)
  complete.mockRejectedValueOnce(new ApiError(503, 'Response unavailable'))
  render(<CertificationPanel />)
  fireEvent.click(await screen.findByRole('button', { name: 'Complete Module' }))
  await waitFor(() => expect(toast).toHaveBeenCalledWith('Completion could not be confirmed. Resume the original request to finish or retrieve its saved result.', 'error'))
  expect(validate).not.toHaveBeenCalled()
})

it('restores the saved module when the authenticated identity arrives after mounting', async () => {
  panelState.progress = progressWith(1)
  panelState.userId = null
  const view = render(<CertificationPanel />)
  expect(screen.queryByRole('button', { name: 'Check Progress' })).not.toBeInTheDocument()
  panelState.userId = 'alice'
  view.rerender(<CertificationPanel />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Check Progress' })).toBeInTheDocument())
})

it('keeps the server module when identity loads after versioned progress', async () => {
  panelState.progress = { ...progressWith(1), enrollment_id: 'server-course', learning_position: { module_id: 'foundations', lesson_id: 'server-lesson', revision: 1, content_sha256: 'hash', saved_at: '2026-10-05' } }
  panelState.userId = null
  localStorage.setItem('cert-active-module:alice', 'governance')
  const view = render(<CertificationPanel />)
  expect(screen.getByText('Module 1: Foundations')).toBeInTheDocument()
  panelState.userId = 'alice'
  view.rerender(<CertificationPanel />)
  expect(screen.getByText('Module 1: Foundations')).toBeInTheDocument()
})

it('resumes a new chat cursor on reopening without replacing an already open module', () => {
  const position = { module_id: 'foundations', lesson_id: 'first', revision: 1, content_sha256: 'hash', saved_at: '2026-10-07' }
  panelState.progress = { ...progressWith(1), enrollment_id: 'server-course', position_revision: 1, learning_position: position }
  const view = render(<CertificationPanel />)
  expect(screen.getByText('Module 1: Foundations')).toBeInTheDocument()
  panelState.progress = { ...panelState.progress, position_revision: 2, learning_position: { ...position, module_id: 'ai_literacy' } }
  view.rerender(<CertificationPanel />)
  expect(screen.getByText('Module 1: Foundations')).toBeInTheDocument()
  panelState.isOpen = false
  view.rerender(<CertificationPanel />)
  panelState.progress = { ...panelState.progress, position_revision: 3 }
  view.rerender(<CertificationPanel />)
  panelState.isOpen = true
  view.rerender(<CertificationPanel />)
  expect(screen.getByText('Module 0: AI Literacy')).toBeInTheDocument()
})

it('keeps an unsaved module selection when closing and reopening without a new cursor', () => {
  panelState.progress = { ...progressWith(1), enrollment_id: 'server-course', position_revision: 1, learning_position: { module_id: 'foundations', lesson_id: 'first', revision: 1, content_sha256: 'hash', saved_at: '2026-10-07' } }
  panelState.course = { enrollment_id: 'server-course', modules: MODULES, prerequisites: Object.fromEntries(MODULES.map(module => [module.id, []])) } as unknown as CourseDefinition
  const view = render(<CertificationPanel />)
  fireEvent.click(screen.getByRole('button', { name: 'Curriculum' }))
  fireEvent.click(screen.getByRole('button', { name: 'Continue: AI Literacy' }))
  panelState.isOpen = false
  view.rerender(<CertificationPanel />)
  panelState.isOpen = true
  view.rerender(<CertificationPanel />)
  expect(screen.getByText('Module 0: AI Literacy')).toBeInTheDocument()
})

describe('CertificationPanel Check Progress on a completed module', () => {
  it('saves a better star result without replaying the completion celebration', async () => {
    panelState.progress = progressWith(2)
    render(<CertificationPanel />)
    fireEvent.click(screen.getByText('Check Progress'))
    await waitFor(() => expect(complete).toHaveBeenCalledWith('foundations'))
    expect(toast).toHaveBeenCalledWith('Saved: 3 stars (+25 XP)', 'success')
    expect(screen.queryByText('Module Complete!')).toBeNull()
  })

  it('does not re-save when the result is no better than the stored stars', async () => {
    panelState.progress = progressWith(3)
    render(<CertificationPanel />)
    fireEvent.click(screen.getByText('Check Progress'))
    await waitFor(() => expect(validate).toHaveBeenCalled())
    await screen.findByText('All checks passed')
    expect(complete).not.toHaveBeenCalled()
  })

  it('leaves an uncompleted module for Complete Module to finish', async () => {
    panelState.progress = progressWith(0, false)
    render(<CertificationPanel />)
    fireEvent.click(screen.getByText('Check Progress'))
    await screen.findByText('All checks passed')
    expect(complete).not.toHaveBeenCalled()
  })
})

it('does not call an interrupted execution a failed assessment or regrade it', async () => {
  panelState.progress = progressWith(0, false)
  const interrupted = new ApiError(400, 'Assessment was interrupted; submit a new request to try again')
  interrupted.code = 'certification_execution_failed'
  complete.mockRejectedValueOnce(interrupted)
  render(<CertificationPanel />)
  fireEvent.click(await screen.findByRole('button', { name: 'Complete Module' }))
  await waitFor(() => expect(toast).toHaveBeenCalledWith(interrupted.message, 'error'))
  expect(validate).not.toHaveBeenCalled()
})

it.each([125, 250, 1600, 1800])('uses earned XP for the next threshold even with a stale stored level (%i XP)', xp => {
  localStorage.removeItem('cert-active-module:alice')
  panelState.progress = { ...progressWith(1), total_xp: xp, level: 'novice' }
  render(<CertificationPanel />)
  const expected = xp === 125 ? '125 XP to Builder' : xp === 250 ? '150 XP to Designer' : 'Highest XP threshold reached'
  expect(screen.getByText(expected)).toBeInTheDocument()
  expect(screen.queryByText(/-\d+ XP to/)).not.toBeInTheDocument()
})

it('does not let bonus XP or unrelated saved modules inflate course completion', () => {
  localStorage.removeItem('cert-active-module:alice')
  panelState.progress = { ...progressWith(3), total_xp: 2675 }
  panelState.progress.modules.unrelated = { completed: true, stars: 3, xp_earned: 500, completed_at: null, attempts: 1 }
  render(<CertificationPanel />)
  fireEvent.click(screen.getByText('Course progress and credential'))
  expect(screen.getByRole('progressbar', { name: 'Course modules completed' })).toHaveAttribute('aria-valuenow', '9')
  expect(screen.getByText(/XP toward this course/)).toHaveTextContent('2675 XP toward this course')
})

it.each([3, 11])('uses the selected %i-module manifest for progress even with high XP and unrelated credit', count => {
  const modules = MODULES.slice(0, count)
  const identity = { enrollment_id: `course-${count}`, course_version: `version-${count}`, manifest_sha256: 'a'.repeat(64) }
  panelState.progress = { ...progressWith(3), ...identity, total_xp: 9999 }
  panelState.progress.modules.unrelated = { completed: true, stars: 3, xp_earned: 500, completed_at: null, attempts: 1 }
  panelState.course = { ...identity, versioned: true, course_title: `Original ${count}-module course`, modules_total: count,
    maximum_xp: modules.reduce((sum, module) => sum + module.xp + 75, 0), modules,
    prerequisites: Object.fromEntries(modules.map(module => [module.id, []])), levels: [{ name: 'Novice', xp: 0 }], tiers: [],
  }
  render(<CertificationPanel />)
  fireEvent.click(screen.getByText('Course progress and credential'))
  expect(screen.getByRole('progressbar', { name: 'Course modules completed' })).toHaveAttribute('aria-valuenow', String(Math.round(100 / count)))
  expect(screen.getByText(/XP toward this course/)).toHaveTextContent('9999 XP toward this course')
  expect(screen.queryByText('Certification complete')).toBeNull()
})

it('preserves the last checks while rechecking and after an unavailable response', async () => {
  panelState.progress = progressWith(0, false)
  const previous: ValidationResult = { passed: false, stars: 0, checks: [
    { name: 'Assigned source', passed: true, detail: 'The assigned source was retained.' },
    { name: 'Value review', passed: false, detail: 'Compare the amount with the original source.' },
  ] }
  validate.mockResolvedValueOnce(previous)
  render(<CertificationPanel />)
  fireEvent.click(screen.getByRole('button', { name: 'Check Progress' }))
  await screen.findByText('Compare the amount with the original source.')
  let fail!: (error: Error) => void
  validate.mockImplementationOnce(() => new Promise((_resolve, reject) => { fail = reject }))
  fireEvent.click(screen.getByRole('button', { name: 'Check Progress' }))
  expect(screen.getByText('Compare the amount with the original source.')).toBeInTheDocument()
  expect(screen.getByText(/Previous check results/)).toBeInTheDocument()
  await act(async () => fail(new Error('Synthetic read failure')))
  expect(screen.getByText('The assigned source was retained.')).toBeInTheDocument()
  expect(screen.getByText(/Recheck unavailable/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Recheck this module' }))
  await waitFor(() => expect(validate).toHaveBeenCalledTimes(3))
})

it.each(['learner', 'enrollment', 'manifest', 'module'])('discards delayed check feedback and automatic star upgrade after %s changes', async field => {
  panelState.progress = { ...progressWith(1), enrollment_id: 'a'.repeat(32), course_version: 'original', manifest_sha256: 'b'.repeat(64),
    learning_position: { module_id: 'foundations', lesson_id: MODULES.find(module => module.id === 'foundations')!.lessons[0].id!, revision: 1, content_sha256: 'd'.repeat(64), saved_at: '2026-10-09' } }
  let finish!: (value: ValidationResult) => void
  validate.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const view = render(<CertificationPanel />)
  fireEvent.click(screen.getByRole('button', { name: 'Check Progress' }))
  if (field === 'module') {
    fireEvent.click(screen.getByRole('button', { name: 'Curriculum' }))
    fireEvent.click(screen.getByRole('button', { name: /^0 AI Literacy/ }))
  } else if (field === 'learner') panelState.userId = 'another-learner'
  else panelState.progress = { ...panelState.progress!, [field === 'enrollment' ? 'enrollment_id' : 'manifest_sha256']: 'c'.repeat(field === 'enrollment' ? 32 : 64) }
  view.rerender(<CertificationPanel />)
  await act(async () => finish({ ...threeStars, checks: [{ name: 'Old course feedback', passed: true, detail: 'Original course only.' }] }))
  expect(screen.queryByText('Old course feedback')).not.toBeInTheDocument()
  expect(complete).not.toHaveBeenCalled()
})
