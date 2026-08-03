import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TagEditor } from './SupportCenter'

const mockListAllTags = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  Navigate: () => null,
  useNavigate: () => vi.fn(),
  useSearch: () => ({}),
}))

vi.mock('../api/support', () => ({
  listAllTags: () => mockListAllTags(),
}))

vi.mock('../hooks/useAuth', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../components/shared/useConfirm', () => ({ useConfirm: () => vi.fn() }))
vi.mock('../components/layout/PageLayout', () => ({
  PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('../api/feedback', () => ({
  listPositiveFeedback: vi.fn(),
  getPositiveFeedbackStats: vi.fn(),
}))

beforeEach(() => {
  mockListAllTags.mockReset()
  mockListAllTags.mockResolvedValue({ tags: ['Deploy', 'Billing', 'Onboarding'] })
})

const openEditor = async () => {
  fireEvent.click(screen.getByRole('button', { name: /add tag/i }))
  await screen.findByRole('option', { name: 'Billing' })
}

const input = () => screen.getByRole('combobox', { name: /add tag/i })

describe('TagEditor', () => {
  it('opens a dropdown of existing tags when Add tag is clicked', async () => {
    render(<TagEditor tags={[]} onChange={vi.fn()} />)
    await openEditor()
    expect(screen.getByRole('option', { name: 'Deploy' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Onboarding' })).toBeInTheDocument()
  })

  it('typing filters the list and picking an existing tag applies it', async () => {
    const onChange = vi.fn()
    render(<TagEditor tags={[]} onChange={onChange} />)
    await openEditor()
    fireEvent.change(input(), { target: { value: 'dep' } })
    expect(screen.queryByRole('option', { name: 'Billing' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('option', { name: 'Deploy' }))
    expect(onChange).toHaveBeenCalledWith(['Deploy'])
  })

  it('offers "Create new tag" when the text matches nothing, and creates it', async () => {
    const onChange = vi.fn()
    render(<TagEditor tags={[]} onChange={onChange} />)
    await openEditor()
    fireEvent.change(input(), { target: { value: 'urgent' } })
    const createOption = screen.getByRole('option', { name: /create new tag/i })
    expect(createOption).toHaveTextContent('urgent')
    fireEvent.click(createOption)
    expect(onChange).toHaveBeenCalledWith(['urgent'])
  })

  it('does not offer to create a tag that already exists (case-insensitive)', async () => {
    render(<TagEditor tags={[]} onChange={vi.fn()} />)
    await openEditor()
    fireEvent.change(input(), { target: { value: 'deploy' } })
    expect(screen.queryByRole('option', { name: /create new tag/i })).not.toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Deploy' })).toBeInTheDocument()
  })

  it('hides tags already on the ticket from the suggestion list', async () => {
    render(<TagEditor tags={['Deploy']} onChange={vi.fn()} />)
    await openEditor()
    expect(screen.queryByRole('option', { name: 'Deploy' })).not.toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Onboarding' })).toBeInTheDocument()
  })

  it('Enter applies the highlighted option after arrow-key navigation', async () => {
    const onChange = vi.fn()
    render(<TagEditor tags={[]} onChange={onChange} />)
    await openEditor()
    fireEvent.keyDown(input(), { key: 'ArrowDown' })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith(['Billing'])
  })
})
