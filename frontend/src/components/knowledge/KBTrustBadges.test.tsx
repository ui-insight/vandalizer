import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OptimizedBadge, VerifiedBadge, optimizedBadgeTitle, optimizationOf } from './KBTrustBadges'

describe('OptimizedBadge', () => {
  it('renders nothing when there is nothing to say', () => {
    const { container } = render(<OptimizedBadge kb={{}} />)
    expect(container.innerHTML).toBe('')
  })

  it('says the settings are applied, when, and that it is not Verified', () => {
    render(<OptimizedBadge kb={{ optimization: {
      state: 'applied', applied_at: '2026-08-01T12:00:00Z', stale: false, stale_reasons: [],
      tuned_keys: ['k', 'model'],
    } }} />)
    const el = screen.getByText('Optimized')
    const title = el.closest('span')!.getAttribute('title')!
    expect(title).toContain('APPLIED')
    expect(title).toContain('applied ' + new Date('2026-08-01T12:00:00Z').toLocaleDateString())
    expect(title).toContain('Tuned: k, model')
    expect(title).toContain('Not the same as Verified')
  })

  it('marks a stale optimization and repeats the reasons', () => {
    render(<OptimizedBadge kb={{ optimization: {
      state: 'stale', applied_at: '2026-08-01T12:00:00Z', stale: true,
      stale_reasons: ['Sources changed since the settings were tuned: 5 added (had 50 sources).'],
    } }} />)
    const el = screen.getByText('Optimized · stale')
    const title = el.closest('span')!.getAttribute('title')!
    expect(title).toContain('STALE: Sources changed since the settings were tuned: 5 added (had 50 sources).')
    expect(title).toContain('re-run Validate & improve')
  })

  it('offers an unapplied optimization only to someone who can apply it', () => {
    const opt = { state: 'available' as const, last_run_at: '2026-08-10T00:00:00Z', stale: false, stale_reasons: [] }
    const { container, unmount } = render(<OptimizedBadge kb={{ optimization: opt, can_manage: false }} />)
    expect(container.innerHTML).toBe('')
    unmount()
    render(<OptimizedBadge kb={{ optimization: opt, can_manage: true }} />)
    const title = screen.getByText('Optimization available').closest('span')!.getAttribute('title')!
    expect(title).toContain('not applied')
    expect(title).toContain('chat still uses the defaults')
  })

  it('falls back to the legacy has_optimized_config flag', () => {
    expect(optimizationOf({ has_optimized_config: true, optimized_config_set_at: '2026-01-01T00:00:00Z' })).toMatchObject({
      state: 'applied', applied_at: '2026-01-01T00:00:00Z',
    })
    render(<OptimizedBadge kb={{ has_optimized_config: true, optimized_config_set_at: null }} />)
    expect(screen.getByText('Optimized')).toBeTruthy()
  })

  it('mentions the most recent run when it is newer than the applied one', () => {
    const title = optimizedBadgeTitle({
      state: 'applied', applied_at: '2026-08-01T12:00:00Z', last_run_at: '2026-08-20T12:00:00Z',
      stale: false, stale_reasons: [],
    })
    expect(title).toContain('Most recent optimization run: ' + new Date('2026-08-20T12:00:00Z').toLocaleDateString())
  })
})

describe('VerifiedBadge', () => {
  it('explains that Verified is about content, not settings', () => {
    render(<VerifiedBadge />)
    const title = screen.getByText('Verified').closest('span')!.getAttribute('title')!
    expect(title).toContain('administrator published')
    expect(title).toContain('Not the same as Optimized')
  })
})
