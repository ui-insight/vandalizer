// jest-dom's matchers (toBeInTheDocument, toHaveValue, …) for vitest 5.
//
// src/test-setup.ts registers them at runtime. jest-dom 7's own type hook
// augments `Assertion<T>`, but vitest 5's Assertion takes `<R, T>`, so that
// augmentation no longer merges and every matcher fails to typecheck.
// vitest 5's documented extension point is `Matchers<R, T>`, which Assertion
// extends; hook the matchers in there instead. Drop this file once jest-dom
// ships a vitest-5-aware `@testing-library/jest-dom/vitest`.
import 'vitest'
import type { TestingLibraryMatchers } from '@testing-library/jest-dom/matchers'

declare module 'vitest' {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars
  interface Matchers<R extends void | Promise<void> = void | Promise<void>, T = unknown>
    extends TestingLibraryMatchers<unknown, R> {}
}
