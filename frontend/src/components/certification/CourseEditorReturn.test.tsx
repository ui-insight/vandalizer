import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CourseEditorReturn } from './CourseEditorReturn'
const state = vi.hoisted(() => ({ courseEditor: undefined as string | undefined, openPanel: vi.fn() }))
vi.mock('@tanstack/react-router', () => ({ useSearch: () => ({ courseEditor: state.courseEditor }) }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanel: () => ({ openPanel: state.openPanel }) }))
beforeEach(() => { vi.useFakeTimers(); state.courseEditor = '1'; state.openPanel.mockReset(); vi.spyOn(window, 'close').mockImplementation(() => {}) })
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })
it('does not offer to close ordinary workspace tabs', () => {
  state.courseEditor = undefined
  render(<CourseEditorReturn />)
  expect(screen.queryByRole('region')).not.toBeInTheDocument()
  expect(window.close).not.toHaveBeenCalled()
})
it('closes only on the explicit action and keeps a non-navigating fallback when the browser refuses', async () => {
  render(<CourseEditorReturn />)
  expect(window.close).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Close editor tab and return to course' }))
  expect(window.close).toHaveBeenCalledOnce()
  expect(screen.getByRole('button', { name: 'Closing editor tab…' })).toBeDisabled()
  await act(async () => vi.advanceTimersByTime(300))
  expect(screen.getByRole('status')).toHaveTextContent('this editor stays open')
  fireEvent.click(screen.getByRole('button', { name: 'Open learning panel here' }))
  expect(state.openPanel).toHaveBeenCalledOnce()
  expect(window.close).toHaveBeenCalledOnce()
})
