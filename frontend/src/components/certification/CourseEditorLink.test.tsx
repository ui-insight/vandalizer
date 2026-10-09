import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { CourseEditorLink } from './CourseEditorLink'

it.each(['extraction', 'workflow'] as const)('opens only the exact selected %s in a separate tab', kind => {
  const artifactId = 'original&workflow=other/#雪'
  render(<CourseEditorLink kind={kind} artifactId={artifactId} title="My original work" />)
  const link = screen.getByRole('link', { name: `Open selected ${kind} in a new tab` })
  const url = new URL(link.getAttribute('href')!, 'https://local.invalid')
  expect(url.origin).toBe('https://local.invalid')
  expect(url.pathname).toBe('/')
  expect([...url.searchParams]).toEqual([['mode', 'files'], ['tab', 'library'], [kind, artifactId], ['courseEditor', '1']])
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  expect(link).toHaveAccessibleDescription(/This course tab stays open.*does not replace evidence already saved/)
})

it('offers no navigation while the original capture is unresolved', () => {
  render(<CourseEditorLink kind="workflow" artifactId="original" title="Original workflow" disabled />)
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Open selected workflow in a new tab' })).toBeDisabled()
})

it.each(['click', 'auxclick'])('focuses the activated link on %s without stealing later focus', activation => {
  render(<><CourseEditorLink kind="workflow" artifactId="original" title="Original" /><input aria-label="Another draft" /></>)
  const link = screen.getByRole('link'), input = screen.getByRole('textbox')
  input.focus()
  if (activation === 'click') fireEvent.click(link)
  else fireEvent(link, new MouseEvent('auxclick', { bubbles: true, button: 1 }))
  expect(link).toHaveFocus()
  input.focus()
  window.dispatchEvent(new Event('focus'))
  expect(input).toHaveFocus()
})
