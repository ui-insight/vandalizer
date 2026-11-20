import { expect, it } from 'vitest'
import { MODULES } from './modules'

// Loaded through a Vite glob, not a static import: the frontend Docker image
// builds with only frontend/ as its context, so `tsc -b` there must not need
// to resolve a path into backend/.
const [served] = Object.values(import.meta.glob(
  '../../../../backend/certification-data/panel-modules.json',
  { import: 'default', eager: true },
)) as Array<Array<Record<string, unknown>>>

// The panel falls back to these constants only before a versioned enrollment
// supplies its own course. They must never drift from the course data the
// backend serves for that same unversioned course (DEF-04).
it('keeps the unversioned fallback identical to the backend course data', () => {
  expect(served, 'backend/certification-data/panel-modules.json not found').toBeDefined()
  expect(MODULES.map(module => module.id)).toEqual(served.map(module => module.id))
  expect(JSON.parse(JSON.stringify(MODULES))).toEqual(served.map(module => Object.fromEntries(
    Object.entries(module).filter(([key]) => key in MODULES[0]))))
})
