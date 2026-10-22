import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CertificationPanelProvider, useCertificationPanel } from './CertificationPanelContext'

const state = vi.hoisted(() => ({ value: {} as unknown }))
vi.mock('../hooks/useCertification', () => ({ useCertification: () => state.value }))
const identity = { enrollment_id: 'selected', course_version: 'draft', manifest_sha256: 'hash' }
function context() {
  return { course: { ...identity, modules: [{ id: 'foundations' }], prerequisites: { foundations: [] as string[] } },
    progress: { ...identity, modules: {} } }
}
function Probe() {
  const ctx = useCertificationPanel()
  return <><button onClick={() => ctx.openAssessment('foundations', 'selected', 'hash')}>Open assessment</button>
    <button onClick={() => ctx.consumeAssessmentDestination(1)}>Consume first</button>
    <output>{JSON.stringify({ open: ctx.isOpen, target: ctx.assessmentDestination })}</output></>
}
beforeEach(() => { localStorage.clear(); state.value = context() })
it('opens a named destination and preserves a newer request when an older one is consumed', () => {
  render(<CertificationPanelProvider><Probe /></CertificationPanelProvider>)
  fireEvent.click(screen.getByText('Open assessment'))
  expect(JSON.parse(screen.getByRole('status').textContent!)).toEqual({ open: true, target: { nonce: 1, moduleId: 'foundations', enrollmentId: 'selected', manifestSha256: 'hash' } })
  fireEvent.click(screen.getByText('Open assessment'))
  fireEvent.click(screen.getByText('Consume first'))
  expect(JSON.parse(screen.getByRole('status').textContent!).target.nonce).toBe(2)
})
it.each(['missing', 'enrollment', 'manifest', 'version', 'module', 'prerequisites'])('rejects an unavailable assessment: %s', reason => {
  const value = context()
  if (reason === 'enrollment') value.progress.enrollment_id = 'other'
  if (reason === 'manifest') value.progress.manifest_sha256 = 'other'
  if (reason === 'version') value.progress.course_version = 'other'
  if (reason === 'module') value.course.modules = []
  if (reason === 'prerequisites') value.course.prerequisites.foundations = ['ai_literacy']
  state.value = reason === 'missing' ? { course: null, progress: null } : value
  render(<CertificationPanelProvider><Probe /></CertificationPanelProvider>)
  fireEvent.click(screen.getByText('Open assessment'))
  expect(JSON.parse(screen.getByRole('status').textContent!)).toEqual({ open: false, target: null })
})
