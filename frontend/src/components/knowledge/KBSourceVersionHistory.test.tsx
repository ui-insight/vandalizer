/**
 * Support ticket: a refresh that picked up a revised page discarded the old
 * text, so nobody could show what a source said when an answer was produced.
 * The panel lists the dated versions, shows any one of them, diffs it against
 * the one before, and names the version in effect on a picked date.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KBSourceVersionHistory, endOfDayIso } from './KBSourceVersionHistory'
import type { KBSourceVersion } from '../../types/knowledge'

vi.mock('../../api/knowledge', () => ({
  listKBSourceVersions: vi.fn(),
  getKBSourceVersion: vi.fn(),
  compareKBSourceVersions: vi.fn(),
}))

import { compareKBSourceVersions, getKBSourceVersion, listKBSourceVersions } from '../../api/knowledge'

const version = (n: number, over: Partial<KBSourceVersion> = {}): KBSourceVersion => ({
  uuid: `v${n}`,
  number: n,
  is_current: false,
  origin: 'refresh',
  url: 'https://www.uidaho.edu/policies/apm/45/14',
  url_title: 'APM 45.14',
  content_hash: `${n}`.repeat(64),
  content_hash_algorithm: 'sha256',
  char_count: 1200,
  truncated: false,
  captured_at: '2026-08-01T12:00:00+00:00',
  in_effect_from: '2026-08-01T12:00:00+00:00',
  superseded_at: null,
  last_confirmed_at: null,
  ...over,
})

const v2 = version(2, { is_current: true })
const v1 = version(1, {
  origin: 'baseline',
  captured_at: '2026-06-01T12:00:00+00:00',
  in_effect_from: '2026-06-01T12:00:00+00:00',
  superseded_at: '2026-08-01T12:00:00+00:00',
})

describe('KBSourceVersionHistory', () => {
  beforeEach(() => {
    vi.mocked(listKBSourceVersions).mockReset()
    vi.mocked(listKBSourceVersions).mockResolvedValue({ versions: [v2, v1] })
  })

  it('lists versions newest first and marks the current one', async () => {
    render(<KBSourceVersionHistory kbUuid="kb" sourceUuid="src" />)
    expect(await screen.findByText('Version history (2)')).toBeInTheDocument()
    expect(screen.getByTestId('version-2')).toHaveTextContent('current')
    expect(screen.getByTestId('version-1')).toHaveTextContent('text held when history began')
    // The first recorded version has nothing earlier to diff against.
    expect(screen.getByRole('button', { name: 'Changes in version 1' })).toBeDisabled()
  })

  it('shows an earlier version\'s text', async () => {
    vi.mocked(getKBSourceVersion).mockResolvedValue({ ...v1, content: 'over $25,000 needs approval' })
    render(<KBSourceVersionHistory kbUuid="kb" sourceUuid="src" />)
    fireEvent.click(await screen.findByRole('button', { name: 'View version 1' }))
    expect(await screen.findByText('over $25,000 needs approval')).toBeInTheDocument()
    expect(getKBSourceVersion).toHaveBeenCalledWith('kb', 'src', 'v1')
  })

  it('diffs a version against the one before it', async () => {
    vi.mocked(compareKBSourceVersions).mockResolvedValue({
      base: v1, target: v2, identical: false, added: 1, removed: 1, truncated: false,
      lines: [
        { op: '@', text: '@@ -1 +1 @@' },
        { op: '-', text: 'over $25,000' },
        { op: '+', text: 'over $50,000' },
      ],
    })
    render(<KBSourceVersionHistory kbUuid="kb" sourceUuid="src" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Changes in version 2' }))
    expect(await screen.findByText('Version 1 → 2: 1 lines added, 1 removed')).toBeInTheDocument()
    expect(screen.getByText('- over $25,000')).toBeInTheDocument()
    expect(screen.getByText('+ over $50,000')).toBeInTheDocument()
    expect(compareKBSourceVersions).toHaveBeenCalledWith('kb', 'src', 'v1', 'v2')
  })

  it('names the version in effect on a picked date', async () => {
    render(<KBSourceVersionHistory kbUuid="kb" sourceUuid="src" />)
    await screen.findByText('Version history (2)')
    vi.mocked(listKBSourceVersions).mockResolvedValue({ versions: [v2, v1], in_effect_version_uuid: 'v1' })

    fireEvent.change(screen.getByLabelText('In effect on'), { target: { value: '2026-07-04' } })

    await waitFor(() => expect(screen.getByTestId('version-1')).toHaveAttribute('aria-current', 'true'))
    expect(screen.getByRole('status')).toHaveTextContent('answers came from version 1')
    expect(listKBSourceVersions).toHaveBeenLastCalledWith('kb', 'src', endOfDayIso('2026-07-04'))
  })

  it('says when history has not started yet', async () => {
    vi.mocked(listKBSourceVersions).mockResolvedValue({ versions: [] })
    render(<KBSourceVersionHistory kbUuid="kb" sourceUuid="src" />)
    expect(await screen.findByText(/History starts at this source's next refresh/)).toBeInTheDocument()
  })
})
