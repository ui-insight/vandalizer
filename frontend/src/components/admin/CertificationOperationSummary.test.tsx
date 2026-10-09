import { expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CertificationOperationSummary } from './CertificationOperationSummary'
import type { CertificationSupportOperations } from '../../api/admin'

it('separates automatic technical failure, required revisions and uncertain execution without staff actions', () => {
  const operations: CertificationSupportOperations = { worker_marked_in_flight: true, course_change_pending: true, groups: [
    { kind: 'automatic_review', more_pending: true, more_recent: true, records: [
      { request_id: 'a'.repeat(32), module_title: 'Foundations', state: 'grading_unavailable', next_step: 'Technical retry uses the same saved evidence.', references: { parent_attempt_id: 'b'.repeat(32), private_content: 'DO NOT SHOW THIS' } },
      { request_id: 'c'.repeat(32), module_title: 'Foundations', state: 'revision_required', next_step: 'Read original feedback.', failed_required_outcomes: [{ outcome_id: 'check', statement: 'Verify the reported source value.' }] },
    ] },
    { kind: 'lab_run', more_pending: false, more_recent: false, records: [
      { request_id: 'd'.repeat(32), module_title: 'Connected workflow', state: 'uncertain', next_step: 'Inspect preserved stage receipts before retrying.', references: { input_snapshot_id: 'e'.repeat(32) } },
    ] },
  ] }
  render(<CertificationOperationSummary operations={operations} />)
  expect(screen.getByText('Foundations · Automatic grading unavailable')).toBeInTheDocument()
  expect(screen.getByText('Foundations · Evidence needs revision')).toBeInTheDocument()
  expect(screen.getByText('Verify the reported source value.')).toBeInTheDocument()
  expect(screen.getByText('Connected workflow · Run outcome uncertain')).toBeInTheDocument()
  expect(screen.getByText(/course selection change is pending/)).toBeInTheDocument()
  expect(screen.getByText(/Additional outstanding records exist/)).toBeInTheDocument()
  expect(screen.getByText('b'.repeat(32))).toBeInTheDocument()
  expect(screen.queryByText('DO NOT SHOW THIS')).toBeNull()
  expect(screen.queryByRole('button')).toBeNull()
})
it('labels absent records without declaring the learner has finished all work', () => {
  render(<CertificationOperationSummary operations={{ worker_marked_in_flight: false, course_change_pending: false, groups: [
    { kind: 'automatic_review', records: [], more_pending: false, more_recent: false },
    { kind: 'lab_run', records: [], more_pending: false, more_recent: false },
  ] }} />)
  expect(screen.getByText('No saved automatic review records exist for this enrollment.')).toBeInTheDocument()
  expect(screen.getByText('No saved lab run records exist for this enrollment.')).toBeInTheDocument()
  expect(screen.getByText(/Saved results do not select evidence or award module credit/)).toBeInTheDocument()
})

it('keeps private handoff receipts separate from execution and excludes delivery actions', () => {
  render(<CertificationOperationSummary operations={{ worker_marked_in_flight: false, course_change_pending: false, groups: [
    { kind: 'private_handoff', more_pending: false, more_recent: true, records: [
      { request_id: 'a'.repeat(32), module_title: 'Output delivery', state: 'delivered', next_step: 'This is only a private training copy.', references: { previous_failed_id: 'b'.repeat(32), review_id: 'c'.repeat(32) } },
      { request_id: 'b'.repeat(32), module_title: 'Output delivery', state: 'failed', next_step: 'The original attempt stopped before a destination write.' },
    ] },
  ] }} />)
  expect(screen.getByRole('heading', { name: 'Private training handoffs' })).toBeInTheDocument()
  expect(screen.getByText('Output delivery · Private training copy saved')).toBeInTheDocument()
  expect(screen.getByText('Output delivery · Training handoff stopped before delivery')).toBeInTheDocument()
  expect(screen.getByText('Original failed handoff')).toBeInTheDocument()
  expect(screen.queryByRole('button')).toBeNull()
})
