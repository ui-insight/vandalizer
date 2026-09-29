import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WorkspaceTourProvider, useWorkspaceTour } from '../../contexts/WorkspaceTourContext'

function Launcher() {
  const open = useWorkspaceTour()
  return <button onClick={() => open?.()}>Take a quick tour</button>
}

describe('optional workspace tour', () => {
  it('opens only on request, supports all steps and returns focus after finishing', async () => {
    render(<WorkspaceTourProvider><Launcher /></WorkspaceTourProvider>)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const trigger = screen.getByRole('button', { name: 'Take a quick tour' })
    trigger.focus(); fireEvent.click(trigger)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Welcome to Vandalizer 5.0' })).toHaveFocus())
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('heading', { name: 'Start with your sources' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('heading', { name: 'Welcome to Vandalizer 5.0' })).toHaveFocus()
    for (let index = 0; index < 3; index++) fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByRole('button', { name: 'Get started' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('dismisses with Escape, never reopens on remount and allows a deliberate restart', async () => {
    const renderTour = () => <WorkspaceTourProvider><Launcher /></WorkspaceTourProvider>
    const view = render(renderTour())
    const trigger = screen.getByRole('button', { name: 'Take a quick tour' })
    trigger.focus(); fireEvent.click(trigger)
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    await waitFor(() => expect(trigger).toHaveFocus())
    view.unmount()
    render(renderTour())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Take a quick tour' }))
    expect(screen.getByRole('heading', { name: 'Welcome to Vandalizer 5.0' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Skip tour' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
