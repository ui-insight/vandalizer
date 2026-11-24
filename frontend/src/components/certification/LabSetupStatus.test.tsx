import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { getLabStatus } from '../../api/certification'
import type { CertificationLabStatus } from '../../types/certification'
import { LabSetupStatus } from './LabSetupStatus'

vi.mock('../../api/certification', () => ({ getLabStatus: vi.fn() }))
const getStatus = vi.mocked(getLabStatus)
const props = { moduleId: 'foundations', enrollmentId: 'enrolled', filenames: ['sample.pdf'], onProvision: vi.fn(), provisioning: false }
function result(state: CertificationLabStatus['state']): CertificationLabStatus {
  return { module_id: 'foundations', enrollment_id: 'enrolled', state, folder_id: 'lab', folder_name: 'Certification Lab',
    documents: ['not_setup', 'not_required'].includes(state) ? [] : [{ name: 'sample.pdf', document_id: 'doc', state: state as 'ready' }], credit_changed: false }
}
beforeEach(() => { vi.clearAllMocks() })

it('does not turn assignment or a pending read into readiness, and refreshes without provisioning', async () => {
  getStatus.mockResolvedValueOnce(result('processing')).mockResolvedValueOnce(result('ready'))
  render(<LabSetupStatus {...props} />)
  expect(screen.getByRole('status')).toHaveTextContent('Checking sample files')
  expect(await screen.findByText('Sample text is not ready yet')).toBeInTheDocument()
  expect(screen.getByText(/Closing the panel does not cancel/)).toBeInTheDocument()
  expect(props.onProvision).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Check sample status' }))
  expect(await screen.findByText('Sample text is ready')).toBeInTheDocument()
  expect(screen.getByText(/setup earns no credit/)).toBeInTheDocument()
  expect(getStatus).toHaveBeenNthCalledWith(2, 'foundations', 'enrolled')
  expect(props.onProvision).not.toHaveBeenCalled()
})

it('prepares explicitly once and then reads actual processing state', async () => {
  getStatus.mockResolvedValueOnce(result('not_setup')).mockResolvedValueOnce(result('processing'))
  const view = render(<LabSetupStatus {...props} />)
  const setup = await screen.findByRole('button', { name: 'Set Up Lab' })
  fireEvent.click(setup); fireEvent.click(setup)
  expect(props.onProvision).toHaveBeenCalledTimes(1)
  view.rerender(<LabSetupStatus {...props} provisioning />)
  expect(screen.getByRole('status')).toHaveTextContent('Preparing sample files')
  expect(screen.getByRole('button', { name: 'Check sample status' })).toBeDisabled()
  view.rerender(<LabSetupStatus {...props} />)
  expect(await screen.findByText('Sample text is not ready yet')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Check sample status' })).toHaveFocus()
})

it('shows a failed sample and its processing recovery instead of repeating setup', async () => {
  getStatus.mockResolvedValue(result('failed'))
  render(<LabSetupStatus {...props} />)
  expect(await screen.findByText('Sample processing failed')).toBeInTheDocument()
  expect(screen.getByText('sample.pdf — Processing failed')).toBeInTheDocument()
  expect(screen.getByText(/repeating lab setup does not repair/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Set Up Lab' })).not.toBeInTheDocument()
  expect(props.onProvision).not.toHaveBeenCalled()
})

it('retains an explicit read retry after transport failure without claiming setup success', async () => {
  getStatus.mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce(result('unavailable'))
  render(<LabSetupStatus {...props} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Your saved work is unchanged')
  expect(screen.queryByRole('button', { name: 'Set Up Lab' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Check sample status' }))
  expect(await screen.findByText('Sample status needs attention')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Set up missing samples' })).toBeEnabled()
  expect(props.onProvision).not.toHaveBeenCalled()
})

it.each(['wrong enrollment', 'wrong module', 'wrong sample', 'false readiness'])('rejects %s', async kind => {
  const value = result('ready')
  if (kind === 'wrong enrollment') value.enrollment_id = 'another-course'
  if (kind === 'wrong module') value.module_id = 'governance'
  if (kind === 'wrong sample') value.documents[0].name = 'private.pdf'
  if (kind === 'false readiness') value.documents[0].state = 'processing'
  getStatus.mockResolvedValue(value)
  render(<LabSetupStatus {...props} />)
  expect(await screen.findByRole('alert')).toBeInTheDocument()
  expect(screen.queryByText('Sample text is ready')).not.toBeInTheDocument()
})

it('ignores a late status response from the previous module', async () => {
  let finish!: (value: CertificationLabStatus) => void
  getStatus.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    .mockResolvedValueOnce({ ...result('not_setup'), module_id: 'batch_processing' })
  const view = render(<LabSetupStatus {...props} />)
  view.rerender(<LabSetupStatus {...props} moduleId="batch_processing" />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Set Up Lab' })).toBeEnabled())
  await act(async () => finish(result('ready')))
  expect(screen.queryByText('Sample text is ready')).not.toBeInTheDocument()
})

it('hands off through the mounted workspace callback once without a reload link', async () => {
  getStatus.mockResolvedValue(result('ready'))
  let finish!: () => void
  const open = vi.fn(() => new Promise<void>(resolve => { finish = resolve }))
  render(<LabSetupStatus {...props} onOpenWorkspace={open} />)
  await screen.findByText('Sample text is ready')
  const button = screen.getByRole('button', { name: 'Open Files in workspace' })
  fireEvent.click(button); fireEvent.click(button)
  expect(open).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Opening Files…' })).toBeDisabled()
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
  await act(async () => finish())
  expect(props.onProvision).not.toHaveBeenCalled()
})

it('keeps the lab and an explicit handoff retry when navigation fails', async () => {
  getStatus.mockResolvedValue(result('ready'))
  const open = vi.fn().mockRejectedValueOnce(new Error('Navigation failed')).mockResolvedValueOnce(undefined)
  render(<LabSetupStatus {...props} onOpenWorkspace={open} />)
  await screen.findByText('Sample text is ready')
  fireEvent.click(screen.getByRole('button', { name: 'Open Files in workspace' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Your lab is still here')
  expect(screen.getByText('Sample text is ready')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open Files in workspace' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(open).toHaveBeenCalledTimes(2)
  expect(getStatus).toHaveBeenCalledTimes(1)
  expect(props.onProvision).not.toHaveBeenCalled()
})
