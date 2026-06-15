// Static import-graph reachability scan: find .ts/.tsx files under src that the
// app entry (src/main.tsx) cannot transitively reach. Handles static imports,
// re-exports, and dynamic import(). Relative specifiers only (no path aliases).
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs'
import { dirname, resolve, join, relative } from 'node:path'

const ROOT = resolve('src')
const ENTRY = resolve('src/main.tsx')
const exts = ['.ts', '.tsx', '.js', '.jsx']

function walk(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) out.push(...walk(p))
    else if (exts.some((e) => p.endsWith(e))) out.push(p)
  }
  return out
}

function resolveSpec(fromFile, spec) {
  if (!spec.startsWith('.')) return null // node_module / bare
  const base = resolve(dirname(fromFile), spec)
  const candidates = [
    base,
    ...exts.map((e) => base + e),
    ...exts.map((e) => join(base, 'index' + e)),
  ]
  for (const c of candidates) {
    if (existsSync(c) && statSync(c).isFile()) return c
  }
  return null // unresolved (css/asset/etc.)
}

const IMPORT_RE = /(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]|import\s*['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)/g

function importsOf(file) {
  const src = readFileSync(file, 'utf8')
  const specs = new Set()
  let m
  while ((m = IMPORT_RE.exec(src))) {
    const spec = m[1] || m[2] || m[3]
    if (spec) specs.add(spec)
  }
  return [...specs]
}

// BFS from entry
const reachable = new Set()
const queue = [ENTRY]
while (queue.length) {
  const file = queue.pop()
  if (reachable.has(file)) continue
  reachable.add(file)
  for (const spec of importsOf(file)) {
    const r = resolveSpec(file, spec)
    if (r && !reachable.has(r)) queue.push(r)
  }
}

const all = walk(ROOT)
const isTest = (p) => /\.(test|spec)\.[tj]sx?$/.test(p) || /(^|\/)__(tests|mocks)__\//.test(p) || /\/test\//.test(p) || /setupTests|vitest|testUtils|test-utils/.test(p)
const dead = all
  .filter((p) => !reachable.has(p))
  .filter((p) => !isTest(p))
  .map((p) => relative(resolve('.'), p))
  .sort()

console.log(`Total src files: ${all.length}`)
console.log(`Reachable from main.tsx: ${reachable.size}`)
console.log(`Unreachable (excluding tests): ${dead.length}\n`)
for (const d of dead) console.log(d)
