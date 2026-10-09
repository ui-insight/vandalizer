import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import * as extractions from '../../api/extractions'
import { ApiError } from '../../api/client'
import type { PracticalPreparationBody, SavedPracticalPreparation } from '../../types/certification'
import type { SearchSet } from '../../types/workflow'
import { PracticalPreparation } from './PracticalPreparation'
vi.mock('../../api/certification', () => ({ preparePracticalRun: vi.fn(), getPracticalPreparation: vi.fn() }))
vi.mock('../../api/extractions', () => ({ listSearchSets: vi.fn() }))
const props = { enrollmentId: 'enrollment', moduleId: 'foundations', onPrepared: vi.fn(), onSaved: vi.fn() }
const key = 'certification-preparation:enrollment:foundations'
const extraction = { uuid: 'owned-extraction', title: 'My proposal fields', set_type: 'extraction', item_count: 3 } as SearchSet
function receipt(body: PracticalPreparationBody): SavedPracticalPreparation {
  return { ...body, input_snapshot_id: body.request_id, enrollment_id: 'enrollment', module_id: 'foundations',
    course_version: 'course', manifest_sha256: 'a'.repeat(64), artifact_title: extraction.title, artifact_sha256: 'b'.repeat(64),
    captured_at: '2026-10-06T00:00:00Z', fields: ['PI Name'], documents: [{ document_id: 'source', assigned_filename: 'assigned.pdf', source_sha256: 'c'.repeat(64) }],
    state: 'prepared', run_id: body.request_id, plan_sha256: 'd'.repeat(64), model_names: ['configured-model'], scope_prompt_id: 'scope_review',
    can_execute: false, credit_awarded: false, module_completion_eligible: false }
}
beforeEach(() => {
  vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear()
  vi.mocked(extractions.listSearchSets).mockResolvedValue([extraction])
  vi.mocked(api.preparePracticalRun).mockImplementation(async (_enrollment, _module, body) => receipt(body))
})
async function choose() {
  fireEvent.click(screen.getByRole('button', { name: 'Choose my extraction' }))
  fireEvent.change(await screen.findByLabelText('My extraction'), { target: { value: extraction.uuid } })
  fireEvent.click(screen.getByRole('button', { name: 'Save inputs and prepare for review' }))
}
it('links the selected owned extraction without preparing or executing it', async () => {
  render(<PracticalPreparation {...props} />)
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Choose my extraction' }))
  fireEvent.change(await screen.findByLabelText('My extraction'), { target: { value: extraction.uuid } })
  const link = screen.getByRole('link', { name: 'Open selected extraction in a new tab' })
  expect(new URL(link.getAttribute('href')!, 'https://local.invalid').searchParams.get('extraction')).toBe(extraction.uuid)
  expect(api.preparePracticalRun).not.toHaveBeenCalled()
  expect(props.onPrepared).not.toHaveBeenCalled()
})
it('lazily lists owned extractions and prepares only on an explicit request before scope review', async () => {
  render(<PracticalPreparation {...props} />)
  expect(extractions.listSearchSets).not.toHaveBeenCalled()
  await choose()
  expect(await screen.findByRole('heading', { name: 'Ready for your scope review' })).toBeInTheDocument()
  expect(extractions.listSearchSets).toHaveBeenCalledWith({ scope: 'mine', search: '' })
  const body = vi.mocked(api.preparePracticalRun).mock.calls[0][2]
  expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(body)
  expect(props.onPrepared).not.toHaveBeenCalled()
  expect(props.onSaved).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: 'Review proposed scope' }))
  expect(props.onPrepared).toHaveBeenCalledWith(body.request_id)
  fireEvent.click(screen.getByRole('button', { name: 'Close preparation' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Open saved preparation' })).toHaveFocus())
})
it('recovers a lost response after remount by reading the original receipt without another POST', async () => {
  let original!: PracticalPreparationBody
  vi.mocked(api.preparePracticalRun).mockImplementation(async (_e, _m, body) => { original = body; throw new Error('Response lost') })
  const first = render(<PracticalPreparation {...props} />)
  await choose(); await screen.findByRole('alert'); first.unmount()
  vi.mocked(api.getPracticalPreparation).mockResolvedValue(receipt(original))
  render(<PracticalPreparation {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check and finish saved preparation' }))
  await screen.findByRole('heading', { name: 'Ready for your scope review' })
  expect(api.getPracticalPreparation).toHaveBeenCalledWith('enrollment', original.request_id)
  expect(api.preparePracticalRun).toHaveBeenCalledTimes(1)
})
it('finishes partially saved inputs using exactly the preserved request', async () => {
  const body = { request_id: 'a'.repeat(32), artifact_id: extraction.uuid }
  sessionStorage.setItem(key, JSON.stringify(body))
  vi.mocked(api.getPracticalPreparation).mockResolvedValue({ ...receipt(body), state: 'inputs_saved', run_id: null, plan_sha256: null })
  render(<PracticalPreparation {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check and finish saved preparation' }))
  await screen.findByRole('heading', { name: 'Ready for your scope review' })
  expect(api.preparePracticalRun).toHaveBeenCalledWith('enrollment', 'foundations', body)
})
it('does not send or create a replacement when recovery cannot establish the saved state', async () => {
  const body = { request_id: 'a'.repeat(32), artifact_id: extraction.uuid }
  sessionStorage.setItem(key, JSON.stringify(body))
  vi.mocked(api.getPracticalPreparation).mockRejectedValue(new ApiError(503, 'History unavailable'))
  render(<PracticalPreparation {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check and finish saved preparation' }))
  await screen.findByRole('alert')
  expect(api.preparePracticalRun).not.toHaveBeenCalled()
  expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(body)
})
it('does not transmit when browser storage cannot preserve the request', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage disabled') })
  render(<PracticalPreparation {...props} />)
  await choose()
  expect(await screen.findByRole('alert')).toHaveTextContent('no request was sent')
  expect(api.preparePracticalRun).not.toHaveBeenCalled()
})
it('unlocks the selection only after a definite unsaved rejection', async () => {
  vi.mocked(api.preparePracticalRun).mockRejectedValueOnce(new ApiError(422, 'Provision the assigned documents'))
  render(<PracticalPreparation {...props} />)
  await choose()
  expect(await screen.findByRole('alert')).toHaveTextContent('This preparation was not saved')
  expect(sessionStorage.getItem(key)).toBeNull()
  expect(screen.getByLabelText('My extraction')).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: 'Save inputs and prepare for review' }))
  await screen.findByRole('heading', { name: 'Ready for your scope review' })
  const calls = vi.mocked(api.preparePracticalRun).mock.calls
  expect(calls[0][2].request_id).not.toBe(calls[1][2].request_id)
})
it.each([{ enrollment_id: 'foreign' }, { request_id: 'b'.repeat(32) }, { credit_awarded: true }])('rejects an incompatible preparation receipt %j', async changed => {
  vi.mocked(api.preparePracticalRun).mockImplementation(async (_e, _m, body) => ({ ...receipt(body), ...changed } as SavedPracticalPreparation))
  render(<PracticalPreparation {...props} />)
  await choose(); await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Review proposed scope' })).not.toBeInTheDocument()
  expect(sessionStorage.getItem(key)).not.toBeNull()
})
it('ignores a result arriving after this enrollment view was unmounted', async () => {
  let resolve!: (value: SavedPracticalPreparation) => void
  let body!: PracticalPreparationBody
  vi.mocked(api.preparePracticalRun).mockImplementation((_e, _m, value) => { body = value; return new Promise(done => { resolve = done }) })
  const view = render(<PracticalPreparation {...props} />)
  await choose(); view.unmount()
  render(<PracticalPreparation {...props} enrollmentId="another-course" />)
  await act(async () => { resolve(receipt(body)) })
  expect(screen.queryByRole('button', { name: 'Review proposed scope' })).not.toBeInTheDocument()
  expect(props.onPrepared).not.toHaveBeenCalled()
})

it('distinguishes reading and saving the original preparation', async () => {
  let resolveRead!: (value: SavedPracticalPreparation) => void
  let resolveWrite!: (value: SavedPracticalPreparation) => void
  const body = { request_id: 'a'.repeat(32), artifact_id: extraction.uuid }
  sessionStorage.setItem(key, JSON.stringify(body))
  vi.mocked(api.getPracticalPreparation).mockReturnValue(new Promise(done => { resolveRead = done }))
  vi.mocked(api.preparePracticalRun).mockReturnValue(new Promise(done => { resolveWrite = done }))
  render(<PracticalPreparation {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check and finish saved preparation' }))
  expect(screen.getByRole('status')).toHaveTextContent('Checking the saved preparation')
  await act(async () => resolveRead({ ...receipt(body), state: 'inputs_saved', run_id: null }))
  expect(screen.getByRole('status')).toHaveTextContent('Saving inputs and preparing the run')
  expect(api.preparePracticalRun).toHaveBeenCalledWith('enrollment', 'foundations', body)
  await act(async () => resolveWrite(receipt(body)))
  expect(screen.getByRole('heading', { name: 'Ready for your scope review' })).toBeInTheDocument()
})
