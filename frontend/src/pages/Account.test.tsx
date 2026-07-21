import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Account from './Account'

const mockUpdateProfile = vi.fn()
const mockGetApiTokenStatus = vi.fn()
const mockRefreshUser = vi.fn()

// Stable references: Account's mount effect depends on `user`, so a fresh
// object each render would re-run the effect and clobber typed input.
const mockUser = { user_id: 'testuser', email: 'old@example.com', name: 'Test User', is_admin: false }
const mockAuthValue = { user: mockUser, refreshUser: mockRefreshUser }

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => mockAuthValue,
}))

vi.mock('../components/shared/useConfirm', () => ({
  useConfirm: () => vi.fn().mockResolvedValue(true),
}))

vi.mock('../components/layout/PageLayout', () => ({
  PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../api/auth', () => ({
  updateProfile: (data: unknown) => mockUpdateProfile(data),
  generateApiToken: vi.fn(),
  revokeApiToken: vi.fn(),
  getApiTokenStatus: () => mockGetApiTokenStatus(),
}))

beforeEach(() => {
  mockUpdateProfile.mockReset()
  mockRefreshUser.mockReset()
  mockGetApiTokenStatus.mockReset()
  mockGetApiTokenStatus.mockResolvedValue({ has_token: false, created_at: null })
})

describe('Account — email change re-authentication', () => {
  it('hides the current-password field until the email is edited', () => {
    render(<Account />)
    expect(screen.queryByLabelText('Current Password')).not.toBeInTheDocument()
  })

  it('reveals the current-password field when the email changes', () => {
    render(<Account />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
    expect(screen.getByLabelText('Current Password')).toBeInTheDocument()
  })

  it('blocks saving an email change with no password and does not call the API', () => {
    render(<Account />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: /save profile/i }))
    expect(mockUpdateProfile).not.toHaveBeenCalled()
    expect(screen.getByText(/current password to change your email/i)).toBeInTheDocument()
  })

  it('sends current_password when the email is changed with a password', async () => {
    mockUpdateProfile.mockResolvedValueOnce({})
    render(<Account />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('Current Password'), { target: { value: 'hunter2' } })
    fireEvent.click(screen.getByRole('button', { name: /save profile/i }))
    await waitFor(() => expect(mockUpdateProfile).toHaveBeenCalledWith({
      name: 'Test User',
      email: 'new@example.com',
      current_password: 'hunter2',
    }))
  })

  it('does not require a password for a name-only change', async () => {
    mockUpdateProfile.mockResolvedValueOnce({})
    render(<Account />)
    fireEvent.change(screen.getByLabelText('Display Name'), { target: { value: 'Renamed' } })
    fireEvent.click(screen.getByRole('button', { name: /save profile/i }))
    await waitFor(() => expect(mockUpdateProfile).toHaveBeenCalledWith({
      name: 'Renamed',
      email: 'old@example.com',
    }))
    expect(screen.queryByLabelText('Current Password')).not.toBeInTheDocument()
  })

  it('surfaces the backend error message on a rejected email change', async () => {
    mockUpdateProfile.mockRejectedValueOnce(new Error('Incorrect password.'))
    render(<Account />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('Current Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /save profile/i }))
    await waitFor(() => expect(screen.getByText('Incorrect password.')).toBeInTheDocument())
  })
})
