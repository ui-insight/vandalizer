import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { HomeQualityAlerts } from './HomeQualityAlerts'
import { getHomeAlertEvidence, reviewHomeAlert, type ActiveAlertItem } from '../../api/config'

vi.mock('../../api/config', () => ({ getHomeAlertEvidence: vi.fn(), reviewHomeAlert: vi.fn() }))
const alert: ActiveAlertItem = { uuid: 'alert-1', item_kind: 'search_set', item_id: 'set-1', item_name: 'test', severity: 'warning', alert_type: 'regression', message: 'Quality dropped by 10.0 points (95.0 -> 85.0)', previous_score: 95, current_score: 85, created_at: '2026-10-09T12:00:00Z', review_state: 'new' }
const props = () => ({ alerts: [alert], recentActivity: [], onOpenActivity: vi.fn(), onOpenTool: vi.fn(), onSendMessage: vi.fn() })
beforeEach(() => { vi.clearAllMocks(); vi.mocked(getHomeAlertEvidence).mockResolvedValue({ runs: [], linked_run: false }); vi.mocked(reviewHomeAlert).mockImplementation(async (_uuid, state) => ({ ...alert, review_state: state })) })
describe('home quality notices', () => {
  it('shows a duplicate once, uses points instead of accuracy, and does not call the model to view evidence', async () => {
    const actions = props()
    render(<HomeQualityAlerts {...actions} alerts={[alert, alert]} />)
    expect(screen.getAllByText('test')).toHaveLength(1)
    expect(screen.getByText('Evaluation score fell from 95 to 85')).toBeInTheDocument()
    expect(screen.queryByText(/85%/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View evaluation details' }))
    expect(await screen.findByText('No evaluation history is available for this tool.')).toBeInTheDocument()
    expect(getHomeAlertEvidence).toHaveBeenCalledWith('alert-1')
    expect(actions.onSendMessage).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Open extraction template' }))
    expect(actions.onOpenTool).toHaveBeenCalledWith(alert)
  })
  it('persists review/acknowledgement and explains that acknowledgement is not a fix', async () => {
    render(<HomeQualityAlerts {...props()} />)
    fireEvent.click(screen.getByRole('button', { name: 'View evaluation details' }))
    fireEvent.click(screen.getByRole('button', { name: 'Mark under review' }))
    await screen.findByText(/Extraction template · Warning · Under review/)
    expect(reviewHomeAlert).toHaveBeenCalledWith('alert-1', 'in_review')
    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge notice' }))
    await screen.findByText(/Extraction template · Warning · Acknowledged/)
    expect(screen.getByText(/It does not fix the tool or verify its results/)).toBeInTheDocument()
  })
  it('keeps an evidence failure distinct from an empty history and supports retry', async () => {
    vi.mocked(getHomeAlertEvidence).mockRejectedValueOnce(new Error('offline'))
    render(<HomeQualityAlerts {...props()} />)
    fireEvent.click(screen.getByRole('button', { name: 'View evaluation details' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Retry evaluation history' }))
    await screen.findByText('No evaluation history is available for this tool.')
    expect(getHomeAlertEvidence).toHaveBeenCalledTimes(2)
  })
  it('only links known uses by kind and id, without declaring them affected', async () => {
    render(<HomeQualityAlerts {...props()} recentActivity={[{ id: 'a', title: 'Actual use', item_kind: 'search_set', item_id: 'set-1' }, { id: 'b', title: 'Same name is not proof', item_kind: 'workflow', item_id: 'set-1' }]} />)
    fireEvent.click(screen.getByRole('button', { name: 'View evaluation details' }))
    await waitFor(() => expect(screen.queryByText('Loading evaluation history…')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Actual use' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Same name is not proof' })).not.toBeInTheDocument()
    expect(screen.getByText(/not confirmed affected/)).toBeInTheDocument()
  })
  it('does not offer unpersistable status actions on legacy notices', () => {
    render(<HomeQualityAlerts {...props()} alerts={[{ ...alert, uuid: undefined, created_at: null }]} />)
    fireEvent.click(screen.getByRole('button', { name: 'View evaluation details' }))
    expect(screen.getByText('Date not recorded')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Acknowledge notice' })).not.toBeInTheDocument()
    expect(getHomeAlertEvidence).not.toHaveBeenCalled()
  })
})
