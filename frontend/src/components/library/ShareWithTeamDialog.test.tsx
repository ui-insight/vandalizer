import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ShareWithTeamDialog } from './ShareWithTeamDialog'

vi.mock('focus-trap-react', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

const TEAMS = [
  { id: 'team-a', name: 'OSP Pre-Award' },
  { id: 'team-b', name: 'Post-Award' },
]

describe('ShareWithTeamDialog', () => {
  // Ticket: opened from the share wizard, this dialog had no way back.
  it('shows Back only when opened from another step, and Back is not Cancel', () => {
    const onBack = vi.fn()
    const onCancel = vi.fn()
    const { rerender } = render(
      <ShareWithTeamDialog itemName="Award intake" teams={TEAMS} onCancel={onCancel} onConfirm={vi.fn()} />,
    )
    expect(screen.queryByRole('button', { name: 'Back' })).toBeNull()

    rerender(
      <ShareWithTeamDialog itemName="Award intake" teams={TEAMS} onBack={onBack} onCancel={onCancel} onConfirm={vi.fn()} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(onBack).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('shows a team picker defaulting to the current team, and sends the choice', async () => {
    const onConfirm = vi.fn()
    render(
      <ShareWithTeamDialog
        itemName="Award intake"
        teams={TEAMS}
        defaultTeamId="team-b"
        onCancel={vi.fn()}
        onConfirm={onConfirm}
      />,
    )

    const select = screen.getByLabelText('Team') as HTMLSelectElement
    expect(select.value).toBe('team-b')
    expect(screen.getByRole('option', { name: 'Post-Award (current team)' })).toBeTruthy()

    fireEvent.change(select, { target: { value: 'team-a' } })
    fireEvent.click(screen.getByRole('button', { name: 'Share with OSP Pre-Award' }))

    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith('', 'team-a'))
  })

  it('names the only team instead of showing a picker', () => {
    render(
      <ShareWithTeamDialog
        itemName="Award intake"
        teams={[TEAMS[0]]}
        defaultTeamId="team-a"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )

    expect(screen.queryByLabelText('Team')).toBeNull()
    expect(screen.getByText('OSP Pre-Award')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Share with OSP Pre-Award' })).toBeTruthy()
  })

  it('names a fixed destination when there is nothing to choose', () => {
    render(
      <ShareWithTeamDialog
        itemName="2 CFR 200"
        teamName="Post-Award"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )

    expect(screen.queryByLabelText('Team')).toBeNull()
    expect(screen.getByText('Post-Award')).toBeTruthy()
  })

  it('falls back to the first team when the current team is not in the list', () => {
    render(
      <ShareWithTeamDialog
        itemName="Award intake"
        teams={TEAMS}
        defaultTeamId="team-gone"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    )

    expect((screen.getByLabelText('Team') as HTMLSelectElement).value).toBe('team-a')
  })
})

it('keeps the note after failure and prevents duplicate submission or dismissal while pending', async () => {
  let reject!: (reason: Error) => void
  const submit = vi.fn(() => new Promise<void>((_resolve, fail) => { reject = fail }))
  const cancel = vi.fn()
  render(<ShareWithTeamDialog itemName="Research" teamName="Operations" onConfirm={submit} onCancel={cancel} />)
  fireEvent.change(screen.getByLabelText('Add a note (optional)'), { target: { value: 'Please review these sources.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Share with Operations' }))
  fireEvent.click(screen.getByRole('button', { name: 'Sharing…' }))
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(submit).toHaveBeenCalledTimes(1); expect(cancel).not.toHaveBeenCalled()
  reject(new Error('Sharing temporarily unavailable.'))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Sharing temporarily unavailable.'))
  expect(screen.getByLabelText('Add a note (optional)')).toHaveValue('Please review these sources.')
  fireEvent.click(screen.getByRole('button', { name: 'Share with Operations' }))
  expect(submit).toHaveBeenNthCalledWith(2, 'Please review these sources.', undefined)
})
