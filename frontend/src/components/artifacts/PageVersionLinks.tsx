import { ArrowUpRight, Check, Copy, Link2 } from 'lucide-react'
import type { Artifact } from '../../api/artifacts'

/** Only explicitly published revisions have a stable, independently revocable URL. */
export function PageVersionLinks({ artifact, revision, busy, publishDisabled, onPublish, onRemove, onCopy }: {
  artifact: Artifact
  revision: string
  busy: boolean
  publishDisabled: boolean
  onPublish: () => void
  onRemove: (revision: string) => void
  onCopy: (url: string) => void
}) {
  const links = artifact.publications ?? []
  const selectedIsPublic = links.some(link => link.revision === revision)
  const number = (id: string) => artifact.revisions.find(r => r.uuid === id)?.version
    ?? artifact.revisions.findIndex(r => r.uuid === id) + 1
  return <section className="page-share-section" aria-label="Separate version links">
    <h3><Link2 size={17} />Separate version links</h3>
    <p>Share versions side by side. Each link always shows its chosen version, even when you publish updates to the main link. Other versions stay private unless you publish or share them.</p>
    <p>Selected: version {number(revision)}. Check this version for private information before publishing.</p>
    <button className="page-button" disabled={busy || publishDisabled || selectedIsPublic}
      onClick={onPublish}>{selectedIsPublic ? <><Check size={16} />Separate link published</> : 'Publish as separate link'}</button>
    {links.length > 0 && <ul aria-label="Published version links" className="mt-4 space-y-4">
      {links.map(link => {
        const version = number(link.revision)
        const url = `${window.location.origin}/a/${link.token}`
        return <li key={link.revision}>
          <strong>Version {version}</strong>
          <div className="page-share-link"><label>Public link for version {version}<input readOnly value={url} onFocus={event => event.target.select()} /></label>
            <button className="page-icon-button" aria-label={`Copy version ${version} link`} disabled={busy} onClick={() => onCopy(url)}><Copy size={17} /></button>
          </div>
          <div className="page-actions">
            <a className="page-button" href={url} target="_blank" rel="noreferrer"><ArrowUpRight size={16} />Open version {version}</a>
            <button className="page-text-button" disabled={busy} onClick={() => onRemove(link.revision)}>Remove version {version} link</button>
          </div>
        </li>
      })}
    </ul>}
  </section>
}
