import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import type { CourseDefinition } from '../../types/certification'
import { CourseLearningPolicy } from './CourseLearningPolicy'

const scope = { contract_id: 'original-contract', contract_sha256: 'a'.repeat(64),
  promise: 'Supervise the bounded task defined in this course.',
  agent_assistance: 'The agent may propose work; the learner owns the required decisions.',
  exclusions: ['This is not institutional approval.', 'It does not guarantee future output accuracy.'] }

it('shows the pinned promise, assistance and limits without requiring a separate policy artifact', () => {
  render(<CourseLearningPolicy course={{ credential_scope: { ...scope, state: 'design_draft' } } as CourseDefinition} />)
  expect(screen.getByText(scope.promise)).toBeInTheDocument()
  expect(screen.getByText(scope.agent_assistance, { exact: false })).toBeInTheDocument()
  for (const limit of scope.exclusions) expect(screen.getByText(limit)).toBeInTheDocument()
  expect(screen.getByText('Unpublished course goal. This preview cannot award a credential.')).toBeInTheDocument()
  expect(screen.queryByText('How learning and credit work')).not.toBeInTheDocument()
})

it('does not attach the newer promise to a legacy course', () => {
  const { container } = render(<CourseLearningPolicy course={{} as CourseDefinition} />)
  expect(container).toBeEmptyDOMElement()
})

it('uses the newly selected course scope instead of retaining the earlier description', () => {
  const { rerender } = render(<CourseLearningPolicy course={{ credential_scope: { ...scope, state: 'release_candidate' } } as CourseDefinition} />)
  expect(screen.queryByText(/Unpublished course goal/)).not.toBeInTheDocument()
  rerender(<CourseLearningPolicy course={{ credential_scope: { ...scope, promise: 'Another course has its own recorded scope.', state: 'release_candidate' } } as CourseDefinition} />)
  expect(screen.queryByText(scope.promise)).not.toBeInTheDocument()
  expect(screen.getByText('Another course has its own recorded scope.')).toBeInTheDocument()
})
