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
