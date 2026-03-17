import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

// Mock the approvals API module
vi.mock('../api/approvals', () => ({
  listApprovals: vi.fn(),
  approveRequest: vi.fn(),
  rejectRequest: vi.fn(),
  getApprovalCount: vi.fn(),
}))

// Mock useAuth hook
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: '1', user_id: 'testuser', email: 'test@example.com', name: 'Test', is_admin: false },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

// Mock PageLayout to render children directly
vi.mock('../components/layout/PageLayout', () => ({
  PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

import * as api from '../api/approvals'
import type { ApprovalRequest } from '../api/approvals'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Approvals page', () => {
  it('renders "Approval Queue" heading', async () => {
    vi.mocked(api.listApprovals).mockResolvedValue({ approvals: [] })

    const Approvals = (await import('./Approvals')).default
    render(<Approvals />)

    expect(screen.getByText('Approval Queue')).toBeTruthy()
  })

  it('shows loading state initially', async () => {
    // Make the API call hang so loading state persists
    vi.mocked(api.listApprovals).mockReturnValue(new Promise(() => {}))

    const Approvals = (await import('./Approvals')).default
    render(<Approvals />)

    expect(screen.getByText('Loading...')).toBeTruthy()
  })

  it('renders approval items after API loads', async () => {
    const mockApprovals: ApprovalRequest[] = [
      {
        uuid: 'appr-1',
        workflow_result_id: 'wr-1',
        workflow_id: 'wf-1',
        step_index: 0,
        step_name: 'Review Budget Data',
        data_for_review: { total: 50000 },
        review_instructions: 'Please verify the budget figures',
        status: 'pending',
        assigned_to_user_ids: ['testuser'],
        reviewer_user_id: null,
        reviewer_comments: '',
        decision_at: null,
        created_at: '2025-06-01T10:00:00',
      },
      {
        uuid: 'appr-2',
        workflow_result_id: 'wr-2',
        workflow_id: 'wf-2',
        step_index: 1,
        step_name: 'Approve Publication',
        data_for_review: { title: 'Research Paper' },
        review_instructions: 'Check publication compliance',
        status: 'pending',
        assigned_to_user_ids: ['testuser'],
        reviewer_user_id: null,
        reviewer_comments: '',
        decision_at: null,
        created_at: '2025-06-02T14:30:00',
      },
    ]

    vi.mocked(api.listApprovals).mockResolvedValue({ approvals: mockApprovals })

    const Approvals = (await import('./Approvals')).default
    render(<Approvals />)

    await waitFor(() => {
      expect(screen.getByText('Review Budget Data')).toBeTruthy()
      expect(screen.getByText('Approve Publication')).toBeTruthy()
    })

    // Verify the review instructions are shown (truncated in the list)
    expect(screen.getByText(/Please verify the budget figures/)).toBeTruthy()
  })
})
