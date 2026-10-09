import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CertCheckCard, CertCompletionCard, CertProgressCard, CertModuleCard } from './CertificationCards'

const state = vi.hoisted(() => ({ enrollment: 'current', courseAvailable: true, progressDigest: 'a'.repeat(64), refresh: vi.fn(), send: vi.fn(), open: vi.fn() }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ sendChatMessage: state.send }) }))
vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanelOptional: () => ({
    progress: { enrollment_id: state.enrollment, course_version: 'original', manifest_sha256: state.progressDigest },
    course: state.courseAvailable ? { enrollment_id: state.enrollment, course_version: 'original', manifest_sha256: 'a'.repeat(64), modules: [{ id: 'foundations' }] } : null,
    refresh: state.refresh, openPanel: state.open,
  }),
}))
const identity = { enrollment_id: 'current', course_version: 'original', manifest_sha256: 'a'.repeat(64) }
const checked = { ...identity, module_id: 'foundations', title: 'Foundations', passed: true, stars: 3, checks: [], course_title: 'Your existing course' }
beforeEach(() => { vi.clearAllMocks(); state.enrollment = 'current'; state.courseAvailable = true; state.progressDigest = 'a'.repeat(64) })

it('describes the completed course without assuming the current catalog size', () => {
  const { rerender } = render(<CertCompletionCard content={{ certified: true, course_title: 'Supervision bridge', modules_total: 3 }} />)
  expect(screen.getByText('Supervision bridge complete — all 3 modules complete.')).toBeInTheDocument()
  rerender(<CertCompletionCard content={{ certified: true }} />)
  expect(screen.getByText('Certification complete — the course requirements are complete.')).toBeInTheDocument()
})

it('disables a stale course submission and offers a read-only refresh', () => {
  render(<CertCheckCard content={{ ...checked, enrollment_id: 'previous' }} />)
  expect(screen.getByRole('button', { name: /bank|complete/i })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: /refresh progress/i }))
  expect(state.refresh).toHaveBeenCalledOnce()
  expect(state.send).not.toHaveBeenCalled()
  expect(screen.getByText('Your existing course · original')).toBeInTheDocument()
})

it('does not treat a historical unversioned card as a current enrollment', () => {
  render(<CertCheckCard content={{ ...checked, enrollment_id: undefined, course_version: undefined, manifest_sha256: undefined }} />)
  expect(screen.getByRole('button', { name: /bank|complete/i })).toBeDisabled()
})

it('allows the action when the card matches the active enrollment', () => {
  render(<CertCheckCard content={{ ...checked, enrollment_id: 'current' }} />)
  const button = screen.getByRole('button', { name: /bank|complete/i })
  expect(button).toBeEnabled()
  fireEvent.click(button)
  expect(state.send).toHaveBeenCalledOnce()
})

it.each([
  { course_version: 'obsolete' }, { manifest_sha256: 'b'.repeat(64) },
  { manifest_sha256: undefined }, { module_id: 'removed_module' },
])('does not allow a check result to act on mismatched course metadata %j', change => {
  render(<CertCheckCard content={{ ...checked, ...change }} />)
  const button = screen.getByRole('button', { name: 'Complete the module' })
  expect(button).toBeDisabled()
  fireEvent.click(button)
  expect(state.send).not.toHaveBeenCalled()
})

it.each(['missing-course', 'mismatched-progress'])('keeps unavailable progress actions disabled: %s', kind => {
  if (kind === 'missing-course') state.courseAvailable = false
  else state.progressDigest = 'b'.repeat(64)
  render(<CertProgressCard content={{ ...identity, modules: [{ module_id: 'foundations', title: 'Foundations', xp: 100, completed: false, stars: 0 }], modules_completed: 0, modules_total: 1, next_module_id: 'foundations' }} />)
  const button = screen.getByRole('button', { name: 'Start with Foundations' })
  expect(button).toBeDisabled()
  fireEvent.click(button)
  expect(state.send).not.toHaveBeenCalled()
})

it('preserves original completion identity and opens the selected course without a chat prompt', () => {
  render(<CertCompletionCard content={{ ...identity, enrollment_id: 'previous', title: 'Foundations', course_title: 'Original course', certified: false }} />)
  expect(screen.getByText('Original course')).toBeInTheDocument()
  expect(screen.getByText('Course version: original')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: "What's next?" })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open current course' }))
  expect(state.open).toHaveBeenCalledOnce()
  expect(state.send).not.toHaveBeenCalled()
})

it('keeps historical instructions and source links readable without enabling course actions', () => {
  render(<CertModuleCard content={{ ...identity, enrollment_id: 'previous', module_id: 'foundations', title: 'Foundations',
    overview: '[Read original source](https://example.test/source)', instructions: ['Inspect the original source.'] }} />)
  const summary = screen.getByText('Exercise instructions · 1 step')
  fireEvent.click(summary)
  expect(summary.closest('details')).toHaveAttribute('open')
  const source = screen.getByRole('link', { name: 'Read original source' })
  let allowed = false
  source.addEventListener('click', event => { allowed = !event.defaultPrevented; event.preventDefault() })
  fireEvent.click(source)
  expect(allowed).toBe(true)
  expect(screen.queryByRole('button', { name: 'Check my progress' })).not.toBeInTheDocument()
  expect(state.send).not.toHaveBeenCalled()
})
