import { StrictMode, useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PanelEditorSurface } from './PanelEditorSurface'

function Editors() {
  const [step, setStep] = useState(false)
  const [task, setTask] = useState(false)
  return <><button>Source document</button><div>
    <div data-testid="base"><button onClick={() => setStep(true)}>Open step</button></div>
    {step && <PanelEditorSurface label="Step" onClose={() => setStep(false)}>
      <button onClick={() => setTask(true)}>Open task</button>
    </PanelEditorSurface>}
    {task && <PanelEditorSurface label="Task" onClose={() => setTask(false)}><input aria-label="Task name" /></PanelEditorSurface>}
  </div></>
}

describe('pane editor focus', () => {
  it('hides covered controls, keeps sources available, and restores each nested opener', async () => {
    render(<StrictMode><Editors /></StrictMode>)
    const openStep = screen.getByRole('button', { name: 'Open step' })
    openStep.focus()
    fireEvent.click(openStep)
    const step = screen.getByRole('region', { name: 'Step' })
    expect(step).toHaveFocus()
    expect(screen.getByTestId('base').inert).toBe(true)
    const source = screen.getByRole('button', { name: 'Source document' })
    expect(source.closest('[inert]')).toBeNull()
    source.focus()
    expect(source).toHaveFocus()
    const openTask = screen.getByRole('button', { name: 'Open task' })
    openTask.focus()
    fireEvent.click(openTask)
    expect(screen.getByRole('region', { name: 'Task' })).toHaveFocus()
    expect(step.inert).toBe(true)
    fireEvent.keyDown(screen.getByRole('region', { name: 'Task' }), { key: 'Escape' })
    await waitFor(() => expect(openTask).toHaveFocus())
    expect(step.inert).not.toBe(true)
    expect(screen.getByTestId('base').inert).toBe(true)
    fireEvent.keyDown(step, { key: 'Escape' })
    await waitFor(() => expect(openStep).toHaveFocus())
    expect(screen.getByTestId('base').inert).not.toBe(true)
  })
})

describe('editors mounted in one render', () => {
  // Support ticket: after picking a task its details were frozen until a
  // browser refresh. Reloading the workflow re-mounted the step and task
  // editors together; the step editor made the task editor inert.
  function Reloaded({ loading }: { loading: boolean }) {
    if (loading) return <div>Loading workflow…</div>
    return <div>
      <div data-testid="base"><button>Run</button></div>
      <PanelEditorSurface label="Step" onClose={() => {}} layer={1000}><button>Add a task</button></PanelEditorSurface>
      <PanelEditorSurface label="Task" onClose={() => {}} layer={1002}><input aria-label="Prompt" /></PanelEditorSurface>
    </div>
  }

  it('never makes the editor on top inert', () => {
    const { rerender } = render(<StrictMode><Reloaded loading={false} /></StrictMode>)
    rerender(<StrictMode><Reloaded loading /></StrictMode>)
    rerender(<StrictMode><Reloaded loading={false} /></StrictMode>)
    const task = screen.getByRole('region', { name: 'Task' })
    expect(task.inert).not.toBe(true)
    expect(screen.getByLabelText('Prompt').closest('[inert]')).toBeNull()
    expect(screen.getByRole('region', { name: 'Step' }).inert).toBe(true)
    expect(screen.getByTestId('base').inert).toBe(true)
  })

  it('treats a later editor on the same layer as the one on top', () => {
    render(<div>
      <PanelEditorSurface label="First" onClose={() => {}}><button>A</button></PanelEditorSurface>
      <PanelEditorSurface label="Second" onClose={() => {}}><button>B</button></PanelEditorSurface>
    </div>)
    expect(screen.getByRole('region', { name: 'Second' }).inert).not.toBe(true)
    expect(screen.getByRole('region', { name: 'First' }).inert).toBe(true)
  })
})
