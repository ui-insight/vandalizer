import '@testing-library/jest-dom'

// Node 22+ defines an experimental `localStorage` global that shadows jsdom's
// implementation under vitest; its methods are unusable without
// --localstorage-file, so any component touching storage crashes with
// "localStorage.getItem is not a function". Replace broken globals with an
// in-memory Storage shim.
function ensureStorage(name: 'localStorage' | 'sessionStorage') {
  const current = (globalThis as Record<string, unknown>)[name] as Storage | undefined
  if (current && typeof current.getItem === 'function') return
  const store = new Map<string, string>()
  const shim: Storage = {
    getItem: (key) => (store.has(key) ? store.get(key)! : null),
    setItem: (key, value) => { store.set(key, String(value)) },
    removeItem: (key) => { store.delete(key) },
    clear: () => { store.clear() },
    key: (index) => Array.from(store.keys())[index] ?? null,
    get length() { return store.size },
  }
  Object.defineProperty(globalThis, name, { value: shim, configurable: true })
  Object.defineProperty(window, name, { value: shim, configurable: true })
}
ensureStorage('localStorage')
ensureStorage('sessionStorage')
