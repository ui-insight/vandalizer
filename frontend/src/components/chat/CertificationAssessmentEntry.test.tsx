import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CertModuleCard } from './CertificationCards'

const state = vi.hoisted(() => ({ context: null as unknown, send: vi.fn(), open: vi.fn(), assess: vi.fn() }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ sendChatMessage: state.send }) }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => state.context }))
const identity = { enrollment_id: 'selected', course_version: '5-preview', manifest_sha256: 'a'.repeat(64) }
const card = { ...identity, module_id: 'foundations', title: 'Foundations', sample_documents: ['assigned.pdf'] }
const module = { id: 'foundations', decisionPrompts: [{}] }
function context() {
  return { course: { ...identity, modules: [module], prerequisites: { foundations: [] as string[] } },
    progress: { ...identity, modules: {} }, openPanel: state.open, openAssessment: state.assess }
}
beforeEach(() => { vi.clearAllMocks(); state.context = context() })

it('opens the exact enrolled assessment without asking the agent to grade or prepare', () => {
  render(<CertModuleCard content={card} />)
  fireEvent.click(screen.getByRole('button', { name: 'Open module assessment' }))
  expect(state.assess).toHaveBeenCalledExactlyOnceWith('foundations', identity.enrollment_id, identity.manifest_sha256)
  expect(screen.queryByRole('button', { name: 'Check my progress' })).not.toBeInTheDocument()
  expect(state.send).not.toHaveBeenCalled()
})

it.each(['enrollment_id', 'course_version', 'manifest_sha256', 'module_id'])('keeps a saved card read-only when its %s differs', key => {
  render(<CertModuleCard content={{ ...card, [key]: 'old' }} />)
  expect(screen.queryByRole('button', { name: 'Open module assessment' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Set up lab' })).not.toBeInTheDocument()
  const open = screen.getByRole('button', { name: 'Open current course' })
  expect(open).toBeEnabled()
  fireEvent.click(open)
  expect(state.open).toHaveBeenCalledOnce()
  expect(state.send).not.toHaveBeenCalled()
})

it('requires actual prerequisite completion and updates when it arrives', () => {
  const value = context()
  value.course.prerequisites.foundations = ['ai_literacy']
  state.context = value
  const view = render(<CertModuleCard content={card} />)
  expect(screen.getByRole('button', { name: 'Open module assessment' })).toBeDisabled()
  state.context = { ...value, progress: { ...value.progress, modules: { ai_literacy: { completed: true } } } }
  view.rerender(<CertModuleCard content={card} />)
  expect(screen.getByRole('button', { name: 'Open module assessment' })).toBeEnabled()
})

it('withdraws the action during a course switch or missing provider', () => {
  const view = render(<CertModuleCard content={card} />)
  state.context = { ...context(), progress: { ...identity, enrollment_id: 'another', modules: {} } }
  view.rerender(<CertModuleCard content={card} />)
  expect(screen.queryByRole('button', { name: 'Open module assessment' })).not.toBeInTheDocument()
  state.context = null
  view.rerender(<CertModuleCard content={card} />)
  expect(screen.queryByRole('button', { name: /check my progress|set up lab|open current course/i })).not.toBeInTheDocument()
  expect(state.send).not.toHaveBeenCalled()
})
