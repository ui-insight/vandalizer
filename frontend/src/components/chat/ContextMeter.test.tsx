import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ContextMeter } from './ContextMeter'

// Phase 2 of the agentic-chat uplift: the meter renders the backend's
// warn/compact/block escalation state when provided, and falls back to the
// local ratio thresholds before the first context_meter chunk arrives.

const noop = vi.fn()

describe('ContextMeter', () => {
  it('renders nothing without tokens or a window', () => {
    const { container } = render(
      <ContextMeter tokensUsed={0} contextWindow={128000} onClick={noop} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('shows utilization percent of the window', () => {
    render(
      <ContextMeter tokensUsed={64000} contextWindow={128000} onClick={noop} />,
    )
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('backend warning state colors amber even at low utilization', () => {
    // 10% utilization would be gray by local thresholds — the backend state
    // must win (it knows the response reserve and real thresholds).
    render(
      <ContextMeter
        tokensUsed={12800}
        contextWindow={128000}
        state="warning"
        percentUntilCompact={22}
        onClick={noop}
      />,
    )
    const label = screen.getByText('10%')
    expect(label).toHaveStyle({ color: '#d97706' })
    expect(screen.getByRole('button').title).toContain(
      '22% until compaction is recommended',
    )
  })

  it('blocked state colors red and says context is full', () => {
    render(
      <ContextMeter
        tokensUsed={125000}
        contextWindow={128000}
        state="blocked"
        percentUntilCompact={0}
        onClick={noop}
      />,
    )
    expect(screen.getByText('98%')).toHaveStyle({ color: '#ef4444' })
    expect(screen.getByRole('button').title).toContain('context full')
  })

  it('falls back to local ratio thresholds without a backend state', () => {
    render(
      <ContextMeter tokensUsed={120000} contextWindow={128000} onClick={noop} />,
    )
    // 94% of window → red under the legacy >=90% rule.
    expect(screen.getByText('94%')).toHaveStyle({ color: '#ef4444' })
  })
})
