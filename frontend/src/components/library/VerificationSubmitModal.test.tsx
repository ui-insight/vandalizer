import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { VerificationSubmitModal } from './VerificationSubmitModal'

vi.mock('focus-trap-react', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ user: { user_id: 'u1', name: 'Ada', email: 'ada@example.edu' } }),
}))
vi.mock('../../api/library', () => ({
  submitForVerification: vi.fn().mockResolvedValue({}),
}))

import { submitForVerification } from '../../api/library'

function open(props: Partial<React.ComponentProps<typeof VerificationSubmitModal>> = {}) {
  const onClose = vi.fn()
  const onSubmitted = vi.fn()
  render(
    <VerificationSubmitModal itemKind="workflow" itemId="wf-1" itemTitle="Budget check" onClose={onClose} onSubmitted={onSubmitted} {...props} />,
  )
  return { onClose, onSubmitted }
}

describe('VerificationSubmitModal', () => {
  beforeEach(() => vi.mocked(submitForVerification).mockClear())

  it('opens on "what do you want?" and hides the team card when the caller cannot share to a team', () => {
    open()
    expect(screen.getByText('Share with everyone — it works for me')).toBeTruthy()
    expect(screen.getByText('Get a second pair of eyes')).toBeTruthy()
    expect(screen.queryByText('Share with a team')).toBeNull()
  })

  it('"Share with a team" closes the wizard and hands off — no examiner involved', () => {
    const onShareWithTeam = vi.fn()
    const { onClose } = open({ onShareWithTeam })
    fireEvent.click(screen.getByText('Share with a team'))
    expect(onClose).toHaveBeenCalled()
    expect(onShareWithTeam).toHaveBeenCalled()
    expect(submitForVerification).not.toHaveBeenCalled()
  })

  it('"Get a second pair of eyes" is the needs-help path: skip_validation true, and the button says so', async () => {
    const { onSubmitted } = open()
    fireEvent.click(screen.getByText('Get a second pair of eyes'))
    // Basics -> Details -> Review
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText(/an examiner will look it over and run a validation/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Ask for a look/ }))
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled())
    expect(vi.mocked(submitForVerification).mock.calls[0][0]).toMatchObject({ item_id: 'wf-1', skip_validation: true })
  })

  it('"Share with everyone" submits with skip_validation false', async () => {
    const { onSubmitted } = open()
    fireEvent.click(screen.getByText('Share with everyone — it works for me'))
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByRole('button', { name: /^Share with everyone$/ }))
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled())
    expect(vi.mocked(submitForVerification).mock.calls[0][0]).toMatchObject({ skip_validation: false })
  })
})
