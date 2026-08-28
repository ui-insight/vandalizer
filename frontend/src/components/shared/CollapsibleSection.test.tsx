import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CollapsibleSection } from './CollapsibleSection'

describe('CollapsibleSection', () => {
  it('starts open by default and folds on the header button', () => {
    render(
      <CollapsibleSection title="Input Configuration" summary="Manual (Select Documents)">
        <div>body content</div>
      </CollapsibleSection>,
    )
    const toggle = screen.getByRole('button', { name: /Input Configuration/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('body content')).toBeVisible()

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('body content')).not.toBeVisible()
    // The summary keeps saying what the folded section is set to.
    expect(screen.getByText('Manual (Select Documents)')).toBeVisible()

    fireEvent.click(toggle)
    expect(screen.getByText('body content')).toBeVisible()
  })

  it('can start collapsed and wires aria-controls to the body', () => {
    render(
      <CollapsibleSection title="Output Configuration" defaultOpen={false}>
        <div>output body</div>
      </CollapsibleSection>,
    )
    const toggle = screen.getByRole('button', { name: /Output Configuration/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('output body')).not.toBeVisible()
    const id = toggle.getAttribute('aria-controls')
    expect(id).toBeTruthy()
    expect(document.getElementById(id!)).toContainElement(screen.getByText('output body'))
  })

  it('supports controlled open state', () => {
    const onToggle = vi.fn()
    const { rerender } = render(
      <CollapsibleSection title="S" open={false} onToggle={onToggle}>
        <div>x</div>
      </CollapsibleSection>,
    )
    fireEvent.click(screen.getByRole('button', { name: /S/ }))
    expect(onToggle).toHaveBeenCalledWith(true)
    // Still closed until the parent flips it.
    expect(screen.getByText('x')).not.toBeVisible()
    rerender(
      <CollapsibleSection title="S" open onToggle={onToggle}>
        <div>x</div>
      </CollapsibleSection>,
    )
    expect(screen.getByText('x')).toBeVisible()
  })
})
