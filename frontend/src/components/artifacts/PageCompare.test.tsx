import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { PageCompare } from './PageCompare'

const api = vi.hoisted(() => ({ compareArtifactVersions: vi.fn() }))
vi.mock('../../api/artifacts', () => api)

const revisions = [1, 2, 3, 4, 5].map(n => ({ uuid: `r${n}`, title: 'NIH R01 Budget Dashboard', created_at: '', warnings: [], version: n }))
const result = (base: number, target: number) => ({
  base: { revision: `r${base}`, version: base }, target: { revision: `r${target}`, version: target }, title: null,
  numbers: [{ label: 'Equipment · Y2', old: '$15,000', new: '$20,000', section: 'Budget by year' }],
  sections_added: ['How to read this page'], sections_removed: [], text: [],
  design: ['Colours changed: #1e3a8a → #b8860b'], truncated: false,
  summary: '1 figure changed (Equipment · Y2: $15,000 → $20,000); added section “How to read this page”; design changed',
})

beforeEach(() => {
  api.compareArtifactVersions.mockImplementation((_id: string, base: string, target: string) => Promise.resolve(result(Number(base[1]), Number(target[1]))))
})

it('compares the last two versions first, then any two the user picks', async () => {
  render(<PageCompare uuid="p" revisions={revisions} versionNumber={id => Number(id.slice(1))} />)
  await waitFor(() => expect(api.compareArtifactVersions).toHaveBeenCalledWith('p', 'r4', 'r5'))
  fireEvent.change(screen.getByLabelText('Compare from version'), { target: { value: 'r1' } })
  await waitFor(() => expect(api.compareArtifactVersions).toHaveBeenLastCalledWith('p', 'r1', 'r5'))
  expect(await screen.findByText(/Version 1 → Version 5:/)).toBeTruthy()
  const row = screen.getByRole('row', { name: /Equipment · Y2/ })
  expect(within(row).getByText('$15,000').tagName).toBe('DEL')
  expect(within(row).getByText('$20,000').tagName).toBe('INS')
  expect(screen.getByText('Added: How to read this page')).toBeTruthy()
  // Design changes are listed on their own, under their own heading.
  expect(screen.getByRole('heading', { name: 'Design only' })).toBeTruthy()
  expect(screen.getByText('Colours changed: #1e3a8a → #b8860b')).toBeTruthy()
})

it('does not compare a version with itself', async () => {
  render(<PageCompare uuid="p" revisions={revisions} versionNumber={id => Number(id.slice(1))} />)
  await waitFor(() => expect(api.compareArtifactVersions).toHaveBeenCalledTimes(1))
  fireEvent.change(screen.getByLabelText('Compare from version'), { target: { value: 'r5' } })
  expect(screen.getByText('Choose two different versions.')).toBeTruthy()
  expect(api.compareArtifactVersions).toHaveBeenCalledTimes(1)
})
