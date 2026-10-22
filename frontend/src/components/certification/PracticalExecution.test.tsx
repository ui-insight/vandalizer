import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import type { SavedPracticalExecution } from '../../types/certification'
import { PracticalExecution } from './PracticalExecution'
vi.mock('../../api/certification', () => ({ getPracticalExecution: vi.fn(), executePracticalRun: vi.fn() }))
const props = { enrollmentId: 'enrollment', moduleId: 'foundations', runId: 'a'.repeat(32), onChanged: vi.fn(), onReviewResult: vi.fn() }
const key = `certification-execution:enrollment:${props.runId}`
const ready: SavedPracticalExecution = { enrollment_id: 'enrollment', module_id: 'foundations', course_version: 'course', manifest_sha256: 'b'.repeat(64), input_snapshot_id: 'a'.repeat(32), run_id: props.runId,
  state: 'prepared', plan_sha256: 'c'.repeat(64), scope_decision_id: 'd'.repeat(32), scope_decision_sha256: 'e'.repeat(64), model_names: ['configured-model'], can_execute: true, blocked_reason: null,
  started_at: null, finished_at: null, documents_executed: null, result_available: false, credit_awarded: false, module_completion_eligible: false }
const completed: SavedPracticalExecution = { ...ready, state: 'completed', can_execute: false, documents_executed: 1, result_available: true }
beforeEach(() => {
  vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear()
  vi.mocked(api.getPracticalExecution).mockResolvedValue(ready)
  vi.mocked(api.executePracticalRun).mockResolvedValue(completed)
})
async function checkStatus() { fireEvent.click(screen.getByRole('button', { name: 'Check execution status' })); await screen.findByRole('region', { name: 'Saved execution status' }) }
it('checks lazily and executes only the explicitly displayed plan and approval', async () => {
  render(<PracticalExecution {...props} />)
  expect(api.getPracticalExecution).not.toHaveBeenCalled()
  await checkStatus()
  expect(api.executePracticalRun).not.toHaveBeenCalled()
  await waitFor(() => expect(screen.getByRole('region', { name: 'Saved execution status' })).toHaveFocus())
  fireEvent.click(screen.getByRole('button', { name: 'Run these saved inputs' }))
  await screen.findByRole('heading', { name: 'Execution result saved' })
  expect(api.executePracticalRun).toHaveBeenCalledWith(props.enrollmentId, props.runId, { plan_sha256: ready.plan_sha256, scope_decision_id: ready.scope_decision_id, scope_decision_sha256: ready.scope_decision_sha256, consent: 'execute_saved_inputs' })
  expect(sessionStorage.getItem(key)).toBeNull()
  expect(props.onReviewResult).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Review saved values' }))
  expect(props.onReviewResult).toHaveBeenCalledOnce()
})
it('preserves a lost execution request across remount and recovers using GET only', async () => {
  vi.mocked(api.executePracticalRun).mockRejectedValue(new Error('Lost response'))
  const first = render(<PracticalExecution {...props} />)
  await checkStatus(); fireEvent.click(screen.getByRole('button', { name: 'Run these saved inputs' }))
  await screen.findByRole('alert')
  expect(sessionStorage.getItem(key)).not.toBeNull()
  first.unmount()
  vi.mocked(api.getPracticalExecution).mockResolvedValue(completed)
  render(<PracticalExecution {...props} />)
  expect(screen.getByText(/An execution request awaits confirmation/)).toBeInTheDocument()
  await checkStatus()
  expect(screen.getByRole('heading', { name: 'Execution result saved' })).toBeInTheDocument()
  expect(api.executePracticalRun).toHaveBeenCalledOnce()
})
it('never automatically POSTs when a recovered status is still prepared', async () => {
  sessionStorage.setItem(key, '{}')
  render(<PracticalExecution {...props} />)
  await checkStatus()
  expect(screen.getByRole('button', { name: 'Run these saved inputs' })).toBeEnabled()
  expect(api.executePracticalRun).not.toHaveBeenCalled()
})
it.each(['executing', 'failed', 'uncertain'] as const)('shows %s without a rerun control or assessment failure', async state => {
  vi.mocked(api.getPracticalExecution).mockResolvedValue({ ...ready, state, can_execute: false })
  render(<PracticalExecution {...props} />); await checkStatus()
  expect(screen.queryByRole('button', { name: 'Run these saved inputs' })).not.toBeInTheDocument()
  expect(api.executePracticalRun).not.toHaveBeenCalled()
  if (state !== 'executing') expect(screen.getByText(/not a failed assessment/)).toBeInTheDocument()
})
it('keeps uncertain request recovery read-only when status is unavailable', async () => {
  sessionStorage.setItem(key, '{}')
  vi.mocked(api.getPracticalExecution).mockRejectedValue(new Error('Unavailable'))
  render(<PracticalExecution {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check execution status' }))
  await screen.findByRole('alert')
  expect(sessionStorage.getItem(key)).not.toBeNull()
  expect(api.executePracticalRun).not.toHaveBeenCalled()
})
it('does not dispatch if browser storage cannot preserve the reference', async () => {
  render(<PracticalExecution {...props} />); await checkStatus()
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage disabled') })
  fireEvent.click(screen.getByRole('button', { name: 'Run these saved inputs' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('no execution request was sent')
  expect(api.executePracticalRun).not.toHaveBeenCalled()
})
it.each([{ enrollment_id: 'foreign' }, { run_id: 'f'.repeat(32) }, { credit_awarded: true }, { state: 'completed', can_execute: true }])('rejects mismatched or contradictory saved statuses (%j)', async change => {
  vi.mocked(api.getPracticalExecution).mockResolvedValue({ ...ready, ...change } as SavedPracticalExecution)
  render(<PracticalExecution {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check execution status' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Run these saved inputs' })).not.toBeInTheDocument()
})
it('hides stale readiness after a changed-approval response and requires a fresh read', async () => {
  vi.mocked(api.executePracticalRun).mockResolvedValue({ ...completed, scope_decision_id: 'f'.repeat(32) })
  render(<PracticalExecution {...props} />); await checkStatus()
  fireEvent.click(screen.getByRole('button', { name: 'Run these saved inputs' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Run these saved inputs' })).not.toBeInTheDocument()
  expect(sessionStorage.getItem(key)).not.toBeNull()
})
it('ignores a late response after leaving the run', async () => {
  let finish!: (value: SavedPracticalExecution) => void
  vi.mocked(api.getPracticalExecution).mockReturnValue(new Promise(resolve => { finish = resolve }))
  const view = render(<PracticalExecution {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check execution status' })); view.unmount()
  await act(async () => finish(ready))
  expect(props.onChanged).not.toHaveBeenCalled()
})

it('distinguishes checking an uncertain request from sending execution and makes no timing promise', async () => {
  sessionStorage.setItem(key, JSON.stringify({ pending: true }))
  let resolve!: (value: SavedPracticalExecution) => void
  vi.mocked(api.getPracticalExecution).mockReturnValue(new Promise(done => { resolve = done }))
  render(<PracticalExecution {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check execution status' }))
  expect(screen.getByRole('status')).toHaveTextContent('Checking the saved execution state')
  expect(api.executePracticalRun).not.toHaveBeenCalled()
  await act(async () => resolve(ready))
  expect(screen.queryByText(/take up to two minutes/)).not.toBeInTheDocument()
  vi.mocked(api.executePracticalRun).mockReturnValue(new Promise(done => { resolve = done }))
  fireEvent.click(screen.getByRole('button', { name: 'Run these saved inputs' }))
  expect(screen.getByRole('status')).toHaveTextContent('Sending the execution request')
  expect(screen.getByRole('heading', { name: 'Last confirmed: Saved run is prepared' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run these saved inputs' })).not.toBeInTheDocument()
  expect(screen.getByText(/Closing this panel does not confirm/)).toBeInTheDocument()
  await act(async () => resolve(completed))
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
