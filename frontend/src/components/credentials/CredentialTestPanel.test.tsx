import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CredentialTestPanel, summarizeTest } from './CredentialTestPanel'
import type { CredentialTestResult } from '../../types/credential'

const OK: CredentialTestResult = {
  ok: true, status_code: 200, elapsed_ms: 40,
  steps: [
    { step: 'Configuration', ok: true, detail: 'All required fields are present.' },
    { step: 'Header', ok: true, detail: 'Will send header X-Api-Key (12 characters, value not shown).' },
    { step: 'Test request', ok: true, detail: 'GET https://api.example.com/me → 200 OK in 40 ms.' },
  ],
}
const BAD: CredentialTestResult = {
  ok: false, status_code: 401, elapsed_ms: 30,
  steps: [
    { step: 'Configuration', ok: true, detail: 'All required fields are present.' },
    { step: 'Header', ok: true, detail: 'Will send header X-Api-Key (3 characters, value not shown).' },
    { step: 'Test request', ok: false, detail: 'GET https://api.example.com/me → 401 Unauthorized in 30 ms. The server rejected the credential (401 Unauthorized).' },
  ],
}

describe('summarizeTest', () => {
  it('names the outcome and the failing step', () => {
    expect(summarizeTest(OK)).toBe('Connection works — the test request returned 200.')
    expect(summarizeTest({ ...OK, status_code: null })).toMatch(/Add a test URL/)
    expect(summarizeTest(BAD)).toBe('Test request failed.')
  })
})

describe('CredentialTestPanel', () => {
  it('runs the test with the URL and lists each step', async () => {
    const run = vi.fn().mockResolvedValue(OK)
    const onUrl = vi.fn()
    render(<CredentialTestPanel run={run} testUrl="https://api.example.com/me" onTestUrlChange={onUrl} />)
    fireEvent.click(screen.getByRole('button', { name: 'Test' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Connection works'))
    expect(run).toHaveBeenCalledWith('https://api.example.com/me')
    expect(screen.getByText(/Will send header X-Api-Key/)).toBeInTheDocument()
    expect(screen.getByText(/→ 200 OK/)).toBeInTheDocument()
  })

  it('shows the failing step and the server hint', async () => {
    render(<CredentialTestPanel run={vi.fn().mockResolvedValue(BAD)} testUrl="" onTestUrlChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Test' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Test request failed.'))
    expect(screen.getByText(/rejected the credential/)).toBeInTheDocument()
  })

  it('surfaces a request error without a report', async () => {
    render(<CredentialTestPanel run={vi.fn().mockRejectedValue(new Error('Network down'))} testUrl="" onTestUrlChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Test' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Network down'))
  })

  it('edits the URL through the host and can hide the field', () => {
    const onUrl = vi.fn()
    const { rerender } = render(<CredentialTestPanel run={vi.fn()} testUrl="" onTestUrlChange={onUrl} />)
    fireEvent.change(screen.getByLabelText('Test URL'), { target: { value: 'https://x.example/' } })
    expect(onUrl).toHaveBeenCalledWith('https://x.example/')
    rerender(<CredentialTestPanel run={vi.fn()} testUrl="" onTestUrlChange={onUrl} hideUrlField />)
    expect(screen.queryByLabelText('Test URL')).toBeNull()
  })
})
