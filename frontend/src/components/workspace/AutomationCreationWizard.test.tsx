import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { AutomationCreationWizard } from './AutomationCreationWizard'
import { createAutomation, updateAutomation } from '../../api/automations'

vi.mock('focus-trap-react', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../../api/automations', () => ({
  createAutomation: vi.fn(),
  updateAutomation: vi.fn(),
  previewSchedule: vi.fn().mockResolvedValue({
    cron_expression: '0 9 * * 1', timezone: 'UTC',
    next_runs: ['2026-09-28T09:00:00+00:00', '2026-10-05T09:00:00+00:00', '2026-10-12T09:00:00+00:00'],
  }),
}))
vi.mock('./ItemPickerModal', () => ({
  ItemPickerModal: ({ onSelect }: { onSelect: (id: string, name: string) => void }) => (
    <button type="button" onClick={() => onSelect('wf-1', 'Award review')}>pick workflow</button>
  ),
}))
vi.mock('../../api/folders', () => ({ createFolder: vi.fn() }))
vi.mock('../../api/config', () => ({
  getFeatureFlags: vi.fn().mockResolvedValue({ m365_enabled: false }),
}))
vi.mock('../../api/client', () => ({
  apiFetch: vi.fn().mockResolvedValue([{ uuid: 'folder-1', path: '/Inbox' }]),
}))

beforeEach(() => vi.clearAllMocks())

describe('AutomationCreationWizard draft safety', () => {
  it('advances text-field Enter once, preserves input and confirms draft dismissal', () => {
    const onClose = vi.fn()
    render(<AutomationCreationWizard onClose={onClose} onCreate={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Name/i), { target: { value: 'Proposal review' } })
    const description = screen.getByPlaceholderText('What does this automation do?')
    fireEvent.change(description, { target: { value: 'Review incoming proposals' } })
    fireEvent.keyDown(description, { key: 'Enter' })
    expect(screen.getByText(/Step 2 of/)).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByDisplayValue('Review incoming proposals')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Close$/ }))
    expect(screen.getByText('Discard this automation draft?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByDisplayValue('Proposal review')).toBeInTheDocument()
  })

  it('reuses the saved automation when activation fails, and supports saving disabled', async () => {
    vi.mocked(createAutomation).mockResolvedValue({ id: 'saved-draft' } as never)
    vi.mocked(updateAutomation).mockRejectedValueOnce(new Error('Connection interrupted')).mockResolvedValueOnce({} as never)
    const onCreate = vi.fn()
    render(<AutomationCreationWizard onClose={vi.fn()} onCreate={onCreate} />)
    fireEvent.change(screen.getByLabelText(/Name/i), { target: { value: 'API review' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByRole('radio', { name: /API Endpoint/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByRole('button', { name: /Select Workflow/ }))
    fireEvent.click(screen.getByRole('button', { name: 'pick workflow' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Review your automation')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Create & enable' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Retry to update the same automation'))
    fireEvent.click(screen.getByRole('button', { name: 'Save disabled' }))
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith('saved-draft'))
    expect(createAutomation).toHaveBeenCalledTimes(1)
    expect(updateAutomation).toHaveBeenLastCalledWith('saved-draft', expect.objectContaining({ enabled: false, action_id: 'wf-1' }))
  })
})

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

// Support ticket: Schedule as a third trigger, alongside Folder Watch and API.
describe('AutomationCreationWizard schedule trigger', () => {
  it('sets a schedule on a folder, shows the next run, and creates it', async () => {
    vi.mocked(createAutomation).mockResolvedValue({ id: 'auto-1' } as never)
    vi.mocked(updateAutomation).mockResolvedValue({} as never)
    const onCreate = vi.fn()
    render(<AutomationCreationWizard onClose={vi.fn()} onCreate={onCreate} />)
    fireEvent.change(screen.getByLabelText(/Name/i), { target: { value: 'Weekly awards' } })
    fireEvent.click(screen.getByRole('button', { name: /Next/i }))

    const triggers = screen.getAllByRole('radio').map(el => el.textContent)
    expect(triggers.map(t => t?.split('Trigger')[0].split('Run')[0])).toEqual(
      expect.arrayContaining(['Folder Watch', 'API Endpoint', 'Schedule']),
    )
    fireEvent.click(screen.getByRole('radio', { name: /Schedule/ }))
    fireEvent.click(screen.getByRole('button', { name: /Next/i }))

    // The schedule step: next run shown, and nothing to run on yet → can't advance.
    await waitFor(() => expect(screen.getByText(/Next run:/)).toBeInTheDocument())
    const next = screen.getByRole('button', { name: /Next/i })
    expect(next).toBeDisabled()

    await waitFor(() => expect(screen.getByRole('option', { name: '/Inbox' })).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Folder'), { target: { value: 'folder-1' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Only documents added since the last run/ }))
    expect(next).not.toBeDisabled()

    // Sections fold: the When section's fields hide, its summary stays.
    const when = screen.getByRole('button', { name: /^When/ })
    fireEvent.click(when)
    expect(when).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText(/Every Monday at 09:00/)).toBeInTheDocument()

    fireEvent.click(next)
    expect(screen.getByText('What should run on this schedule?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Select Workflow/i }))
    fireEvent.click(screen.getByRole('button', { name: 'pick workflow' }))
    fireEvent.click(screen.getByRole('button', { name: /Next/i }))
    fireEvent.click(screen.getByRole('button', { name: /Create & enable/i }))

    await waitFor(() => expect(onCreate).toHaveBeenCalledWith('auto-1'))
    const body = vi.mocked(createAutomation).mock.calls[0][0]
    expect(body.trigger_type).toBe('schedule')
    expect(body.action_id).toBe('wf-1')
    expect(body.trigger_config).toMatchObject({
      frequency: 'weekly', weekday: 0, time: '09:00', source: 'folder', folder_id: 'folder-1', only_new: true,
    })
  }, 30000)
})

describe('AutomationCreationWizard branch drafts and requirements', () => {
  it('retains folder filters across trigger changes but submits only the active API configuration', async () => {
    vi.mocked(createAutomation).mockResolvedValue({ id: 'api-draft' } as never)
    vi.mocked(updateAutomation).mockResolvedValue({} as never)
    render(<AutomationCreationWizard onClose={vi.fn()} onCreate={vi.fn()} />)
    expect(screen.getByLabelText(/Name/i)).toHaveAccessibleDescription(/Required/)
    fireEvent.change(screen.getByLabelText(/Name/i), { target: { value: 'Branch draft' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByRole('option', { name: '/Inbox' })
    fireEvent.change(screen.getByLabelText(/Watch Folder/), { target: { value: 'folder-1' } })
    fireEvent.change(screen.getByLabelText(/Exclude Patterns/), { target: { value: 'draft*' } })
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    fireEvent.click(screen.getByRole('radio', { name: /API Endpoint/ }))
    fireEvent.click(screen.getByRole('radio', { name: /Folder Watch/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByLabelText(/Watch Folder/)).toHaveValue('folder-1')
    expect(screen.getByLabelText(/Exclude Patterns/)).toHaveValue('draft*')
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    fireEvent.click(screen.getByRole('radio', { name: /API Endpoint/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('button', { name: /Select Workflow/ })).toHaveAccessibleDescription(/Required/)
    fireEvent.click(screen.getByRole('button', { name: /Select Workflow/ }))
    fireEvent.click(screen.getByRole('button', { name: 'pick workflow' }))
    // Clicking an already selected action type must not erase its selection.
    fireEvent.click(screen.getByRole('radio', { name: /Run Workflow/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Save results to a folder/ }))
    expect(screen.getByRole('button', { name: 'Save disabled' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Destination folder'), { target: { value: 'folder-1' } })
    expect(screen.getByLabelText('Output format')).toHaveValue('text')
    fireEvent.click(screen.getByRole('checkbox', { name: /Email results when complete/ }))
    fireEvent.change(screen.getByLabelText('Email recipients'), { target: { value: 'invalid' } })
    expect(screen.getByRole('button', { name: 'Save disabled' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Email recipients'), { target: { value: 'review@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save disabled' }))
    await waitFor(() => expect(createAutomation).toHaveBeenCalledWith(expect.objectContaining({
      trigger_type: 'api', trigger_config: undefined, action_id: 'wf-1',
      output_config: expect.objectContaining({ storage: { enabled: true, destination_folder: 'folder-1', format: 'text' } }),
    })))
  })
})
