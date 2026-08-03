import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { EmailAnalyticsTab } from './EmailAnalyticsTab'
import type { EmailAnalyticsResponse } from '../../api/admin'

const mockGetEmailAnalytics = vi.fn()

vi.mock('../../api/admin', () => ({
  getEmailAnalytics: (...args: unknown[]) => mockGetEmailAnalytics(...args),
}))

const analytics: EmailAnalyticsResponse = {
  window_days: 30,
  total_sent: 240,
  total_failed: 6,
  success_rate: 0.975,
  by_day: [{ date: '2026-01-01', sent: 10, failed: 1 }],
  by_type: [{ email_type: 'digest', sent: 120, failed: 3, success_rate: 0.95 }],
  recent_failures: [
    { created_at: '2026-01-01T00:00:00Z', recipient: 'a@example.com', email_type: 'digest', provider: 'smtp', subject: 'Hi', error: 'bounced' },
  ],
  providers: ['smtp'],
}

beforeEach(() => {
  mockGetEmailAnalytics.mockReset()
})

describe('EmailAnalyticsTab — success', () => {
  it('renders analytics on success', async () => {
    mockGetEmailAnalytics.mockResolvedValue(analytics)
    render(<EmailAnalyticsTab />)
    await waitFor(() => expect(screen.getByText('97.5%')).toBeInTheDocument())
    expect(screen.getByText('240')).toBeInTheDocument()
    expect(screen.getByText('bounced')).toBeInTheDocument()
  })
})

describe('EmailAnalyticsTab — rejected load (regression for plan 005)', () => {
  it('renders an error message rather than a blank panel', async () => {
    mockGetEmailAnalytics.mockRejectedValue(new Error('network down'))
    const { container } = render(<EmailAnalyticsTab />)
    await waitFor(() => expect(screen.getByText('network down')).toBeInTheDocument())
    // Not a blank panel: the component's root element still renders content.
    expect(container).not.toBeEmptyDOMElement()
  })
})
