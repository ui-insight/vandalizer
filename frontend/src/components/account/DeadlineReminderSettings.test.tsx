import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DeadlineReminderSettings } from './DeadlineReminderSettings'
import type { ReminderSettings } from '../../api/obligations'

const api = vi.hoisted(() => ({ getReminderSettings: vi.fn(), updateReminderSettings: vi.fn() }))
vi.mock('../../api/obligations', () => api)

const DEFAULTS: ReminderSettings = {
  bell: true, email: false, days_before: [14, 3], on_due: true, overdue: true, weekly_summary: false, team_projects: false,
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getReminderSettings.mockResolvedValue({ settings: DEFAULTS, team_admin: false })
  api.updateReminderSettings.mockImplementation(async (changes: Partial<ReminderSettings>) => ({ settings: { ...DEFAULTS, ...changes }, team_admin: false }))
})

describe('Deadline reminder settings', () => {
  it('shows the saved timing and saves a changed reminder day', async () => {
    render(<DeadlineReminderSettings />)
    expect(await screen.findByRole('button', { name: '14 days before' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '7 days before' })).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(screen.getByRole('button', { name: '7 days before' }))
    await waitFor(() => expect(api.updateReminderSettings).toHaveBeenCalledWith({ days_before: [14, 7, 3] }))
    expect(await screen.findByRole('button', { name: '7 days before' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('turns email on and offers team projects only to team admins', async () => {
    const { unmount } = render(<DeadlineReminderSettings />)
    fireEvent.click(await screen.findByRole('checkbox', { name: /^Email/ }))
    await waitFor(() => expect(api.updateReminderSettings).toHaveBeenCalledWith({ email: true }))
    expect(screen.queryByRole('checkbox', { name: /teams' projects/ })).not.toBeInTheDocument()
    unmount()

    api.getReminderSettings.mockResolvedValue({ settings: DEFAULTS, team_admin: true })
    render(<DeadlineReminderSettings />)
    expect(await screen.findByRole('checkbox', { name: /teams' projects/ })).not.toBeChecked()
  })

  it('restores the saved settings when a change fails', async () => {
    api.updateReminderSettings.mockRejectedValue(new Error('Network down.'))
    render(<DeadlineReminderSettings />)
    fireEvent.click(await screen.findByRole('checkbox', { name: /Weekly summary/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Network down. Your saved settings were restored.')
    expect(screen.getByRole('checkbox', { name: /Weekly summary/ })).not.toBeChecked()
  })
})
