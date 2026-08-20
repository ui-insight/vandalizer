import { describe, it, expect } from 'vitest'

// `formatPageLocator(page, approximate)` takes its second argument optionally,
// which means dropping it is legal TypeScript: `tsc -b` passes, and the page
// silently stops being hedged. Verified — sabotaging a call site that way
// typechecks clean and only a behavioural test catches it.
//
// ChatMessage has such a test (ChatMessage.citations.test.tsx). The extraction
// and workflow panels are several thousand lines with heavy context
// dependencies, and standing them up in jsdom to assert one string is a poor
// trade. So this guards every call site at the source instead: cheap, exact
// about the one mistake that matters, and it fails for the same reason a
// rendering test would.
//
// If a call site legitimately has no approximate flag to pass, the fix is to
// carry the flag through to it — not to relax this test.

// Read through Vite rather than node:fs — this project has no @types/node, and
// adding one as a test dependency would touch the lockfile for no other reason.
const sources = import.meta.glob('../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** Argument text of every formatPageLocator(...) call, paren-balanced. */
function callArguments(source: string): string[] {
  const calls: string[] = []
  const needle = 'formatPageLocator('
  let index = source.indexOf(needle)
  while (index !== -1) {
    let depth = 1
    let cursor = index + needle.length
    while (cursor < source.length && depth > 0) {
      if (source[cursor] === '(') depth += 1
      else if (source[cursor] === ')') depth -= 1
      cursor += 1
    }
    calls.push(source.slice(index + needle.length, cursor - 1))
    index = source.indexOf(needle, cursor)
  }
  return calls
}

describe('formatPageLocator call sites', () => {
  const sites = Object.entries(sources)
    .filter(([path]) => !/\.test\.tsx?$/.test(path) && !path.endsWith('pageLocator.ts'))
    .flatMap(([path, source]) =>
      callArguments(source).map(args => ({ file: path, args })),
    )

  it('finds the call sites at all, so a rename cannot silently empty this test', () => {
    expect(sites.length).toBeGreaterThanOrEqual(5)
  })

  it('always passes the approximate flag, so an OCR page is never shown as exact', () => {
    const unhedged = sites.filter(site => !/approximate/i.test(site.args))

    expect(
      unhedged.map(site => `${site.file}: formatPageLocator(${site.args})`),
    ).toEqual([])
  })
})
