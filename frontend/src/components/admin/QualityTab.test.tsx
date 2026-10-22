import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QualityTab } from './QualityTab'
import * as api from '../../api/admin'
import { getModels } from '../../api/config'

vi.mock('../../api/admin', () => ({
  getQualitySummary: vi.fn(), getQualityTimeline: vi.fn(), getQualityAlerts: vi.fn(),
  getQualityItems: vi.fn(), getQualityItemDetail: vi.fn(), getJudgeCalibration: vi.fn(),
  getRegressionSuiteRuns: vi.fn(), getQualityByModel: vi.fn(), getRegressionSuiteRun: vi.fn(),
  runRegressionSuite: vi.fn(), acknowledgeAlert: vi.fn(),
}))
vi.mock('../../api/config', () => ({ getModels: vi.fn().mockResolvedValue([]) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('recharts', () => ({
  ResponsiveContainer: () => null, CartesianGrid: () => null, Line: () => null,
  LineChart: () => null, Tooltip: () => null, XAxis: () => null, YAxis: () => null,
}))
const item = (id: string) => ({ item_id: id, display_name: id, item_kind: 'workflow', quality_score: 80, quality_tier: 'good', last_validated_at: null, validation_run_count: 3, trend: 'flat' as const, stale: false })
const detail = (id: string) => ({ item_kind: 'workflow', item_id: id, history: [], model_comparison: [{ model: id, avg_score: 80, run_count: 3 }] })
const suite = { run_uuid: 'accepted-run', status: 'completed' as const, model: 'test', total_items: 1, completed_items: 1, succeeded: 1, failed: 0, mean_score: 80, error: null, started_at: null, finished_at: null, results: [] }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getModels).mockResolvedValue([])
  vi.mocked(api.getQualitySummary).mockResolvedValue({ avg_score: 80, total_runs: 3, items_validated: 2, total_verified: 2, items_below_threshold: 0 })
  vi.mocked(api.getQualityTimeline).mockResolvedValue({ timeline: [] })
  vi.mocked(api.getQualityAlerts).mockResolvedValue({ alerts: [] })
  vi.mocked(api.getQualityItems).mockResolvedValue({ items: [item('first'), item('second')] })
  vi.mocked(api.getJudgeCalibration).mockResolvedValue({ surfaces: [], available_models: [] })
  vi.mocked(api.getRegressionSuiteRuns).mockResolvedValue({ runs: [] })
  vi.mocked(api.getQualityByModel).mockResolvedValue({ models: [] })
})
describe('Quality recovery', () => {
  it('retries the accepted regression run after a failed status read without starting another', async () => {
    vi.mocked(api.runRegressionSuite).mockResolvedValue({ run_uuid: suite.run_uuid, status: 'running' })
    vi.mocked(api.getRegressionSuiteRun).mockRejectedValueOnce(new Error('Status unavailable')).mockResolvedValue(suite)
    render(<QualityTab />)
    fireEvent.click(await screen.findByRole('button', { name: 'Run Regression Suite' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Retry run status' }))
    await screen.findByText('Catalog mean:')
    expect(api.runRegressionSuite).toHaveBeenCalledTimes(1)
    expect(api.getRegressionSuiteRun).toHaveBeenCalledTimes(2)
    expect(api.getRegressionSuiteRun).toHaveBeenLastCalledWith('accepted-run')
  })
  it('does not replace the selected item with an earlier slow detail response', async () => {
    let resolveFirst!: (value: ReturnType<typeof detail>) => void
    vi.mocked(api.getQualityItemDetail).mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve })).mockResolvedValueOnce(detail('current-model'))
    render(<QualityTab />)
    fireEvent.click(await screen.findByRole('button', { name: 'View quality for first' }))
    await waitFor(() => expect(api.getQualityItemDetail).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'View quality for second' }))
    await screen.findByText('current-model')
    await act(async () => resolveFirst(detail('obsolete-model')))
    expect(screen.queryByText('obsolete-model')).not.toBeInTheDocument()
    expect(screen.getByText('current-model')).toBeInTheDocument()
  })
  it('shows an item read failure and retries the same item', async () => {
    vi.mocked(api.getQualityItemDetail).mockRejectedValueOnce(new Error('Detail unavailable')).mockResolvedValue(detail('retried-model'))
    render(<QualityTab />)
    fireEvent.click(await screen.findByRole('button', { name: 'View quality for first' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Retry item quality' }))
    await screen.findByText('retried-model')
    expect(api.getQualityItemDetail).toHaveBeenLastCalledWith('workflow', 'first')
  })
})
