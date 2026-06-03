// Shared naming rules for user-created entities: workflows, folders,
// extractions, prompts, formatters, knowledge bases, automations and library
// folders. Mirrors backend/app/utils/naming.py - keep the two in sync so the
// client and server agree on what a valid name is.

// Keep in sync with MAX_NAME_LENGTH in backend/app/utils/naming.py
export const MAX_NAME_LENGTH = 100

// C0 / C1 control characters - stripped to match the backend Unicode
// "Other" category strip. Ordinary whitespace is handled by the collapse step.
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u0008\u000E-\u001F\u007F-\u009F]/g

/**
 * Strip control characters and collapse whitespace runs to a single space, then
 * trim. Mirrors the backend normalizer so a pasted multi-line title renders as
 * one tidy line everywhere it's shown. Does not validate.
 */
export function normalizeName(value: string): string {
  return value.replace(CONTROL_CHARS, '').replace(/\s+/g, ' ').trim()
}

/**
 * Validate a name against the shared rules. Returns a human-readable error
 * message if invalid, or null if valid. Pass the raw input value; the label
 * (e.g. "Name", "Title", "Folder name") is woven into the message.
 */
export function getNameError(value: string, label = 'Name'): string | null {
  const cleaned = normalizeName(value)
  if (!cleaned) return `${label} cannot be empty.`
  if (cleaned.length > MAX_NAME_LENGTH) {
    return `${label} must be ${MAX_NAME_LENGTH} characters or fewer.`
  }
  return null
}
