import { afterEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { EditorialCorrection } from './EditorialCorrection'
import corrections from './editorialCorrections.json'

const notice = corrections.module_notices[0]
const digestBytes = Uint8Array.from(notice.unversioned_content_sha256[0].match(/../g)!, byte => parseInt(byte, 16)).buffer
afterEach(() => vi.unstubAllGlobals())

it('binds a module correction to the known historical package and module', () => {
  const view = render(<EditorialCorrection moduleId={notice.module_ids[0]} manifestSha256={notice.manifest_sha256} />)
  expect(screen.getByRole('complementary', { name: notice.title })).toBeInTheDocument()
  view.rerender(<EditorialCorrection moduleId="foreign" manifestSha256={notice.manifest_sha256} />)
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  view.rerender(<EditorialCorrection moduleId={notice.module_ids[0]} manifestSha256={'f'.repeat(64)} content="original" />)
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
})

it('explains an exact unversioned description match without inventing a course identity', async () => {
  vi.stubGlobal('crypto', { subtle: { digest: vi.fn().mockResolvedValue(digestBytes) } })
  render(<EditorialCorrection moduleId={notice.module_ids[0]} content="preserved description" />)
  expect(await screen.findByRole('complementary', { name: notice.title })).toBeInTheDocument()
  expect(screen.getByText(/matches the preserved module description; it does not identify a historical course version/)).toBeInTheDocument()
})

it('discards an old description match after navigation', async () => {
  let finish!: (value: ArrayBuffer) => void
  const digest = vi.fn().mockImplementationOnce(() => new Promise<ArrayBuffer>(resolve => { finish = resolve }))
    .mockResolvedValue(new Uint8Array(32).buffer)
  vi.stubGlobal('crypto', { subtle: { digest } })
  const view = render(<EditorialCorrection moduleId={notice.module_ids[0]} content="preserved description" />)
  view.rerender(<EditorialCorrection moduleId="other" content="different description" />)
  finish(digestBytes)
  await waitFor(() => expect(digest).toHaveBeenCalledTimes(2))
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
})
