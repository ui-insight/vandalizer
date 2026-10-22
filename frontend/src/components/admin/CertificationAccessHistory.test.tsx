import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CertificationAccessHistory } from './CertificationAccessHistory'

describe('Administrator access history', () => {
  it('shows the recorded actor and reason separately from credit', () => {
    render(<CertificationAccessHistory history={{ state: 'recorded', historical_unlocked: true, older_available: true, changes: [{
      request_id: 'a'.repeat(32), actor_user_id: 'authorized-admin', reason: 'Restore requested course access',
      previous_unlocked: false, unlocked: true, recorded_at: '2026-10-08T12:00:00Z', credit_effect: 'none',
    }] }} />)
    expect(screen.getByText('authorized-admin')).toBeInTheDocument()
    expect(screen.getByText('Restore requested course access')).toBeInTheDocument()
    expect(screen.getByText(/do not establish assessed credit/)).toBeInTheDocument()
    expect(screen.getByText(/Earlier changes remain/)).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('does not invent attribution for a historical flag', () => {
    render(<CertificationAccessHistory history={{ state: 'not_recorded', historical_unlocked: true, older_available: false, changes: [] }} />)
    expect(screen.getByText(/reason or authorizing administrator/)).toBeInTheDocument()
  })

  it('keeps unavailable history distinct from no changes', () => {
    render(<CertificationAccessHistory history={{ state: 'unavailable', historical_unlocked: false, older_available: false, changes: [] }} />)
    expect(screen.getByText(/history is unavailable/)).toBeInTheDocument()
    expect(screen.queryByText(/No administrator access changes are recorded/)).not.toBeInTheDocument()
  })
})
