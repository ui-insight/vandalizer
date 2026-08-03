// University directory display names often embed the email in brackets —
// "Kasireddy, Kiran Kumar Reddy (kkasireddy@uidaho.edu)". When the UI renders
// the email separately anyway, strip the duplicate from the name.
export function nameWithoutEmail(
  name: string | null | undefined,
  email: string | null | undefined,
): string | null {
  if (!name) return null
  if (!email) return name
  const escaped = email.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const stripped = name.replace(new RegExp(`\\s*[([]\\s*${escaped}\\s*[)\\]]\\s*$`, 'i'), '').trim()
  // If the name was nothing but the email, keep it rather than render blank.
  return stripped || name
}
