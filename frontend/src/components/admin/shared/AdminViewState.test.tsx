import { it, expect } from 'vitest'
import { render, fireEvent, screen } from '@testing-library/react'
import { AdminViewState, useAdminViewState } from './AdminViewState'
function Filter() {
  const [value, setValue] = useAdminViewState('search', '')
  return <input aria-label="Filter" value={value} onChange={e => setValue(e.target.value)} />
}
it('restores filters across section navigation and isolates administrative scopes', () => {
  const view = render(<AdminViewState key="a" scope="test-a"><Filter /></AdminViewState>)
  fireEvent.change(screen.getByLabelText('Filter'), { target: { value: 'Research' } })
  view.rerender(<AdminViewState key="a" scope="test-a"><p>Other section</p></AdminViewState>)
  view.rerender(<AdminViewState key="a" scope="test-a"><Filter /></AdminViewState>)
  expect(screen.getByLabelText('Filter')).toHaveValue('Research')
  view.rerender(<AdminViewState key="b" scope="test-b"><Filter /></AdminViewState>)
  expect(screen.getByLabelText('Filter')).toHaveValue('')
})
