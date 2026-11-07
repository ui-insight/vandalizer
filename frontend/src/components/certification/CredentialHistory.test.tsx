import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { CredentialHistory } from './CredentialHistory'
import * as api from '../../api/certification'
vi.mock('../../api/certification', () => ({ getCredentials: vi.fn(), downloadPreservedCertificate: vi.fn() }))
const record = { credential_id: 'original-issuance', enrollment_id: 'previous-course', learner_name: 'Original name', course_title: 'Earlier certification', course_version: null, certified_at: '2024-01-02T00:00:00Z', provenance: 'legacy_completion_unverified' }
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.getCredentials).mockResolvedValue({ credentials: [record] }) })
it('downloads the original issuance while another course is selected', async () => {
  vi.mocked(api.downloadPreservedCertificate).mockResolvedValue(undefined)
  const view = render(<CredentialHistory refreshKey="new-course:false" />)
  const download = await screen.findByRole('button', { name: 'Download certificate for Earlier certification' })
  expect(screen.getByText('Earned 2024-01-02')).toBeInTheDocument()
  fireEvent.click(download)
  await waitFor(() => expect(api.downloadPreservedCertificate).toHaveBeenCalledExactlyOnceWith('original-issuance'))
  view.rerender(<CredentialHistory refreshKey="another-course:false" />)
  await waitFor(() => expect(api.getCredentials).toHaveBeenCalledTimes(2))
  expect(await screen.findByText('Earned 2024-01-02')).toBeInTheDocument()
})
it('retries history reads without repeating a failed download', async () => {
  vi.mocked(api.downloadPreservedCertificate).mockRejectedValue(new Error('Download unavailable'))
  render(<CredentialHistory refreshKey="new-course:false" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Download certificate for Earlier certification' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh certificate history' }))
  await waitFor(() => expect(api.getCredentials).toHaveBeenCalledTimes(2))
  expect(api.downloadPreservedCertificate).toHaveBeenCalledTimes(1)
})

it('describes the preserved issuance scope and does not infer it for older records', async () => {
  const scope = { contract_id: 'original-contract', contract_sha256: 'b'.repeat(64),
    promise: 'This is the original issued competency promise.', agent_assistance: 'These were its original assistance rules.',
    exclusions: ['This credential does not approve institutional decisions.'] }
  vi.mocked(api.getCredentials).mockResolvedValue({ credentials: [record, { ...record,
    credential_id: 'scoped-issuance', course_title: 'Recorded competency course', credential_scope: scope }] })
  render(<CredentialHistory refreshKey="a-different-course" />)
  await screen.findByText('Recorded competency course')
  expect(screen.getAllByText('Recorded certificate scope')).toHaveLength(1)
  expect(screen.getByText(scope.promise)).toBeInTheDocument()
  expect(screen.getByText(scope.agent_assistance, { exact: false })).toBeInTheDocument()
  expect(screen.getByText(scope.exclusions[0])).toBeInTheDocument()
})
