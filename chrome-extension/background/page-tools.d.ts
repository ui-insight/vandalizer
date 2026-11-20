// Types for frontend/src/lib/extensionPageTools.test.ts, which runs these
// injected functions under jsdom. The extension itself loads the .js file.
export function readPage(query: string, maxChars: number): {
  url: string
  title: string
  text: string
  truncated: boolean
  login_required: boolean
  query_not_found?: boolean
}
export function clickRef(ref: number): Record<string, unknown>
export function typeRef(ref: number, text: string): Record<string, unknown>
export function selectRef(ref: number, option: string): Record<string, unknown>
