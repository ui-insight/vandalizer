import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { getUsageStats, getUsageTimeseries, type UsageStats } from '../../api/admin'
import { UsageTab } from './UsageTab'

vi.mock('../../api/admin', () => ({ getUsageStats: vi.fn(), getUsageTimeseries: vi.fn() }))
const stats = (conversations: number): UsageStats => ({ conversations, search_runs: 0, workflows_started: 0, workflows_completed: 0, workflows_failed: 0, tokens_in: 0, tokens_out: 0, active_users: 0, active_teams: 0 })
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getUsageTimeseries).mockResolvedValue({ days: [], previous_period: stats(0) })
})

it('labels retained values with their original range and blocks export after a failed range change', async () => {
  vi.mocked(getUsageStats).mockResolvedValueOnce(stats(321)).mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce(stats(72))
  render(<UsageTab />)
  await screen.findByText('321')
  fireEvent.click(screen.getByRole('button', { name: '7d' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('alert')).toHaveTextContent('last loaded 30-day window')
  expect(screen.getAllByText('in the last 30 days')).toHaveLength(2)
  expect(screen.getByRole('button', { name: /Export/ })).toBeDisabled()
  expect(screen.getByText('321')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
  await screen.findByText('72')
  expect(screen.getAllByText('in the last 7 days')).toHaveLength(2)
  expect(screen.getByRole('button', { name: /Export/ })).toBeEnabled()
})

it('ignores a slower previous range response after the new range is loaded', async () => {
  let finish!: (value: UsageStats) => void
  vi.mocked(getUsageStats).mockResolvedValueOnce(stats(321))
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    .mockResolvedValueOnce(stats(72))
  render(<UsageTab />)
  await screen.findByText('321')
  fireEvent.click(screen.getByRole('button', { name: '90d' }))
  await waitFor(() => expect(getUsageStats).toHaveBeenCalledWith(90))
  fireEvent.click(screen.getByRole('button', { name: '7d' }))
  await screen.findByText('72')
  await act(async () => { finish(stats(999)) })
  expect(screen.queryByText('999')).not.toBeInTheDocument()
  expect(screen.getByText('72')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Export/ })).toBeEnabled()
})
