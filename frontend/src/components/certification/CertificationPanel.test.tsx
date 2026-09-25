import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { CertificationProgress, ValidationResult, CompletionResult } from '../../types/certification'

const validate = vi.fn()
const complete = vi.fn()
const toast = vi.fn()
const panelState: { progress: CertificationProgress | null } = { progress: null }

vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({
    isOpen: true,
    mode: 'fullscreen',
    closePanel: vi.fn(),
    setMode: vi.fn(),
    progress: panelState.progress,
    loading: false,
    validate,
    complete,
    provision: vi.fn(),
    getExercise: vi.fn().mockResolvedValue(null),
    submitAssessment: vi.fn(),
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ user: { user_id: 'alice' } }),
}))

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast }),
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

// The detail view is exercised elsewhere; here it only needs a Check Progress.
vi.mock('./ModuleDetail', () => ({
  ModuleDetail: ({ onValidate }: { onValidate: () => void }) => (
    <button onClick={onValidate}>Check Progress</button>
  ),
}))

vi.mock('./CelebrationOverlay', () => ({
  CelebrationOverlay: () => <div>Module Complete!</div>,
}))

import { CertificationPanel } from './CertificationPanel'

function progressWith(stars: number, completed = true): CertificationProgress {
  return {
    id: 'p1',
    user_id: 'alice',
    modules: {
      foundations: { completed, stars, completed_at: null, attempts: 1, xp_earned: 150 },
    },
    total_xp: 150,
    level: 'novice',
    certified: false,
    certified_at: null,
    last_activity_date: null,
    unlocked: true,
  }
}

const threeStars: ValidationResult = {
  passed: true,
  stars: 3,
  checks: [{ name: 'Has extraction workflow', passed: true, detail: '' }],
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.setItem('cert-active-module:alice', 'foundations')
  validate.mockResolvedValue(threeStars)
  complete.mockResolvedValue({ module_id: 'foundations', stars: 3, xp_earned: 25 } as CompletionResult)
})

describe('CertificationPanel Check Progress on a completed module', () => {
  it('saves a better star result without replaying the completion celebration', async () => {
    panelState.progress = progressWith(2)
    render(<CertificationPanel />)
    fireEvent.click(screen.getByText('Check Progress'))
    await waitFor(() => expect(complete).toHaveBeenCalledWith('foundations'))
    expect(toast).toHaveBeenCalledWith('Saved: 3 stars (+25 XP)', 'success')
    expect(screen.queryByText('Module Complete!')).toBeNull()
  })

  it('does not re-save when the result is no better than the stored stars', async () => {
    panelState.progress = progressWith(3)
    render(<CertificationPanel />)
    fireEvent.click(screen.getByText('Check Progress'))
    await waitFor(() => expect(validate).toHaveBeenCalled())
    await screen.findByText('All checks passed!')
    expect(complete).not.toHaveBeenCalled()
  })

  it('leaves an uncompleted module for Complete Module to finish', async () => {
    panelState.progress = progressWith(0, false)
    render(<CertificationPanel />)
    fireEvent.click(screen.getByText('Check Progress'))
    await screen.findByText('All checks passed!')
    expect(complete).not.toHaveBeenCalled()
  })
})
