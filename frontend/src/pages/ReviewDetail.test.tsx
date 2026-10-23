import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
const approve = vi.fn()
const navigate = vi.fn()
vi.mock('@tanstack/react-router', () => ({ useParams: () => ({ uuid: 'review-1' }), useNavigate: () => navigate, Link: ({ children }: { children: ReactNode }) => <a>{children}</a> }))
vi.mock('../components/layout/PageLayout', () => ({ PageLayout: ({ children }: { children: ReactNode }) => <main>{children}</main> }))
vi.mock('../components/files/DocumentViewer', () => ({ DocumentViewer: ({ docUuid }: { docUuid: string }) => <div>Original source {docUuid}</div> }))
vi.mock('../hooks/useMyReviewCount', () => ({ useMyReviewCount: () => ({ refresh: vi.fn() }) }))
vi.mock('../api/reviews', () => ({
  getReview: vi.fn().mockResolvedValue({ uuid: 'review-1', workflow_name: 'Proposal review', step_name: 'Check budget', status: 'pending', artifact_kind: 'markdown', data_for_review: { value: 'Original output' }, source_docs: [{ uuid: 'doc-1', title: 'Budget.pdf' }], review_instructions: 'Compare with the source.' }),
  approveReview: (...args: unknown[]) => approve(...args), rejectReview: vi.fn(),
}))
import ReviewDetail from './ReviewDetail'
beforeEach(() => { vi.clearAllMocks() })
describe('review evidence and decision recovery', () => {
  it('preserves edits and comments while inspecting a source, then sends exactly one edited decision', async () => {
    let resolve!: (value: unknown) => void
    approve.mockImplementation(() => new Promise(r => { resolve = r }))
    render(<ReviewDetail />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edit before approving' }))
    fireEvent.change(screen.getByLabelText('Edit review output'), { target: { value: 'Checked output' } })
    fireEvent.change(screen.getByLabelText('Comments (optional)'), { target: { value: 'Checked against the budget.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Inspect Budget.pdf' }))
    await screen.findByText('Original source doc-1')
    fireEvent.click(screen.getByRole('button', { name: 'Close source' }))
    expect(screen.getByLabelText('Edit review output')).toHaveValue('Checked output')
    expect(screen.getByLabelText('Comments (optional)')).toHaveValue('Checked against the budget.')
    const submit = screen.getByRole('button', { name: 'Approve with edits' })
    fireEvent.click(submit); fireEvent.click(submit)
    expect(approve).toHaveBeenCalledTimes(1)
    expect(approve).toHaveBeenCalledWith('review-1', { comments: 'Checked against the budget.', edited_artifact: { value: 'Checked output' } })
    resolve({ detail: 'approved' })
    await waitFor(() => expect(navigate).toHaveBeenCalled())
  })
  it('keeps comments on a failed decision and allows a retry', async () => {
    approve.mockRejectedValueOnce(new Error('Connection interrupted')).mockResolvedValue({ detail: 'approved' })
    render(<ReviewDetail />)
    await screen.findByRole('button', { name: 'Approve' })
    fireEvent.change(screen.getByLabelText('Comments (optional)'), { target: { value: 'Keep this note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Connection interrupted')
    expect(screen.getByLabelText('Comments (optional)')).toHaveValue('Keep this note')
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(approve).toHaveBeenCalledTimes(2))
  })
})
