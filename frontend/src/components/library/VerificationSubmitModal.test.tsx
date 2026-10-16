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
    expect(screen.getByText(/I've already validated it/)).toBeTruthy()
    expect(screen.getByText(/I haven't validated it yet/)).toBeTruthy()
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

  it('"I haven\'t validated it yet" is the needs-help path: skip_validation true, and the button says so', async () => {
    const { onSubmitted } = open()
    fireEvent.click(screen.getByText(/I haven't validated it yet/))
    // Basics -> Details -> Review
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByText('Next'))
    expect(screen.getByText(/an examiner will run a validation/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Ask for a look/ }))
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled())
    expect(vi.mocked(submitForVerification).mock.calls[0][0]).toMatchObject({ item_id: 'wf-1', skip_validation: true })
  })

  it('"I\'ve already validated it" submits with skip_validation false', async () => {
    const { onSubmitted } = open()
    fireEvent.click(screen.getByText(/I've already validated it/))
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByText('Next'))
    fireEvent.click(screen.getByRole('button', { name: /^Share with everyone$/ }))
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled())
    expect(vi.mocked(submitForVerification).mock.calls[0][0]).toMatchObject({ skip_validation: false })
  })

  describe('closing after typing', () => {
    function typeDescription() {
      const result = open()
      fireEvent.click(screen.getByText(/I've already validated it/))
      fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Checks F&A rates' } })
      return result
    }

    it('Esc with nothing typed closes at once', () => {
      const { onClose } = open()
      fireEvent.keyDown(document, { key: 'Escape' })
      expect(onClose).toHaveBeenCalled()
    })

    it('Esc after typing asks first and keeps what was typed', () => {
      const { onClose } = typeDescription()
      fireEvent.keyDown(document, { key: 'Escape' })
      expect(onClose).not.toHaveBeenCalled()
      expect(screen.getByText('Discard your changes?')).toBeTruthy()
      fireEvent.click(screen.getByText('Keep editing'))
      expect(screen.queryByText('Discard your changes?')).toBeNull()
      expect((screen.getByLabelText('Description') as HTMLTextAreaElement).value).toBe('Checks F&A rates')
    })

    it('a second Esc while asking keeps editing instead of closing', () => {
      const { onClose } = typeDescription()
      fireEvent.keyDown(document, { key: 'Escape' })
      fireEvent.keyDown(document, { key: 'Escape' })
      expect(onClose).not.toHaveBeenCalled()
      expect(screen.queryByText('Discard your changes?')).toBeNull()
    })

    it('Cancel and the close button ask too; Discard closes', () => {
      const { onClose } = typeDescription()
      fireEvent.click(screen.getByText('Cancel'))
      expect(screen.getByText('Discard your changes?')).toBeTruthy()
      fireEvent.click(screen.getByText('Keep editing'))
      fireEvent.click(screen.getByRole('button', { name: 'Close' }))
      expect(onClose).not.toHaveBeenCalled()
      fireEvent.click(screen.getByText('Discard'))
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('names the item kind in the title instead of one of the options', () => {
    open({ itemKind: 'search_set' })
    expect(screen.getByRole('heading', { name: 'Share this extraction' })).toBeTruthy()
  })

  it('says Summary is required and will not go past Basics without it', () => {
    open()
    fireEvent.click(screen.getByText(/I've already validated it/))
    fireEvent.change(screen.getByLabelText('Summary *'), { target: { value: '  ' } })
    expect(screen.getByText('Summary is required.')).toBeTruthy()
    expect((screen.getByText('Next').closest('button') as HTMLButtonElement).disabled).toBe(true)
  })

  it('explains the disabled final button when Review is reached with no Summary', () => {
    open({ itemTitle: '' })
    fireEvent.click(screen.getByText(/I've already validated it/))
    fireEvent.click(screen.getByText('4. Review'))
    expect(screen.getByText('Summary is required (Basics step).')).toBeTruthy()
    expect((screen.getByRole('button', { name: /^Share with everyone$/ }) as HTMLButtonElement).disabled).toBe(true)
  })
})
