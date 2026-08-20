import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ContextLimitDialog } from './ContextLimitDialog'

// ---------------------------------------------------------------------------
// The dialog opens when a request won't fit. Truncate, Compact and Clear all
// solve that by throwing something away. Answering with a larger model solves
// it by not needing to — so it is offered first, and only when the server
// actually found one. A deployment with a single model has nothing to offer,
// and an invented choice that silently does nothing is worse than no choice.
// ---------------------------------------------------------------------------

const noop = () => Promise.resolve()

function renderDialog(props: Partial<React.ComponentProps<typeof ContextLimitDialog>> = {}) {
  return render(
    <ContextLimitDialog
      open
      onClose={() => {}}
      onTruncate={noop}
      onCompact={noop}
      onClear={noop}
      percent={98}
      suggestedModel={null}
      onUseModel={noop}
      {...props}
    />,
  )
}

describe('ContextLimitDialog — larger model option', () => {
  it('is absent when the server suggested nothing', () => {
    renderDialog({ suggestedModel: null })
    expect(screen.queryByRole('button', { name: /answer with/i })).toBeNull()
  })

  it('is absent when there is only one model configured', () => {
    // Same path as above from the UI's side: one model means the server has
    // nothing bigger to point at, so the field arrives null.
    renderDialog({ suggestedModel: null })
    expect(screen.getByRole('button', { name: /truncate/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /answer with/i })).toBeNull()
  })

  it('names the model it would switch to', () => {
    renderDialog({
      suggestedModel: { name: 'Qwen/Qwen3.5-9B', tag: 'Qwen-9b', context_window: 262144 },
    })
    expect(screen.getByRole('button', { name: /Qwen-9b/ })).toBeInTheDocument()
  })

  it('is offered before the options that discard content', () => {
    renderDialog({
      suggestedModel: { name: 'Qwen/Qwen3.5-9B', tag: 'Qwen-9b', context_window: 262144 },
    })
    const labels = screen.getAllByRole('button').map(b => b.textContent ?? '')
    const model = labels.findIndex(t => /answer with/i.test(t))
    const truncate = labels.findIndex(t => /truncate/i.test(t))
    expect(model).toBeGreaterThanOrEqual(0)
    expect(model).toBeLessThan(truncate)
  })

  it('hands the chosen model back to the caller', async () => {
    const onUseModel = vi.fn().mockResolvedValue(undefined)
    renderDialog({
      suggestedModel: { name: 'Qwen/Qwen3.5-9B', tag: 'Qwen-9b', context_window: 262144 },
      onUseModel,
    })
    fireEvent.click(screen.getByRole('button', { name: /Qwen-9b/ }))
    await waitFor(() => expect(onUseModel).toHaveBeenCalledWith('Qwen/Qwen3.5-9B'))
  })
})
