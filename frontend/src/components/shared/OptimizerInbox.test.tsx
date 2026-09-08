import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { OptimizerInbox } from './OptimizerInbox'
import {
  getOptimizerInbox,
  dismissOptimizerCandidate,
  type OptimizerInboxItem,
  type OptimizerInboxResponse,
} from '../../api/optimizerInbox'
import { applyWorkflowOptimization } from '../../api/workflows'

vi.mock('../../api/optimizerInbox', () => ({
  getOptimizerInbox: vi.fn(),
  dismissOptimizerCandidate: vi.fn(),
  restoreOptimizerCandidate: vi.fn(),
}))
vi.mock('../../api/workflows', () => ({ applyWorkflowOptimization: vi.fn() }))
vi.mock('../../api/knowledge', () => ({ applyKBOptimization: vi.fn() }))
vi.mock('../../api/extractions', () => ({ applyExtractionOptimization: vi.fn() }))

const mockToast = vi.fn()
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: mockToast }) }))
vi.mock('./useConfirm', () => ({ useConfirm: () => () => Promise.resolve(true) }))

const mockGet = vi.mocked(getOptimizerInbox)
const mockDismiss = vi.mocked(dismissOptimizerCandidate)
const mockApplyWorkflow = vi.mocked(applyWorkflowOptimization)

function makeItem(overrides: Partial<OptimizerInboxItem> = {}): OptimizerInboxItem {
  return {
    surface: 'workflow',
    run_uuid: 'run-1',
    item_id: 'wf-1',
    item_name: 'Proposal intake',
    status: 'completed',
    category: 'needs_review',
    started_at: '2026-07-20T12:00:00Z',
    completed_at: '2026-07-20T12:30:00Z',
    score: 0.85,
    baseline_score: 0.7,
    trigger: 'quality_alert',
    trigger_detail: {},
    tied_with_baseline: false,
    apply_preview: null,
    suggestion_count: 0,
    applied_at: null,
    reverted_at: null,
    is_live: false,
    can_manage: true,
    dismissed_at: null,
    error_message: null,
    error_code: null,
    error_context: null,
    stopped_reason: null,
    phase: null,
    progress_message: null,
    judge_model: 'judge-1',
    overfitting_warning: false,
    link: '/?workflow=wf-1',
    ...overrides,
  }
}

function makeResponse(items: OptimizerInboxItem[]): OptimizerInboxResponse {
  const count = (category: string) => items.filter(i => i.category === category).length
  return {
    items,
    counts: {
      total: items.length,
      needs_review: count('needs_review'),
      failed: count('failed'),
      in_flight: count('in_flight'),
      applied: count('applied'),
      no_change: count('no_change'),
      dismissed: count('dismissed'),
      pending_review: count('needs_review'),
    },
    lookback_days: 14,
  }
}

beforeEach(() => {
  mockGet.mockReset()
  mockDismiss.mockReset()
  mockApplyWorkflow.mockReset()
  mockToast.mockReset()
})

describe('OptimizerInbox', () => {
  it('shows a reviewable candidate with its item name and lift', async () => {
    mockGet.mockResolvedValue(makeResponse([makeItem()]))
    render(<OptimizerInbox />)

    expect(await screen.findByText('Proposal intake')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Ready to review/ })).toBeInTheDocument()
    expect(screen.getByText(/\+15\.0 pts/)).toBeInTheDocument()
    expect(screen.getByText(/Auto-tuned because a quality regression alert fired/)).toBeInTheDocument()
  })

  it('explains the empty state instead of rendering nothing', async () => {
    mockGet.mockResolvedValue(makeResponse([]))
    render(<OptimizerInbox />)

    expect(await screen.findByText('Nothing waiting for review')).toBeInTheDocument()
  })

  it('surfaces the error message of a failed tuning run', async () => {
    mockGet.mockResolvedValue(makeResponse([
      makeItem({
        category: 'failed', status: 'failed',
        error_code: 'judge_unavailable', error_message: 'Judge model unavailable',
        score: null,
      }),
    ]))
    render(<OptimizerInbox />)

    expect(await screen.findByText('Tuning failed')).toBeInTheDocument()
    expect(screen.getByText('Judge model unavailable')).toBeInTheDocument()
    expect(screen.getByText('judge unavailable')).toBeInTheDocument()
  })

  it('applies through the surface-specific endpoint and reloads', async () => {
    mockGet.mockResolvedValue(makeResponse([makeItem()]))
    mockApplyWorkflow.mockResolvedValue({
      ok: true,
      applied_config: { step_overrides: {} },
      applied_step_ids: [],
      partial: false,
    })
    render(<OptimizerInbox />)

    fireEvent.click(await screen.findByRole('button', { name: /Review & apply/i }))

    await waitFor(() => expect(mockApplyWorkflow).toHaveBeenCalledWith('wf-1', 'run-1'))
    expect(mockToast).toHaveBeenCalledWith('Applied to Proposal intake', 'success')
    // Refetched so the row moves out of "Ready to review".
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
  })

  it('dismisses a candidate', async () => {
    mockGet.mockResolvedValue(makeResponse([makeItem()]))
    mockDismiss.mockResolvedValue({ ok: true, dismissed_at: '2026-07-21T00:00:00Z' })
    render(<OptimizerInbox />)

    fireEvent.click(await screen.findByRole('button', { name: /Dismiss/i }))

    await waitFor(() => expect(mockDismiss).toHaveBeenCalledWith('workflow', 'run-1'))
  })

  it('hides Apply and Dismiss without manage rights', async () => {
    mockGet.mockResolvedValue(makeResponse([makeItem({ can_manage: false })]))
    render(<OptimizerInbox />)

    expect(await screen.findByText('Proposal intake')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Review & apply/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Dismiss/i })).not.toBeInTheDocument()
  })

  it('opens an item in a new tab so the worklist survives', async () => {
    mockGet.mockResolvedValue(makeResponse([makeItem()]))
    render(<OptimizerInbox />)

    const open = await screen.findByRole('link', { name: /Open/i })
    expect(open).toHaveAttribute('href', '/?workflow=wf-1')
    expect(open).toHaveAttribute('target', '_blank')
    expect(open).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('acknowledges a refresh that returns the same rows', async () => {
    mockGet.mockResolvedValue(makeResponse([makeItem()]))
    render(<OptimizerInbox />)

    await screen.findByText('Proposal intake')
    fireEvent.click(screen.getByRole('button', { name: /Refresh/i }))

    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
    // Identical data comes back — the confirmation is the only visible change.
    expect(await screen.findByText(/Updated just now/i)).toBeInTheDocument()
  })

  it('replaces the panel with the error when a refresh fails', async () => {
    mockGet.mockResolvedValueOnce(makeResponse([makeItem()]))
    render(<OptimizerInbox />)
    await screen.findByText('Proposal intake')

    mockGet.mockRejectedValueOnce(new Error('Backend unavailable'))
    fireEvent.click(screen.getByRole('button', { name: /Refresh/i }))

    // The error branch returns before the header, so the whole panel — rows,
    // Refresh, "Updated …" stamp — is replaced by the banner and its Retry.
    // This pins that early return, NOT the justRefreshed gate added in #791:
    // that gate has no observable effect precisely because of this branch, and
    // a test written against it passes with or without it.
    expect(await screen.findByText('Backend unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Refresh/i })).not.toBeInTheDocument()
    expect(screen.queryByText('Proposal intake')).not.toBeInTheDocument()
  })

  it('offers nothing to apply on a tied candidate', async () => {
    mockGet.mockResolvedValue(makeResponse([
      makeItem({ category: 'no_change', tied_with_baseline: true }),
    ]))
    render(<OptimizerInbox />)

    expect(await screen.findByText('No change recommended')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Review & apply/i })).not.toBeInTheDocument()
  })
})
