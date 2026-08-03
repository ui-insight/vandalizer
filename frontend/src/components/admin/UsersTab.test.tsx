import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { UsersTab } from './UsersTab'
import type { UserDetailResponse, UserLeaderboardItem } from '../../api/admin'

const mockGetUserLeaderboard = vi.fn()
const mockGetUserDetail = vi.fn()
const mockGetUserHistory = vi.fn()
const mockUpdateUserRoles = vi.fn()
const mockConfirm = vi.fn()
const mockToast = vi.fn()

const leaderboardItem: UserLeaderboardItem = {
  user_id: 'target-1',
  name: 'Target User',
  email: 'target@example.com',
  is_admin: false,
  is_staff: false,
  is_examiner: false,
  tokens_total: 100,
  workflows_run: 2,
  conversations: 3,
  last_active: null,
}

const userDetail: UserDetailResponse = {
  user_id: 'target-1',
  name: 'Target User',
  email: 'target@example.com',
  is_admin: false,
  is_staff: false,
  is_examiner: false,
  tokens_in: 10,
  tokens_out: 20,
  workflows_started: 1,
  workflows_completed: 1,
  workflows_failed: 0,
  conversations: 3,
  document_count: 0,
  timeseries: [],
  previous_period: {
    conversations: 0, search_runs: 0, workflows_started: 0, workflows_completed: 0,
    workflows_failed: 0, tokens_in: 0, tokens_out: 0, active_users: 0, active_teams: 0,
  },
  recent_workflows: [],
}

vi.mock('../../api/admin', () => ({
  getUserLeaderboard: (...args: unknown[]) => mockGetUserLeaderboard(...args),
  getUserDetail: (...args: unknown[]) => mockGetUserDetail(...args),
  getUserHistory: (...args: unknown[]) => mockGetUserHistory(...args),
  updateUserRoles: (...args: unknown[]) => mockUpdateUserRoles(...args),
}))

vi.mock('../../api/audit', () => ({
  exportAuditLog: () => '#',
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ user: { user_id: 'admin-1', is_admin: true, is_staff: false, is_examiner: false } }),
}))

vi.mock('../shared/useConfirm', () => ({
  useConfirm: () => mockConfirm,
}))

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: mockToast }),
}))

beforeEach(() => {
  mockGetUserLeaderboard.mockReset().mockResolvedValue({ items: [leaderboardItem], total: 1, capped: false })
  mockGetUserDetail.mockReset().mockResolvedValue(userDetail)
  mockGetUserHistory.mockReset().mockResolvedValue({ items: [], total: 0, capped: false })
  mockUpdateUserRoles.mockReset()
  mockConfirm.mockReset()
  mockToast.mockReset()
})

async function openDrillDown() {
  render(<UsersTab />)
  await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: /view target-1/i }))
  await waitFor(() => expect(screen.getByText('Platform Roles')).toBeInTheDocument())
}

describe('UsersTab — platform role toggle', () => {
  it('does not call updateUserRoles when the confirmation is declined', async () => {
    mockConfirm.mockResolvedValue(false)
    await openDrillDown()
    fireEvent.click(screen.getByRole('button', { name: 'Staff' }))
    await waitFor(() => expect(mockConfirm).toHaveBeenCalled())
    expect(mockUpdateUserRoles).not.toHaveBeenCalled()
  })

  it('does not leave the role indicator flipped when updateUserRoles rejects, and surfaces the error', async () => {
    mockConfirm.mockResolvedValue(true)
    mockUpdateUserRoles.mockRejectedValue(new Error('Server rejected the change'))
    await openDrillDown()
    const staffButton = screen.getByRole('button', { name: 'Staff' })
    fireEvent.click(staffButton)
    await waitFor(() => expect(mockUpdateUserRoles).toHaveBeenCalledWith('target-1', { is_staff: true }))
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith(
      expect.stringContaining('Failed to grant Staff role'),
      'error',
    ))
    // The button must still render as inactive (no visible flip on a rejected write).
    expect(staffButton.style.background).not.toBe('rgb(240, 253, 244)')
  })
})
