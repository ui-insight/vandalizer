import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as api from '../../api/certification'
import { CertCompletionCard, CertProgressCard } from './CertificationCards'

const state = vi.hoisted(() => ({ enrollment: 'current' as string | undefined, send: vi.fn() }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ sendChatMessage: state.send }) }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => ({ progress: { enrollment_id: state.enrollment }, refresh: vi.fn() }) }))
vi.mock('../../api/certification', () => ({ getCredentials: vi.fn(), downloadPreservedCertificate: vi.fn(), downloadCertificate: vi.fn() }))
const original = { credential_id: 'original-credential', enrollment_id: 'previous', learner_name: 'Learner', course_title: 'Preserved course', course_version: 'original-version', certified_at: '2024-01-02', provenance: 'verified_completion' }
beforeEach(() => {
  vi.clearAllMocks(); state.enrollment = 'current'
  vi.mocked(api.getCredentials).mockResolvedValue({ credentials: [original, { ...original, credential_id: 'new-credential', enrollment_id: 'current' }] })
  vi.mocked(api.downloadPreservedCertificate).mockResolvedValue(undefined)
  vi.mocked(api.downloadCertificate).mockResolvedValue(undefined)
})

it.each([CertCompletionCard, CertProgressCard])('downloads the preserved course from a historical card without using today’s selection', async Card => {
  render(<Card content={{ certified: true, enrollment_id: 'previous', course_title: 'Preserved course', course_version: 'original-version' }} />)
  const action = screen.getByRole('button', { name: 'Download certificate (PDF)' })
  expect(action).toBeEnabled()
  fireEvent.click(action)
  await waitFor(() => expect(api.downloadPreservedCertificate).toHaveBeenCalledExactlyOnceWith('original-credential'))
  expect(api.downloadCertificate).not.toHaveBeenCalled()
  expect(state.send).not.toHaveBeenCalled()
})

it('does not substitute the selected course when the original issuance is missing', async () => {
  vi.mocked(api.getCredentials).mockResolvedValue({ credentials: [{ ...original, enrollment_id: 'current' }] })
  render(<CertCompletionCard content={{ certified: true, enrollment_id: 'previous' }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Download certificate (PDF)' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('The original certificate is not available yet')
  expect(api.downloadPreservedCertificate).not.toHaveBeenCalled()
  expect(api.downloadCertificate).not.toHaveBeenCalled()
})

it('keeps a failed download retry bound to the same original issuance', async () => {
  vi.mocked(api.downloadPreservedCertificate).mockRejectedValueOnce(new Error('Certificate service unavailable'))
  render(<CertCompletionCard content={{ certified: true, enrollment_id: 'previous' }} />)
  const action = screen.getByRole('button', { name: 'Download certificate (PDF)' })
  fireEvent.click(action)
  expect(await screen.findByRole('alert')).toHaveTextContent('Certificate service unavailable')
  fireEvent.click(action)
  await waitFor(() => expect(api.downloadPreservedCertificate).toHaveBeenCalledTimes(2))
  expect(vi.mocked(api.downloadPreservedCertificate).mock.calls).toEqual([['original-credential'], ['original-credential']])
  expect(state.send).not.toHaveBeenCalled()
})

it('requires choosing from history when an unversioned card cannot identify its earned course', async () => {
  render(<CertCompletionCard content={{ certified: true }} />)
  expect(screen.queryByRole('button', { name: 'Download certificate (PDF)' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'View earned certificates' }))
  await screen.findByRole('heading', { name: 'Your earned certificates' })
  await waitFor(() => expect(api.getCredentials).toHaveBeenCalledOnce())
  expect(api.downloadCertificate).not.toHaveBeenCalled()
  expect(api.downloadPreservedCertificate).not.toHaveBeenCalled()
})

it('supports the existing unversioned course certificate endpoint when still on that course', async () => {
  state.enrollment = undefined
  render(<CertCompletionCard content={{ certified: true }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Download certificate (PDF)' }))
  await waitFor(() => expect(api.downloadCertificate).toHaveBeenCalledExactlyOnceWith())
  expect(api.getCredentials).not.toHaveBeenCalled()
  expect(state.send).not.toHaveBeenCalled()
})

it('does not offer a certificate before course completion', () => {
  render(<CertCompletionCard content={{ certified: false, enrollment_id: 'current' }} />)
  expect(screen.queryByRole('button', { name: /certificate/i })).not.toBeInTheDocument()
})
