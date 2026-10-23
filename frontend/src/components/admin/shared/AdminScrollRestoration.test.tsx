import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { AdminScrollRestoration, restoreAdminScroll } from './AdminScrollRestoration'
import { AdminViewState } from './AdminViewState'
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
function geometry(container: HTMLElement, height: number) {
  Object.defineProperty(container, 'scrollHeight', { configurable: true, value: height })
  Object.defineProperty(container, 'clientHeight', { configurable: true, value: 100 })
}
it('waits for async content and stops observing once the saved position is reachable', async () => {
  const container = document.createElement('div'), content = document.createElement('div')
  container.append(content); geometry(container, 100)
  const restoration = restoreAdminScroll(container, content, 500)
  expect(restoration.pending()).toBe(true)
  geometry(container, 1000)
  await act(async () => { content.append(document.createElement('p')) })
  expect(container.scrollTop).toBe(500)
  expect(restoration.pending()).toBe(false)
  container.scrollTop = 30
  await act(async () => { content.append(document.createElement('p')) })
  expect(container.scrollTop).toBe(30)
})
it.each(['wheel', 'touchstart', 'pointerdown', 'keydown'])('does not jump after deliberate %s input during loading', async event => {
  const container = document.createElement('div'), content = document.createElement('div')
  container.append(content); geometry(container, 100)
  const restoration = restoreAdminScroll(container, content, 500)
  container.dispatchEvent(new Event(event))
  geometry(container, 1000)
  await act(async () => { content.append(document.createElement('p')) })
  expect(container.scrollTop).toBe(0)
  expect(restoration.pending()).toBe(false)
})
it('restores each section independently after unmount and isolates user scopes', () => {
  const shell = (section: string, scope = 'scroll-test-user') => <div data-testid="scroll"><main><AdminViewState key={scope} scope={scope}><AdminScrollRestoration key={section} section={section}><p>{section}</p></AdminScrollRestoration></AdminViewState></main></div>
  const view = render(shell('users'))
  const container = screen.getByTestId('scroll'); geometry(container, 1000)
  container.scrollTop = 500; fireEvent.scroll(container)
  view.rerender(shell('teams'))
  expect(container.scrollTop).toBe(0)
  container.scrollTop = 200; fireEvent.scroll(container)
  view.rerender(shell('users'))
  expect(container.scrollTop).toBe(500)
  view.rerender(shell('users', 'other-scroll-user'))
  expect(container.scrollTop).toBe(0)
})
