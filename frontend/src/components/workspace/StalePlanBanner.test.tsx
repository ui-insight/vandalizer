import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StalePlanBanner } from './StalePlanBanner'

const baseProps = {
  orphanedCount: 0,
  canManage: true,
  generating: false,
  confirming: false,
  onRegenerate: () => {},
  onConfirmFresh: () => {},
}

describe('StalePlanBanner', () => {
  it('explains definition drift when no checks are orphaned', () => {
    render(<StalePlanBanner {...baseProps} />)
    expect(screen.getByText('This plan may be out of sync with the workflow')).toBeTruthy()
    expect(screen.getByText(/The workflow was edited after this plan was created/)).toBeTruthy()
  })

  it('counts orphaned checks when present', () => {
    render(<StalePlanBanner {...baseProps} orphanedCount={3} />)
    expect(screen.getByText(/3 checks target a step that no longer exists/)).toBeTruthy()
  })

  it('uses singular phrasing for one orphaned check', () => {
    render(<StalePlanBanner {...baseProps} orphanedCount={1} />)
    expect(screen.getByText(/1 check targets a step that no longer exists/)).toBeTruthy()
  })

  it('shows action buttons for managers', () => {
    render(<StalePlanBanner {...baseProps} />)
    expect(screen.getByText('Regenerate plan')).toBeTruthy()
    expect(screen.getByText('Plan is still correct')).toBeTruthy()
  })

  it('hides action buttons for view-only users', () => {
    render(<StalePlanBanner {...baseProps} canManage={false} />)
    expect(screen.queryByText('Regenerate plan')).toBeNull()
    expect(screen.queryByText('Plan is still correct')).toBeNull()
    // The explanation is still visible.
    expect(screen.getByText('This plan may be out of sync with the workflow')).toBeTruthy()
  })

  it('fires callbacks on click', () => {
    const onRegenerate = vi.fn()
    const onConfirmFresh = vi.fn()
    render(<StalePlanBanner {...baseProps} onRegenerate={onRegenerate} onConfirmFresh={onConfirmFresh} />)
    fireEvent.click(screen.getByText('Regenerate plan'))
    fireEvent.click(screen.getByText('Plan is still correct'))
    expect(onRegenerate).toHaveBeenCalledOnce()
    expect(onConfirmFresh).toHaveBeenCalledOnce()
  })

  it('disables buttons while busy', () => {
    render(<StalePlanBanner {...baseProps} generating confirming />)
    expect((screen.getByText('Regenerate plan').closest('button') as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByText('Plan is still correct').closest('button') as HTMLButtonElement).disabled).toBe(true)
  })
})
