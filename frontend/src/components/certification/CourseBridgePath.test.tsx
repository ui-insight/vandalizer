import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { CertificationProgress, CourseDefinition } from '../../types/certification'
import { CourseBridgePath } from './CourseBridgePath'

const course = { enrollment_id: 'owned', course_version: 'v5', manifest_sha256: 'a'.repeat(64), modules: [{ id: 'governance' }],
  bridge_path: { path_id: 'bridge.1', title: 'Already familiar with Vandalizer?', description: 'Start with assessment; study where needed.',
    state: 'design_draft', course_version: 'v5', manifest_sha256: 'a'.repeat(64), required_outcomes: 3,
    credit_policy: 'same_course_same_required_outcomes', duration_minutes: null, rules: ['Every required outcome remains required.'],
    stages: [{ id: 'capstone', title: 'Supervise the complete task', purpose: 'Verify the source and justify the handoff.',
      modules: [{ module_id: 'governance', title: 'Governance', required_outcomes: 3 }] }] } } as CourseDefinition

it('opens the exact assessment without claiming credit or a completion duration', () => {
  const open = vi.fn()
  render(<CourseBridgePath course={course} progress={null} onAssess={open} />)
  fireEvent.click(screen.getByText('Already familiar with Vandalizer?'))
  fireEvent.click(screen.getByRole('button', { name: 'Open assessment: Governance' }))
  expect(open).toHaveBeenCalledExactlyOnceWith('governance')
  expect(screen.getByText(/Unpublished bridge preview/)).toBeInTheDocument()
  expect(screen.getByText('3 required outcomes · the same course certificate')).toBeInTheDocument()
})

it('only labels completion from this enrollment and this pinned course', () => {
  const progress: CertificationProgress = { id: 'bridge-progress', user_id: 'learner',
    enrollment_id: 'owned', course_version: 'v5', manifest_sha256: course.manifest_sha256,
    total_xp: 100, level: 'novice', certified: false, certified_at: null, last_activity_date: null,
    modules: { governance: { completed: true, completed_at: '2026-10-09', stars: 1, xp_earned: 100, attempts: 1 } } }
  const { rerender } = render(<CourseBridgePath course={course} progress={progress} onAssess={vi.fn()} />)
  fireEvent.click(screen.getByText('Already familiar with Vandalizer?'))
  expect(screen.getByRole('button', { name: 'Review assessment: Governance' })).toBeInTheDocument()
  rerender(<CourseBridgePath course={course} progress={{ ...progress, enrollment_id: 'old-course' }} onAssess={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Open assessment: Governance' })).toBeInTheDocument()
  expect(screen.queryByText(/completed in this course/)).not.toBeInTheDocument()
})

it.each(['missing', 'different_course', 'different_manifest', 'missing_outcome', 'unknown_module'])('withholds unsupported bridge navigation: %s', change => {
  const altered = structuredClone(course)
  if (change === 'missing') altered.bridge_path = null
  else if (change === 'different_course') altered.bridge_path!.course_version = 'old'
  else if (change === 'different_manifest') altered.bridge_path!.manifest_sha256 = 'b'.repeat(64)
  else if (change === 'missing_outcome') altered.bridge_path!.required_outcomes = 4
  else altered.bridge_path!.stages[0].modules[0].module_id = 'unavailable'
  const { container } = render(<CourseBridgePath course={altered} progress={null} onAssess={vi.fn()} />)
  expect(container).toBeEmptyDOMElement()
})
