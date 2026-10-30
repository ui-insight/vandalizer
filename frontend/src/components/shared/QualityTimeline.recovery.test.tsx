import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QualityTimeline, type QualityHistoryItem } from './QualityTimeline'

const labels = { itemKindLabel: 'KB', itemKindPluralLabel: 'KBs', sampleNoun: 'questions' }
const rows: QualityHistoryItem[] = Array.from({ length: 30 }, (_, i) => ({
  uuid: `run-${i}`, score: i === 29 ? undefined : 80, created_at: `2026-09-${String(30-i).padStart(2, '0')}T12:00:00Z`,
  judge_model: 'evaluation-model', mode: 'judge', num_test_queries: 3,
  question_set: { fingerprint: i === 0 ? 'changed-set' : 'original-set' },
}))

describe('quality history recovery and run identity', () => {
  it('distinguishes failed loading from an empty history and retries', async () => {
    const fetchHistory = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ history: rows })
    render(<QualityTimeline {...labels} fetchHistory={fetchHistory} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('History could not load')
    expect(screen.queryByText(/No quality history/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry history' }))
    expect(await screen.findAllByRole('article')).toHaveLength(30)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps loaded rows on refresh failure and can recover them', async () => {
    const fetchHistory = vi.fn().mockResolvedValueOnce({ history: rows }).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ history: rows.slice(0, 1) })
    const { rerender } = render(<QualityTimeline {...labels} fetchHistory={fetchHistory} refreshKey={0} />)
    await screen.findAllByRole('article')
    rerender(<QualityTimeline {...labels} fetchHistory={fetchHistory} refreshKey={1} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Previously loaded runs are still shown')
    expect(screen.getAllByRole('article')).toHaveLength(30)
    fireEvent.click(screen.getByRole('button', { name: 'Retry history' }))
    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(1))
  })

  it('opens and exports the intended older run, surfaces export failure, and prevents duplicate requests', async () => {
    const onOpenRun = vi.fn()
    let resolveDownload!: () => void
    const onExportRun = vi.fn().mockRejectedValueOnce(new Error('offline')).mockImplementationOnce(() => new Promise<void>(resolve => { resolveDownload = resolve }))
    render(<QualityTimeline {...labels} fetchHistory={async () => ({ history: rows })} onOpenRun={onOpenRun} canOpenRun={() => true} onExportRun={onExportRun} />)
    const articles = await screen.findAllByRole('article')
    const old = within(articles[29])
    expect(old.getByText('Score unavailable')).toBeInTheDocument()
    fireEvent.click(old.getByRole('button', { name: 'Open results' }))
    expect(onOpenRun).toHaveBeenCalledWith(rows[29])
    fireEvent.click(old.getByRole('button', { name: 'Export run results' }))
    fireEvent.click(old.getByRole('button', { name: 'CSV' }))
    expect(await old.findByRole('alert')).toHaveTextContent('Choose a format to retry')
    expect(onExportRun).toHaveBeenNthCalledWith(1, 'run-29', 'csv')
    fireEvent.click(old.getByRole('button', { name: 'JSON' }))
    expect(old.getByRole('status')).toHaveTextContent('Preparing download')
    expect(old.getByRole('button', { name: 'Export run results' })).toBeDisabled()
    expect(onExportRun).toHaveBeenCalledTimes(2)
    resolveDownload()
    await waitFor(() => expect(old.queryByRole('status')).not.toBeInTheDocument())
    expect(onExportRun).toHaveBeenNthCalledWith(2, 'run-29', 'json')
  })
})
