import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  TrendDelta, SortableHeader, StatusBadge, RoleBadge, UserAvatar,
} from './primitives'

describe('TrendDelta', () => {
  it('renders nothing when both current and previous are 0', () => {
    const { container } = render(<TrendDelta current={0} previous={0} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('reports +100% when previous is 0 and current is positive', () => {
    render(<TrendDelta current={5} previous={0} />)
    expect(screen.getByText('+100%')).toBeInTheDocument()
  })

  it('renders an increase as "good" (green) by default', () => {
    render(<TrendDelta current={20} previous={10} />)
    const el = screen.getByText('+100%')
    expect(el.style.color).toBe('rgb(22, 163, 74)')
  })

  it('invert flips an increase to "bad" (red) styling', () => {
    render(<TrendDelta current={20} previous={10} invert />)
    const el = screen.getByText('+100%')
    expect(el.style.color).toBe('rgb(220, 38, 38)')
  })

  it('invert flips a decrease to "good" (green) styling', () => {
    render(<TrendDelta current={5} previous={10} invert />)
    const el = screen.getByText('-50%')
    expect(el.style.color).toBe('rgb(22, 163, 74)')
  })
})

function renderHeader(sortKey: string, currentSort: { key: string; dir: 'asc' | 'desc' }) {
  return render(
    <table>
      <thead>
        <tr>
          <SortableHeader label="Name" sortKey={sortKey} currentSort={currentSort} onSort={() => {}} />
        </tr>
      </thead>
    </table>,
  )
}

describe('SortableHeader', () => {
  it('sets aria-sort="ascending" when this column is the active ascending sort', () => {
    renderHeader('name', { key: 'name', dir: 'asc' })
    expect(screen.getByRole('columnheader')).toHaveAttribute('aria-sort', 'ascending')
  })

  it('sets aria-sort="descending" when this column is the active descending sort', () => {
    renderHeader('name', { key: 'name', dir: 'desc' })
    expect(screen.getByRole('columnheader')).toHaveAttribute('aria-sort', 'descending')
  })

  it('sets aria-sort="none" when a different column is active', () => {
    renderHeader('name', { key: 'other', dir: 'asc' })
    expect(screen.getByRole('columnheader')).toHaveAttribute('aria-sort', 'none')
  })
})

describe('StatusBadge', () => {
  it('renders the status label for a known status', () => {
    render(<StatusBadge status="completed" />)
    expect(screen.getByText('completed')).toBeInTheDocument()
  })

  it('renders the raw status label for an unrecognized status (falls back to default styling)', () => {
    render(<StatusBadge status="mystery-status" />)
    expect(screen.getByText('mystery-status')).toBeInTheDocument()
  })
})

describe('RoleBadge', () => {
  it('renders the role label for a known role', () => {
    render(<RoleBadge role="admin" />)
    expect(screen.getByText('admin')).toBeInTheDocument()
  })

  it('renders the raw role label for an unrecognized role', () => {
    render(<RoleBadge role="nobody" />)
    expect(screen.getByText('nobody')).toBeInTheDocument()
  })
})

describe('UserAvatar', () => {
  it('falls back to "?" when name is null', () => {
    render(<UserAvatar name={null} />)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('falls back to "?" when name is an empty string', () => {
    render(<UserAvatar name="" />)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('renders the uppercased first letter of a real name', () => {
    render(<UserAvatar name="zach" />)
    expect(screen.getByText('Z')).toBeInTheDocument()
  })
})
