import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { VerificationSession, VerificationSessionField } from '../../api/verificationSessions'

const patchVerificationField = vi.fn()
vi.mock('../../api/verificationSessions', () => ({
  patchVerificationField: (...args: unknown[]) => patchVerificationField(...args),
  finalizeVerificationSession: vi.fn(),
  cancelVerificationSession: vi.fn(),
}))

import { VerificationNavBar } from './VerificationNavBar'

function session(field: VerificationSessionField): VerificationSession {
  return {
    uuid: 'vs-1',
    search_set_uuid: 'ss-1',
    document_uuid: 'doc-1',
    document_title: 'NSF Subaward UI-BSU-2024-0847',
    label: 'NSF Subaward',
    status: 'pending',
    test_case_uuid: null,
    fields: [field],
    all_resolved: false,
    created_at: null,
    updated_at: null,
  }
}

function renderBar(field: VerificationSessionField) {
  const s = session(field)
  patchVerificationField.mockResolvedValue(s)
  render(
    <VerificationNavBar
      session={s}
      onSessionUpdated={() => {}}
      onCompleted={() => {}}
      onActiveValueChange={() => {}}
    />,
  )
}

function clearAndSave(key: string) {
  fireEvent.click(screen.getByRole('button', { name: /correct/i }))
  const input = screen.getByLabelText(`Correct value for ${key}`) as HTMLInputElement
  fireEvent.change(input, { target: { value: '' } })
  const save = screen.getByRole('button', { name: 'Save correction' })
  expect(save).not.toBeDisabled()
  fireEvent.click(save)
}

describe('VerificationNavBar corrections', () => {
  beforeEach(() => patchVerificationField.mockReset())

  it('clearing a correction on a field extracted empty restores it (the ticket)', async () => {
    renderBar({ key: 'Cost Share', extracted: '', expected: '$5,000', status: 'corrected' })
    fireEvent.click(screen.getByRole('button', { name: /correct/i }))
    // Editing starts from the correction, not the original extraction.
    expect(screen.getByLabelText('Correct value for Cost Share')).toHaveValue('$5,000')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    clearAndSave('Cost Share')
    await waitFor(() =>
      expect(patchVerificationField).toHaveBeenCalledWith('vs-1', 'Cost Share', {
        status: 'approved',
        expected: undefined,
      }),
    )
  })

  it('a field extracted with a value can be corrected to empty', async () => {
    renderBar({ key: 'FAIN', extracted: '2024-0847', expected: null, status: 'pending' })
    clearAndSave('FAIN')
    await waitFor(() =>
      expect(patchVerificationField).toHaveBeenCalledWith('vs-1', 'FAIN', {
        status: 'corrected',
        expected: '',
      }),
    )
  })

  it('shows a field corrected to empty as empty', () => {
    renderBar({ key: 'FAIN', extracted: '2024-0847', expected: '', status: 'corrected' })
    expect(screen.getByText('(empty)')).toBeInTheDocument()
    expect(screen.getByText('2024-0847')).toHaveStyle({ textDecoration: 'line-through' })
  })
})
