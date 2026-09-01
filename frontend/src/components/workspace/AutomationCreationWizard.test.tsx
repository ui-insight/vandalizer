import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { AutomationCreationWizard } from './AutomationCreationWizard'

vi.mock('focus-trap-react', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../../api/automations', () => ({
  createAutomation: vi.fn(),
  updateAutomation: vi.fn(),
}))
vi.mock('../../api/folders', () => ({ createFolder: vi.fn() }))
vi.mock('../../api/config', () => ({
  getFeatureFlags: vi.fn().mockResolvedValue({ m365_enabled: false }),
}))
vi.mock('../../api/client', () => ({
  apiFetch: vi.fn().mockResolvedValue([{ uuid: 'folder-1', path: '/Inbox' }]),
}))

beforeEach(() => vi.clearAllMocks())

describe('AutomationCreationWizard file type filter', () => {
  // One render for the whole assertion set — the wizard is a heavy tree and
  // each mount costs seconds under jsdom.
  it('offers exactly the uploadable types, preselecting the common ones', async () => {
    render(<AutomationCreationWizard onClose={vi.fn()} onCreate={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Name/i), { target: { value: 'Intake' } })
    fireEvent.click(screen.getByRole('button', { name: /Next/i }))
    // Step 2 keeps the default folder_watch trigger.
    fireEvent.click(screen.getByRole('button', { name: /Next/i }))
    await waitFor(() => expect(screen.getByText('File Types')).toBeInTheDocument())

    const chips = screen.getAllByRole('button').filter(el => el.hasAttribute('aria-pressed'))

    // The filter can only match what the uploader accepts: html is gone (no
    // upload can ever produce one), md is offered.
    expect(chips.map(el => el.textContent)).toEqual(
      ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt', '.md'],
    )
    expect(chips.filter(el => el.getAttribute('aria-pressed') === 'true').map(el => el.textContent))
      .toEqual(['.pdf', '.docx', '.xlsx'])
  }, 30000)
})
