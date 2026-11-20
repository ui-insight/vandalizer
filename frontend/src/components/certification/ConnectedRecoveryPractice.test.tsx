import type { ContextType } from 'react'
import { AuthContext } from '../../contexts/AuthContext'
import { ConnectedRecoveryForm } from './ConnectedRecoveryPractice'
import fixtureJson from './__fixtures__/connected-recovery-http.json?raw'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/connectedWorkflow'
import type { ConnectedCapture, ConnectedList, ConnectedRecoveryDecision, ConnectedRun } from '../../types/connectedWorkflow'
import { ConnectedWorkflow } from './ConnectedWorkflow'
import { sameConnectedCase, verifyConnectedCapture, verifyConnectedRecovery, verifyConnectedRun } from './connectedWorkflowState'

vi.mock('../../api/connectedWorkflow', () => ({ getConnectedWork: vi.fn(), getConnectedCapture: vi.fn(), getConnectedRun: vi.fn(), getConnectedReview: vi.fn(), getConnectedScope: vi.fn(), getConnectedRecoveryDecision: vi.fn(), saveConnectedWork: vi.fn() }))
vi.mock('./SavedAutomaticReviews', () => ({ SavedAutomaticReviews: () => <p>Saved feedback reader</p> }))
vi.mock('./PracticalAssessment', () => ({ PracticalAssessment: () => <p>Explicit assessment action</p> }))
// Responses from the real isolated HTTP journey, with synthetic actors and
// model outputs. This fixture is not a live learner or grading calibration.
const fixture = JSON.parse(fixtureJson) as { listing: ConnectedList; capture: ConnectedCapture; plan: ConnectedRun; stopped: ConnectedRun; completed: ConnectedRun; first: ConnectedRecoveryDecision; second: ConnectedRecoveryDecision }
const { listing, stopped, first, second } = fixture
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v))
beforeEach(() => {
  vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear()
  vi.mocked(api.getConnectedWork).mockResolvedValue(clone(listing))
  vi.mocked(api.getConnectedRun).mockResolvedValue(clone(stopped))
  vi.mocked(api.getConnectedRecoveryDecision).mockImplementation(async (_e, id) => clone(id === first.uuid ? first : second))
})

it('accepts the actual HTTP capture, separately approved purposes and original/revised recovery records', () => {
  expect(() => verifyConnectedCapture(fixture.capture, listing)).not.toThrow()
  for (const run of [fixture.plan, stopped, fixture.completed]) expect(() => verifyConnectedRun(run, listing)).not.toThrow()
  for (const saved of [first, second]) expect(() => verifyConnectedRecovery(saved, listing)).not.toThrow()
})

it.each(['provider', 'feedback', 'run', 'receipt', 'authority'])('rejects a mismatched %s in stopped-run evidence', mutation => {
  const value = clone(second)
  if (mutation === 'provider') value.stopped_run.stage_events[3].receipt.result!.provider_dispatched = true
  if (mutation === 'feedback') value.checks.checks[0].supported = false
  if (mutation === 'run') value.submission.run_id = 'f'.repeat(32)
  if (mutation === 'receipt') value.checks.successful_extraction_receipt_sha256 = 'f'.repeat(64)
  if (mutation === 'authority') Object.assign(value.checks, { execution_authorized: true })
  expect(() => verifyConnectedRecovery(value, listing)).toThrow()
})

it('rejects a substituted disclosure while retaining the original case digest', () => {
  const changed = clone(listing.case)
  changed.controlled_failure_practice!.notice = 'A different execution purpose'
  expect(sameConnectedCase(changed, listing.case)).toBe(false)
})

async function openRecovery(historyOnly = false) {
  render(<ConnectedWorkflow enrollmentId={listing.enrollment_id} definition={listing.case} historyOnly={historyOnly} />)
  fireEvent.change(await screen.findByRole('combobox', { name: 'Open saved connected work' }), { target: { value: 'recovery:' + first.uuid } })
  await screen.findByRole('heading', { name: 'Reconsider the unsupported recovery choices' })
}

it('reads original stopped-run choices from course history without write or grading controls', async () => {
  await openRecovery(true)
  expect(screen.getByRole('region', { name: 'Your saved recovery explanation' })).toHaveTextContent(first.submission.explanation)
  expect(screen.queryByRole('button', { name: 'Revise recovery choices and preserve original' })).not.toBeInTheDocument()
  expect(screen.queryByRole('form', { name: 'Inspect your stopped run and choose recovery' })).not.toBeInTheDocument()
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
})

it('recovers a lost revision reply by reading the same saved request without rerunning work', async () => {
  vi.spyOn(crypto, 'randomUUID').mockReturnValue(second.uuid as ReturnType<Crypto['randomUUID']>)
  vi.mocked(api.saveConnectedWork).mockRejectedValue(new Error('Lost after durable save'))
  await openRecovery()
  fireEvent.click(screen.getByRole('button', { name: 'Revise recovery choices and preserve original' }))
  fireEvent.click(screen.getByRole('radio', { name: 'Reasoning' }))
  fireEvent.click(screen.getByRole('radio', { name: 'Original run, successful output and failed-stage evidence' }))
  fireEvent.click(screen.getByRole('radio', { name: 'Prepare and separately approve a new internal run' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Explain the evidence and recovery limits' }), { target: { value: second.submission.explanation } })
  fireEvent.click(screen.getByRole('button', { name: 'Save revised recovery choices' }))
  await screen.findByRole('alert')
  expect(api.saveConnectedWork).toHaveBeenCalledWith(listing.enrollment_id, { action: 'recovery', body: second.submission })
  fireEvent.click(screen.getByRole('button', { name: 'Check pending request' }))
  await screen.findByRole('heading', { name: 'Recovery choices match this saved run' })
  expect(api.getConnectedRecoveryDecision).toHaveBeenLastCalledWith(listing.enrollment_id, second.uuid)
  expect(api.saveConnectedWork).toHaveBeenCalledOnce()
  expect(screen.queryByRole('heading', { name: 'Reconsider the unsupported recovery choices' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run this approved revision' })).not.toBeInTheDocument()
})

it('prepares a separate normal run only after an explicit learner action, without executing it', async () => {
  vi.mocked(api.getConnectedRecoveryDecision).mockResolvedValue(clone(second))
  vi.spyOn(crypto, 'randomUUID').mockReturnValue('f'.repeat(32) as ReturnType<Crypto['randomUUID']>)
  vi.mocked(api.saveConnectedWork).mockImplementation(() => new Promise(() => {}))
  render(<ConnectedWorkflow enrollmentId={listing.enrollment_id} definition={listing.case} />)
  fireEvent.change(await screen.findByRole('combobox', { name: 'Open saved connected work' }), { target: { value: 'recovery:' + second.uuid } })
  const prepare = await screen.findByRole('button', { name: 'Prepare separate internal run for fresh approval' })
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
  fireEvent.click(prepare)
  await waitFor(() => expect(api.saveConnectedWork).toHaveBeenCalledOnce())
  expect(api.saveConnectedWork).toHaveBeenCalledWith(listing.enrollment_id, { action: 'prepare', body: {
    request_id: 'f'.repeat(32), input_snapshot_id: stopped.input_snapshot_id, input_snapshot_sha256: stopped.input_snapshot.input_snapshot_sha256,
    case_sha256: listing.case.case_sha256, consent: 'prepare_connected_workflow_plan' } })
})

it('retains recovery choices and explanation without saving, and separates a changed receipt or revision', () => {
  const send = vi.fn(), auth = { user: { user_id: 'recovery-learner' } } as NonNullable<ContextType<typeof AuthContext>>
  const node = (run = stopped, previous?: ConnectedRecoveryDecision) => <AuthContext.Provider value={auth}><ConnectedRecoveryForm run={run} previous={previous} disabled={false} send={send} /></AuthContext.Provider>
  let view = render(node())
  fireEvent.click(screen.getByRole('radio', { name: 'Reasoning' }))
  fireEvent.click(screen.getByRole('radio', { name: 'Original run, successful output and failed-stage evidence' }))
  fireEvent.click(screen.getByRole('radio', { name: 'Prepare and separately approve a new internal run' }))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'My unfinished explanation of the saved failed stage and the limits of recovery.' } })
  view.unmount(); view = render(node())
  expect(screen.getByRole('radio', { name: 'Reasoning' })).toBeChecked()
  expect(screen.getByRole('radio', { name: 'Prepare and separately approve a new internal run' })).toBeChecked()
  expect(screen.getByRole('textbox')).toHaveValue('My unfinished explanation of the saved failed stage and the limits of recovery.')
  view.rerender(node({ ...stopped, stage_events_sha256: 'f'.repeat(64) }))
  expect(screen.getByRole('radio', { name: 'Reasoning' })).not.toBeChecked()
  expect(screen.getByRole('textbox')).toHaveValue('')
  view.rerender(node(stopped, first))
  expect(screen.getByRole('textbox')).toHaveValue(first.submission.explanation)
  view.rerender(node())
  expect(screen.getByRole('textbox')).toHaveValue('My unfinished explanation of the saved failed stage and the limits of recovery.')
  expect(send).not.toHaveBeenCalled()
})
