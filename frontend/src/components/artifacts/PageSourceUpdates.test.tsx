import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { PageBuiltFrom, PageSourceUpdates, updateRequest } from './PageSourceUpdates'
import type { PageSourceDocument } from '../../api/artifacts'

const stale: PageSourceDocument = {
  uuid: 'v1', title: 'NIH R01 Budget Table.xlsx', version_number: 1, status: 'updated',
  latest: { uuid: 'v2', title: 'NIH_R01_Budget_Table_v2.xlsx', version_number: 2, created_at: null, ready: true },
  changes: { items: ['Equipment · Y2: 15,000 → 20,000', 'Total · Total: 1,250,000 → 1,255,000'], more: 3, total: 5 },
}

it('shows what changed and hands the new version to Update page', () => {
  const onUpdate = vi.fn()
  render(<PageSourceUpdates sources={[stale, { uuid: 'n', title: 'Narrative.docx', version_number: 1, status: 'current' }]} onUpdate={onUpdate} />)
  expect(screen.getByRole('heading', { name: 'Source updated: review changes' })).toBeTruthy()
  expect(screen.getByText('Equipment · Y2: 15,000 → 20,000')).toBeTruthy()
  expect(screen.getByText('and 3 more changes')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Update page' }))
  expect(onUpdate).toHaveBeenCalledWith([stale])
})

it('waits for the new version to be read before offering the update', () => {
  render(<PageSourceUpdates sources={[{ ...stale, changes: undefined, latest: { ...stale.latest!, ready: false } }]} onUpdate={vi.fn()} />)
  expect(screen.getByText(/still being read/)).toBeTruthy()
  expect((screen.getByRole('button', { name: 'Update page' }) as HTMLButtonElement).disabled).toBe(true)
})

it('stays quiet when every source is current, and names them', () => {
  const { container } = render(<PageSourceUpdates sources={[{ ...stale, status: 'current', latest: undefined }]} onUpdate={vi.fn()} />)
  expect(container.textContent).toBe('')
  render(<PageBuiltFrom sources={[{ ...stale.latest!, status: 'current' }]} />)
  expect(screen.getByText('Built from: NIH_R01_Budget_Table_v2.xlsx (version 2)')).toBeTruthy()
})

it('drafts a request naming the new file and its changes', () => {
  const text = updateRequest([stale])
  expect(text).toContain('version 2, “NIH_R01_Budget_Table_v2.xlsx” (attached)')
  expect(text).toContain('Equipment · Y2: 15,000 → 20,000; Total · Total: 1,250,000 → 1,255,000; and 3 more')
})
