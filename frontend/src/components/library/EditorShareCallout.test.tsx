import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EditorShareCallout } from './EditorShareCallout'

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))
vi.mock('./VerificationSubmitModal', () => ({
  VerificationSubmitModal: ({ itemKind, itemId }: { itemKind: string; itemId: string }) => (
    <div role="dialog">wizard {itemKind} {itemId}</div>
  ),
}))

function show(props: Partial<React.ComponentProps<typeof EditorShareCallout>> = {}) {
  return render(
    <EditorShareCallout itemKind="workflow" itemId="wf-1" itemTitle="Budget check" kindNoun="workflow" score={51} {...props} />,
  )
}

describe('EditorShareCallout', () => {
  it('offers sharing below 80% and opens the same wizard as the Library menu', () => {
    show({ score: 51 })
    expect(screen.getByText(/scored 51%/)).toBeTruthy()
    expect(screen.queryByText(/Great results/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Share with everyone' }))
    expect(screen.getByRole('dialog').textContent).toContain('wizard workflow wf-1')
  })

  it('offers sharing before any score exists', () => {
    show({ score: null, itemKind: 'search_set', kindNoun: 'extraction' })
    expect(screen.queryByText(/scored/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Share with everyone' })).toBeTruthy()
  })

  it('keeps the "Great results" framing at 80% and up, with the new wording', () => {
    show({ score: 86 })
    expect(screen.getByText(/Great results!/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Share with everyone' })).toBeTruthy()
    expect(screen.queryByText(/Public Library/i)).toBeNull()
  })

  it('hides once the item is verified, as the Library menu does', () => {
    const { container } = show({ verified: true })
    expect(container.textContent).toBe('')
  })
})
