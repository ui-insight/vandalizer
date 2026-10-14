import { expect, it } from 'vitest'
import served from '../../../../backend/certification-data/panel-modules.json'
import { MODULES } from './modules'

// The panel falls back to these constants only before a versioned enrollment
// supplies its own course. They must never drift from the course data the
// backend serves for that same unversioned course (DEF-04).
it('keeps the unversioned fallback identical to the backend course data', () => {
  expect(MODULES.map(module => module.id)).toEqual(served.map(module => module.id))
  expect(JSON.parse(JSON.stringify(MODULES))).toEqual(served.map(module => Object.fromEntries(
    Object.entries(module).filter(([key]) => key in MODULES[0]))))
})
