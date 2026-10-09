import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { getLabStatus } from '../../api/certification'
import type { CertificationLabStatus } from '../../types/certification'
import { CourseSamplePreview } from './CourseSamplePreview'

vi.mock('../../api/certification', () => ({ getLabStatus: vi.fn() }))
vi.mock('../files/DocumentViewer', () => ({ DocumentViewer: ({ docUuid }: { docUuid: string }) => <p>Viewing {docUuid}</p> }))
const props = { moduleId: 'foundations', enrollmentId: 'course', documentId: 'sample', name: 'sample.pdf', onClose: vi.fn() }
const status: CertificationLabStatus = { module_id: 'foundations', enrollment_id: 'course', state: 'ready', folder_id: 'lab', folder_name: 'Lab', credit_changed: false,
  documents: [{ name: 'sample.pdf', document_id: 'sample', state: 'ready' }] }
beforeEach(() => { vi.clearAllMocks() })
it('checks current course assignment before opening a viewer and returns to the course explicitly', async () => {
  vi.mocked(getLabStatus).mockResolvedValue(structuredClone(status))
  render(<CourseSamplePreview {...props} />)
  expect(screen.queryByText('Viewing sample')).not.toBeInTheDocument()
  expect(await screen.findByText('Viewing sample')).toBeInTheDocument()
  expect(getLabStatus).toHaveBeenCalledWith('foundations', 'course')
  fireEvent.click(screen.getByRole('button', { name: 'Return to course' }))
  expect(props.onClose).toHaveBeenCalledOnce()
})
it.each(['course', 'source', 'filename', 'folder'])('does not open a source after its %s binding changes', async kind => {
  const value = structuredClone(status)
  if (kind === 'course') value.enrollment_id = 'different-course'
  if (kind === 'source') value.documents[0].document_id = null
  if (kind === 'filename') value.documents[0].name = 'other.pdf'
  if (kind === 'folder') value.folder_id = null
  vi.mocked(getLabStatus).mockResolvedValue(value)
  render(<CourseSamplePreview {...props} />)
  await screen.findByRole('alert')
  expect(screen.queryByText('Viewing sample')).not.toBeInTheDocument()
})
it('retries only the access read and rejects late responses for another source', async () => {
  let finish!: (value: CertificationLabStatus) => void
  vi.mocked(getLabStatus).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    .mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce({ ...status, documents: [{ ...status.documents[0], document_id: 'other' }] })
  const view = render(<CourseSamplePreview {...props} />)
  view.rerender(<CourseSamplePreview {...props} documentId="other" />)
  await screen.findByRole('alert')
  await act(async () => finish(status))
  expect(screen.queryByText('Viewing sample')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Check sample access again' }))
  await waitFor(() => expect(screen.getByText('Viewing other')).toBeInTheDocument())
  expect(getLabStatus).toHaveBeenCalledTimes(3)
})
