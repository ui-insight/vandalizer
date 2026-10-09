import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { HomeInboxSetting } from './HomeInboxSetting'

const api = vi.hoisted(() => ({ getInbox: vi.fn(), setInboxHidden: vi.fn() }))
vi.mock('../../api/obligations', () => api)

describe('Show the RA inbox on Home (#999)', () => {
  it('turns a hidden inbox back on', async () => {
    api.getInbox.mockResolvedValue({ items: [], inbox_hidden: true })
    api.setInboxHidden.mockResolvedValue({ inbox_hidden: false })
    render(<HomeInboxSetting />)
    const box = await screen.findByRole('checkbox', { name: /Show the RA inbox on Home/ })
    await waitFor(() => expect(box).not.toBeDisabled())
    expect(box).not.toBeChecked()
    fireEvent.click(box)
    await waitFor(() => expect(box).toBeChecked())
    expect(api.setInboxHidden).toHaveBeenCalledWith(false)
  })
})
