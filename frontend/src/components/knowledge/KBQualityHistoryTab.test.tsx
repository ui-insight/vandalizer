import { beforeEach, describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  beforeEach(() => { getKBQuality.mockResolvedValue({ history: [] }) })
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

describe('opening saved validation results', () => {
  it('opens the selected snapshot, while legacy and apply rows have no open action', async () => {
    const saved = { retrieval_precision: { details: [] }, judge_model: 'saved-grader', mode: 'judge' }
    getKBQuality.mockResolvedValue({ history: [
      { uuid: 'saved', created_at: '2026-09-01T12:00:00Z', result_snapshot: saved },
      { uuid: 'legacy', result_snapshot: null },
      { uuid: 'apply', source: 'optimizer_apply', result_snapshot: saved },
    ] })
    const onOpenRun = vi.fn()
    render(<KBQualityHistoryTab kbUuid="kb-1" onOpenRun={onOpenRun} />)
    const open = await screen.findAllByRole('button', { name: 'Open results' })
    expect(open).toHaveLength(1)
    fireEvent.click(open[0])
    expect(onOpenRun).toHaveBeenCalledWith('saved', saved, '2026-09-01T12:00:00Z')
  })
})
