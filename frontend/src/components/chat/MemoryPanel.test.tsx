import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryPanel } from './MemoryPanel'

const mocks = vi.hoisted(() => ({ getUserMemory: vi.fn(), setUserMemoryPaused: vi.fn(), clearUserMemory: vi.fn(), toast: vi.fn() }))
vi.mock('../../api/chat', () => ({
  getUserMemory: mocks.getUserMemory,
  setUserMemoryPaused: mocks.setUserMemoryPaused,
  clearUserMemory: mocks.clearUserMemory,
}))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: mocks.toast }) }))

const memory = (paused: boolean) => ({ extractions: [], workflows: [], kbs: [], paused })

beforeEach(() => { vi.clearAllMocks() })

describe('MemoryPanel on/off state (#1014 item 48)', () => {
  it('names the off state on the button without opening the panel', async () => {
    mocks.getUserMemory.mockResolvedValue(memory(true))
    render(<MemoryPanel />)
    expect(await screen.findByRole('button', { name: 'Assistant memory: off' })).toBeInTheDocument()
    expect(screen.getByText('Off')).toBeInTheDocument()
  })

  it('turns memory off from the switch and updates the button', async () => {
    mocks.getUserMemory.mockResolvedValue(memory(false))
    mocks.setUserMemoryPaused.mockResolvedValue({ paused: true })
    render(<MemoryPanel />)
    fireEvent.click(await screen.findByRole('button', { name: 'Assistant memory: on' }))
    const toggle = await screen.findByRole('switch', { name: 'Memory is on' })
    expect(toggle).toBeChecked()
    fireEvent.click(toggle)
    await waitFor(() => expect(mocks.setUserMemoryPaused).toHaveBeenCalledWith(true))
    expect(await screen.findByRole('switch', { name: 'Memory is off' })).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Assistant memory: off' })).toBeInTheDocument()
  })
})
