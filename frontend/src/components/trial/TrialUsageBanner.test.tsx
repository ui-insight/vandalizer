import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { TrialUsageBanner } from './TrialUsageBanner'
import { TrialTopUpDialog } from './TrialTopUpDialog'
import type { InAppTopUpInfo, TrialUsage } from '../../types/demo'

// Support ticket: a trial learner ran out of AI tokens in certification
// Module 1 with no warning, and the only way back was an emailed link their
// address couldn't receive.
const api = vi.hoisted(() => ({
  getTrialUsage: vi.fn(),
  getInAppTopUp: vi.fn(),
  requestInAppTopUp: vi.fn(),
}))
vi.mock('../../api/demo', () => api)
let user: { is_demo_user: boolean } | null = { is_demo_user: true }
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user }) }))

const usage = (percent: number, changes: Partial<TrialUsage> = {}): TrialUsage => ({
  enabled: true, budget: 2_000_000, used: percent * 20_000, remaining: Math.max(0, 2_000_000 - percent * 20_000), percent, email_verified: true, ...changes,
})
const topUpInfo = (changes: Partial<InAppTopUpInfo> = {}): InAppTopUpInfo => ({
  available: true, reason: null, engagement: 'low', tokens_used: 2_000_000, tokens_budget: 2_000_000, percent: 100, topup_tokens: 2_000_000, ...changes,
})

beforeEach(() => {
  vi.clearAllMocks()
  user = { is_demo_user: true }
})

describe('trial usage banner', () => {
  it('warns at 80% and says certification does not count', async () => {
    api.getTrialUsage.mockResolvedValue(usage(85))
    render(<TrialUsageBanner />)
    expect(await screen.findByText(/used 85% of your trial AI tokens/)).toBeInTheDocument()
    expect(screen.getByText(/Certification work in chat doesn't count/)).toBeInTheDocument()
  })

  it('says when the tokens are gone, and that work stays open', async () => {
    api.getTrialUsage.mockResolvedValue(usage(100))
    render(<TrialUsageBanner />)
    expect(await screen.findByText(/used all of your trial AI tokens/)).toBeInTheDocument()
  })

  it.each([
    ['below the warning line', usage(50)],
    ['an unconfirmed address (the verify banner speaks then)', usage(95, { email_verified: false })],
    ['no per-account allowance', usage(0, { enabled: false })],
  ])('stays hidden for %s', async (_, value) => {
    api.getTrialUsage.mockResolvedValue(value)
    render(<TrialUsageBanner />)
    await waitFor(() => expect(api.getTrialUsage).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Top up' })).toBeNull()
  })

  it('never asks for a non-trial account', () => {
    user = { is_demo_user: false }
    render(<TrialUsageBanner />)
    expect(api.getTrialUsage).not.toHaveBeenCalled()
  })

  it('tops up in the app and refreshes the meter', async () => {
    api.getTrialUsage.mockResolvedValueOnce(usage(100)).mockResolvedValue(usage(50))
    api.getInAppTopUp.mockResolvedValue(topUpInfo())
    api.requestInAppTopUp.mockResolvedValue({ ok: true, message: 'ok' })
    render(<TrialUsageBanner />)
    fireEvent.click(await screen.findByRole('button', { name: 'Top up' }))
    fireEvent.click(await screen.findByRole('button', { name: /Add 2M tokens|Add 2,000,000 tokens|Add .* tokens/ }))
    await waitFor(() => expect(api.requestInAppTopUp).toHaveBeenCalledWith(undefined))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Top up' })).toBeNull())
  })
})

describe('in-app top-up dialog', () => {
  it('tells the user why a top-up is not open yet', async () => {
    api.getInAppTopUp.mockResolvedValue(topUpInfo({ available: false, reason: 'no_application' }))
    render(<TrialTopUpDialog open onClose={vi.fn()} />)
    expect(await screen.findByText(/Ask your administrator to add tokens/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Add .* tokens/ })).toBeNull()
  })

  it('asks an engaged user for notes before adding tokens', async () => {
    api.getInAppTopUp.mockResolvedValue(topUpInfo({ engagement: 'engaged' }))
    render(<TrialTopUpDialog open onClose={vi.fn()} />)
    expect(await screen.findByText('What are you using Vandalizer for?', { exact: false })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Add .* tokens/ })).toBeNull()
  })

  it('reports back after tokens were added, so chat can retry', async () => {
    api.getInAppTopUp.mockResolvedValue(topUpInfo())
    api.requestInAppTopUp.mockResolvedValue({ ok: true, message: 'ok' })
    const onToppedUp = vi.fn()
    const onClose = vi.fn()
    render(<TrialTopUpDialog open onClose={onClose} onToppedUp={onToppedUp} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add .* tokens/ }))
    await waitFor(() => expect(onToppedUp).toHaveBeenCalledTimes(1))
    expect(onClose).toHaveBeenCalled()
  })

  it('keeps the dialog open with the reason when the top-up is refused', async () => {
    api.getInAppTopUp.mockResolvedValue(topUpInfo())
    api.requestInAppTopUp.mockRejectedValue(new Error("You can top up once you've used most of your current tokens."))
    const onToppedUp = vi.fn()
    render(<TrialTopUpDialog open onClose={vi.fn()} onToppedUp={onToppedUp} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add .* tokens/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('used most of your current tokens')
    expect(onToppedUp).not.toHaveBeenCalled()
  })
})
