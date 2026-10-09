import { expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ModuleDetail } from './ModuleDetail'
import { MODULES } from './modules'
import type { ModuleDefinition, CertExercise } from '../../types/certification'

vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { user_id: 'learner' } }) }))
vi.mock('./PracticalReview', () => ({ PracticalReview: () => <h2>Assigned assessment directions</h2> }))
const legacy = MODULES.find(module => module.id === 'foundations')!
const draft = { ...legacy, assessment: null, decisionPrompts: [{ id: 'decision' }] } as unknown as ModuleDefinition
const exercise = { documents: ['assigned.pdf'], instructions: ['Review your source.'], overview: 'Assigned work', expected_fields: [], star_criteria: {} } as unknown as CertExercise
const props = { moduleProgress: null, onValidate: vi.fn(), onComplete: vi.fn(), onProvision: vi.fn(), onSubmitAssessment: vi.fn(), exercise,
  validating: false, completing: false, provisioning: false, submittingAssessment: false, enrollmentId: 'selected' }

it('opens draft directions without a prepared lab and focuses the requested challenge once', async () => {
  const view = render(<ModuleDetail {...props} module={draft} openChallengeRequest={1} />)
  expect(screen.getByRole('heading', { name: 'Assigned assessment directions' })).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Challenge' })).toHaveFocus())
  fireEvent.click(screen.getByRole('button', { name: 'Learn' }))
  view.rerender(<ModuleDetail {...props} module={draft} openChallengeRequest={1} />)
  expect(screen.queryByRole('heading', { name: 'Assigned assessment directions' })).not.toBeInTheDocument()
  view.rerender(<ModuleDetail {...props} module={draft} openChallengeRequest={2} />)
  expect(screen.getByRole('heading', { name: 'Assigned assessment directions' })).toBeInTheDocument()
  expect(props.onProvision).not.toHaveBeenCalled()
  expect(props.onValidate).not.toHaveBeenCalled()
  expect(props.onComplete).not.toHaveBeenCalled()
})

it('preserves the original lab requirement for a legacy exercise', () => {
  render(<ModuleDetail {...props} module={legacy} />)
  expect(screen.getByRole('button', { name: 'Challenge' })).toBeDisabled()
})

it('does not imply an outcome assessment has never started or uses a three-star rubric', () => {
  const saved = { completed: false, stars: 0, attempts: 2, provisioned_docs: ['assigned'] }
  const view = render(<ModuleDetail {...props} module={draft} moduleProgress={saved} />)
  expect(screen.getByText('Module: Not complete')).toBeInTheDocument()
  expect(screen.queryByText('Challenge: Not started')).not.toBeInTheDocument()
  expect(screen.queryByRole('img', { name: /stars/ })).not.toBeInTheDocument()
  view.rerender(<ModuleDetail {...props} module={legacy} moduleProgress={{ ...saved, completed: true, stars: 2 }} />)
  expect(screen.getByText('Challenge: Complete')).toBeInTheDocument()
  expect(screen.getAllByRole('img', { name: '2 of 3 stars' })).toHaveLength(2)
})
