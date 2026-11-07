import { useEffect, useState } from 'react'
import { Clock, Eye, Globe2, LockKeyhole } from 'lucide-react'
import * as api from '../../api/artifacts'

export type ExpiryChoice = 'never' | '7' | '30' | 'custom'

/** The form state behind a link's expiry and audience controls. */
export interface LinkDraft { expiry: ExpiryChoice; customDate: string; audience: api.LinkAudience; emails: string }

export const DEFAULT_LINK: LinkDraft = { expiry: 'never', customDate: '', audience: 'anyone', emails: '' }

const DAY = 86_400_000

export function formatDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, withTime
    ? { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }
    : { year: 'numeric', month: 'short', day: 'numeric' })
}

/** A link's current settings as an editable draft. */
export function draftFrom(link: api.PublicLinkInfo | null | undefined): LinkDraft {
  if (!link) return DEFAULT_LINK
  return {
    // An expired link opens on an empty date, not "Never": saving it untouched
    // must ask for a new date instead of making the link permanent.
    expiry: link.expires_at ? 'custom' : 'never',
    customDate: link.expires_at && !link.expired ? link.expires_at.slice(0, 10) : '',
    audience: link.audience, emails: link.emails.join(', '),
  }
}

/** Draft → settings for the API; an error string when it can't be sent. */
export function settingsFrom(draft: LinkDraft, now = new Date()): api.LinkSettings | string {
  let expires: string | null = null
  if (draft.expiry === '7' || draft.expiry === '30') expires = new Date(now.getTime() + Number(draft.expiry) * DAY).toISOString()
  if (draft.expiry === 'custom') {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.customDate)) return 'Choose the date the link should expire.'
    // The link works through the whole chosen day, in the owner's time zone.
    const end = new Date(`${draft.customDate}T23:59:59`)
    if (Number.isNaN(end.getTime()) || end <= now) return 'Choose an expiry date in the future.'
    expires = end.toISOString()
  }
  const emails = draft.audience === 'signed_in'
    ? draft.emails.split(/[\s,;]+/).map(e => e.trim()).filter(Boolean)
    : []
  return { expires_at: expires, audience: draft.audience, emails }
}

/** Expiry and "who can open it" for a public link. */
export function LinkAccessFields({ draft, onChange, disabled, idPrefix, name = 'Link' }: { draft: LinkDraft; onChange: (draft: LinkDraft) => void; disabled?: boolean; idPrefix: string; name?: string }) {
  const today = new Date().toISOString().slice(0, 10)
  return <fieldset className="page-link-access" disabled={disabled}>
    <legend className="sr-only">Link access</legend>
    <label>Link expires
      <select aria-label={`${name} expires`} value={draft.expiry} onChange={e => onChange({ ...draft, expiry: e.target.value as ExpiryChoice })}>
        <option value="never">Never</option>
        <option value="7">In 7 days</option>
        <option value="30">In 30 days</option>
        <option value="custom">On a date…</option>
      </select>
    </label>
    {draft.expiry === 'custom' && <label>Expiry date<input type="date" aria-label={`${name} expiry date`} min={today} value={draft.customDate} onChange={e => onChange({ ...draft, customDate: e.target.value })} /></label>}
    <div role="radiogroup" aria-label={`Who can open the ${name.toLowerCase()}`} className="page-link-audience">
      <label><input type="radio" name={`${idPrefix}-audience`} checked={draft.audience === 'anyone'} onChange={() => onChange({ ...draft, audience: 'anyone' })} /><Globe2 size={14} aria-hidden /> Anyone with the link</label>
      <label><input type="radio" name={`${idPrefix}-audience`} checked={draft.audience === 'signed_in'} onChange={() => onChange({ ...draft, audience: 'signed_in' })} /><LockKeyhole size={14} aria-hidden /> Only people signed in to Vandalizer</label>
    </div>
    {draft.audience === 'signed_in' && <label>Only these people (optional)
      <textarea aria-label={`${name}: only these email addresses`} rows={2} placeholder="name@uidaho.edu, another@uidaho.edu" value={draft.emails} onChange={e => onChange({ ...draft, emails: e.target.value })} />
      <span className="page-link-hint">Leave empty to allow anyone signed in to this Vandalizer. Named people must have verified that email address. You'll see who opened it.</span>
    </label>}
  </fieldset>
}

/** "Expires Dec 15, 2026 · Opened 3 times, last Nov 2, 10:14 AM" plus named viewers. */
export function LinkStatus({ link }: { link: api.PublicLinkInfo | null | undefined }) {
  if (!link) return null
  const expiry = link.expired ? <strong className="page-link-expired">Expired {formatDate(link.expires_at)}</strong>
    : link.expires_at ? <>Expires {formatDate(link.expires_at)}</> : <>Never expires</>
  const opened = link.views.count
    ? <>Opened {link.views.count} time{link.views.count === 1 ? '' : 's'} · last opened {formatDate(link.views.last_at, true)}</>
    : <>Not opened yet</>
  return <div className="page-link-status">
    <p><Clock size={14} aria-hidden /> {expiry} · {link.audience === 'signed_in' ? (link.emails.length ? `Signed-in: ${link.emails.length} named ${link.emails.length === 1 ? 'person' : 'people'}` : 'Signed-in accounts only') : 'Anyone with the link'}</p>
    <p><Eye size={14} aria-hidden /> {opened}</p>
    {link.viewers.length > 0 && <details><summary>Who opened it</summary><ul>
      {link.viewers.map(v => <li key={v.email || v.name}>{v.name || v.email}{v.name && v.email ? ` (${v.email})` : ''}: {v.count} time{v.count === 1 ? '' : 's'}, last {formatDate(v.last_at, true)}</li>)}
    </ul></details>}
  </div>
}

/** Every live public link the user has, so forgotten ones can be cleaned up. */
export function PublicLinksPanel() {
  const [links, setLinks] = useState<api.LivePublicLink[] | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let live = true
    Promise.resolve().then(() => api.listPublicLinks())
      .then(r => { if (live) setLinks(r.links) }).catch(() => { if (live) setError(true) })
    return () => { live = false }
  }, [])
  // A side panel that can't load stays out of the way; the Pages list still works.
  if (error) return null
  if (!links || links.length === 0) return null
  return <details className="page-public-links">
    <summary><Globe2 size={15} aria-hidden /> Your public links ({links.length}){links.some(l => l.expired) ? ` · ${links.filter(l => l.expired).length} expired` : ''}</summary>
    <ul>
      {links.map(link => <li key={link.url}>
        <a href={`/pages/${encodeURIComponent(link.artifact_uuid)}#share`}>{link.title}</a>
        <span> · {link.kind === 'main' ? 'Main link' : 'Version link'}{link.version ? `, version ${link.version}` : ''}</span>
        <span> · {link.expired ? <strong className="page-link-expired">expired {formatDate(link.expires_at)}</strong> : link.expires_at ? `expires ${formatDate(link.expires_at)}` : 'never expires'}</span>
        <span> · {link.audience === 'signed_in' ? 'signed-in only' : 'anyone with the link'}</span>
        <span> · {link.views.count ? `opened ${link.views.count}×, last ${formatDate(link.views.last_at)}` : 'not opened yet'}</span>
      </li>)}
    </ul>
  </details>
}
