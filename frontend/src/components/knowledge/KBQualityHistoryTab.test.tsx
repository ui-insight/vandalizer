import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { KBQualityHistoryTab } from './KBQualityHistoryTab'

const getKBQuality = vi.fn().mockResolvedValue({ history: [] })

vi.mock('../../api/knowledge', () => ({
  getKBQuality: (uuid: string) => getKBQuality(uuid),
  downloadKBValidationRunExport: vi.fn(),
}))

// Support ticket: on a KB with no sources the History tab rendered the
// Validate pitch — a big "Validate & improve" button for a run that KB can't
// do — instead of saying there were no runs.
describe('KBQualityHistoryTab empty state', () => {
  it('states the absence, without the Validate pitch, for a KB with no sources', async () => {
    render(
      <KBQualityHistoryTab
        kbUuid="kb-1"
        kbHasSources={false}
        onSwitchToAutovalidate={vi.fn()}
      />,
    )

    await waitFor(() =>
      expect(screen.getByText(/No validation runs yet for this KB/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/Add at least one source/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Validate & improve/ })).not.toBeInTheDocument()
  })

  it('keeps the Validate & improve pitch for a KB that could be validated', async () => {
    render(
      <KBQualityHistoryTab
        kbUuid="kb-1"
        kbHasSources
        onSwitchToAutovalidate={vi.fn()}
      />,
    )

    await waitFor(() =>
      expect(screen.getByText(/No quality history yet for this KB/)).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: /Validate & improve/ })).toBeInTheDocument()
    expect(screen.queryByText(/No validation runs yet for this KB/)).not.toBeInTheDocument()
  })
})
