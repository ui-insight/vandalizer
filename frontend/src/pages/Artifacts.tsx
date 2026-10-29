import { PageVersionLinks } from '../components/artifacts/PageVersionLinks'
import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowUpRight, Check, ChevronRight, Code2, Copy, Download, FileText, Globe2, Link2, LockKeyhole, MessageSquare, Share2, Trash2, Workflow } from 'lucide-react'
import * as api from '../api/artifacts'
import { PagesBrowser } from '../components/artifacts/PagesBrowser'
import { PageBadge, PageDialog, PagePreview, pagesUrl } from '../components/artifacts/PagePrimitives'
import { listTeams } from '../api/teams'
import { PagePrintLink, pageViewUrl } from '../components/artifacts/PagePrintLink'

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Could not complete this action. Please try again.'

export function ArtifactsHome() {
  return <main className="page-workspace"><div className="page-workspace-inner"><nav className="page-breadcrumb" aria-label="Breadcrumb"><a href={pagesUrl()}><ArrowLeft size={15} />Back to Files → Pages</a></nav><PagesBrowser /></div></main>
}

export default function ArtifactPage({ uuid, publicToken }: { uuid?: string; publicToken?: string }) {
  const [artifact, setArtifact] = useState<api.Artifact | null>(null)
  const [publicInfo, setPublicInfo] = useState<api.PublicArtifact | null>(null)
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const [editor, setEditor] = useState<{ title: string; html: string; base: string } | null>(null)
  const [teams, setTeams] = useState<{ uuid: string; name: string }[]>([])
  const [teamError, setTeamError] = useState(false)
  const [team, setTeam] = useState('')
  const [teamRevision, setTeamRevision] = useState('')
  const [publicRevision, setPublicRevision] = useState('')
  const [sharing, setSharing] = useState(() => window.location.hash === '#share')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [requestChanges, setRequestChanges] = useState(false)
  const [changes, setChanges] = useState('')
  useEffect(() => {
    let live = true
    setLoading(true); setError(''); setArtifact(null); setPublicInfo(null); setEditor(null); setTeamError(false)
    const load = async () => {
      try {
        if (publicToken) { const info = await api.getPublicArtifact(publicToken); if (live) setPublicInfo(info) }
        else if (uuid) {
          const item = await api.getArtifact(uuid)
          if (live) { setArtifact(item); setSelected(item.latest_revision); setTeam(item.team_id || ''); setTeamRevision(item.team_revision || item.published_revision || item.latest_revision); setPublicRevision(item.latest_revision) }
          if (item.can_manage) {
            try { const all = await listTeams(); if (live) setTeams(all) } catch { if (live) setTeamError(true) }
          }
        }
      } catch (e) { if (live) setError(errorMessage(e)) }
      finally { if (live) setLoading(false) }
    }
    void load(); return () => { live = false }
  }, [uuid, publicToken, attempt])
  const action = async (fn: () => Promise<void>) => {
    if (pending.current) return
    pending.current = true; setBusy(true); setError(''); setNotice('')
    try { await fn() } catch (e) { setError(errorMessage(e)) } finally { pending.current = false; setBusy(false) }
  }
  const savedTeam = artifact?.team_id || ''
  const savedTeamRevision = artifact?.team_revision || artifact?.published_revision || artifact?.latest_revision || ''
  const accessDirty = team !== savedTeam || (!!team && teamRevision !== savedTeamRevision)
  const discardAccessChanges = () => { setTeam(savedTeam); setTeamRevision(savedTeamRevision) }
  const reload = async (resetAccess = false) => {
    if (uuid) {
      const item = await api.getArtifact(uuid)
      setArtifact(item)
      if (resetAccess || !accessDirty) {
        setTeam(item.team_id || '')
        setTeamRevision(item.team_revision || item.published_revision || item.latest_revision)
      }
      return item
    }
  }
  const revision = artifact?.revisions.find(r => r.uuid === selected)
  const versionNumber = (id: string) => artifact?.revisions.find(r => r.uuid === id)?.version ?? (artifact ? artifact.revisions.findIndex(r => r.uuid === id) + 1 : 1)
  const version = versionNumber(selected)
  const publishedVersion = artifact?.published_revision ? versionNumber(artifact.published_revision) : 0
  const publicVersion = versionNumber(publicRevision)
  const latestVersion = artifact ? versionNumber(artifact.latest_revision) : 0
  const publicSelectionIsPublished = !!artifact?.published_revision && publicRevision === artifact.published_revision
  const hasSeparateLinks = !!artifact?.publications?.length
  const hasPublicLinks = !!artifact?.published_revision || hasSeparateLinks
  const isPublished = (id: string) => id === artifact?.published_revision || !!artifact?.publications?.some(link => link.revision === id)
  const selectedIsPublished = isPublished(selected)
  const hasDraft = !!artifact?.can_manage && hasPublicLinks && !isPublished(artifact.latest_revision)
  const contentUrl = publicToken ? api.publicArtifactContentUrl(publicToken, publicInfo?.revision) : uuid && selected ? api.artifactContentUrl(uuid, selected) : ''
  const publicUpdated = publicInfo?.updated_at ? new Date(publicInfo.updated_at) : null
  const publicUpdatedLabel = publicUpdated && !Number.isNaN(publicUpdated.getTime())
    ? publicUpdated.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short' }) : null
  const title = publicInfo?.title || revision?.title || artifact?.title || 'Page'
  const backUrl = pagesUrl(artifact?.source?.project_uuid)
  const publicLink = artifact?.public_token ? `${window.location.origin}/a/${artifact.public_token}` : ''
  const copy = (value: string, success: string) => void action(async () => { await navigator.clipboard.writeText(value); setNotice(success) })
  const chatUrl = uuid ? `/?editPage=${encodeURIComponent(uuid)}${artifact?.source?.conversation_uuid ? `&conversation=${encodeURIComponent(artifact.source.conversation_uuid)}` : ''}${artifact?.source?.project_uuid ? `&project=${encodeURIComponent(artifact.source.project_uuid)}` : ''}` : ''
  const closeSharing = () => { setSharing(false); if (window.location.hash === '#share') window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search) }
  const openSharing = () => { setPublicRevision(artifact?.latest_revision || ''); setSharing(true) }
  const feedback = <>{error && <p role="alert" className="page-alert">{error}</p>}{notice && <p role="status" className="page-notice">{notice}</p>}</>
  return <main className="page-workspace"><div className="page-workspace-inner">
    {!publicToken && <nav className="page-breadcrumb" aria-label="Breadcrumb"><a href={backUrl}><ArrowLeft size={15} />Files</a><ChevronRight size={13} /><a href={backUrl}>Pages</a><ChevronRight size={13} /><span>{loading ? 'Loading…' : 'Page details'}</span></nav>}
    <header className="page-heading"><div className="page-heading-copy"><p className="page-eyebrow">{publicToken ? 'SHARED PAGE' : 'SAVED PAGE'}</p><h1>{title}</h1>
      {(artifact || publicInfo) && <div className="page-meta">
        {publicToken ? <><PageBadge published>Published · version {publicInfo?.version}</PageBadge><span>Anyone with the link</span>{publicUpdatedLabel ? <span>Last updated <time dateTime={publicInfo!.updated_at}>{publicUpdatedLabel}</time></span> : <span>Last updated date unavailable</span>}</> : artifact && !artifact.can_manage ? <PageBadge>Team access · version {version}</PageBadge> : <>
          {artifact?.published_revision ? <PageBadge published>Published · version {publishedVersion}</PageBadge> : hasSeparateLinks ? <PageBadge published>Published version links</PageBadge> : <PageBadge>{artifact?.team_id ? 'Team access' : 'Private · only you'}</PageBadge>}
          {hasDraft && <PageBadge>Unpublished changes</PageBadge>}
          {hasPublicLinks && <span>Workspace access: {artifact?.team_id ? 'you and your team' : 'only you'}</span>}
          {!hasPublicLinks && <span>Share only when you’re ready</span>}
        </>}
      </div>}
    </div>
    {!loading && (artifact || publicInfo) && <div className="page-actions">
      <PagePrintLink contentUrl={contentUrl} />
      <a className="page-button" href={`${contentUrl}${contentUrl.includes('?') ? '&' : '?'}download=true`}><Download size={16} />Download HTML</a>
      {artifact?.can_manage && <><button className="page-button" disabled={busy || !!editor} onClick={() => { setNotice(''); setError(''); setRequestChanges(true) }}><MessageSquare size={16} />Request changes</button><button className="page-button page-button-primary" disabled={busy} onClick={openSharing}><Share2 size={16} />Share</button></>}
      {publicToken && <a className="page-button page-button-primary" href={pageViewUrl(contentUrl, 'full')} target="_blank" rel="noreferrer"><ArrowUpRight size={16} />Open full page</a>}
    </div>}</header>
    {!sharing && !requestChanges && !confirmDelete && !editor && feedback}
    {loading && <p role="status" className="pages-loading">Loading your page…</p>}
    {!loading && !artifact && !publicInfo && <div className="pages-empty"><FileText size={32} /><h2>Page unavailable</h2><p>{publicToken ? 'This link may have been removed. Ask the owner for a current link.' : 'The page may have been removed, or your access may have changed.'}</p><button className="page-button" onClick={() => setAttempt(n => n + 1)}>Try again</button></div>}
    {!loading && (artifact || publicInfo) && <>
      {artifact && <div className="page-revision-bar">{artifact.can_manage ? <label>Version<select aria-label="Page version" disabled={busy || !!editor} value={selected} onChange={e => setSelected(e.target.value)}>{artifact.revisions.map((r, index) => <option key={r.uuid} value={r.uuid}>Version {r.version ?? index + 1}{isPublished(r.uuid) ? ' · published' : ''}{r.uuid === artifact.latest_revision ? ' · latest' : ''}</option>)}</select></label> : <span>Shared version {version}</span>}<a className="page-text-button" href={pageViewUrl(contentUrl, 'full')} target="_blank" rel="noreferrer"><ArrowUpRight size={14} />Open full page</a></div>}
      {hasDraft && publishedVersion > 0 && !selectedIsPublished && <p className="page-revision-note">You’re previewing version {version}. The public link still shows version {publishedVersion}. Share → Publish updates when you’re ready.</p>}
      {!!revision?.warnings.length && <div className="page-revision-note"><strong>Some content was removed to keep this page safe.</strong>{revision.warnings.map(w => <p key={w}>{w}</p>)}</div>}
      <PagePreview key={contentUrl} src={contentUrl} title={title} />
      {artifact?.source && <nav aria-label="Page source" className="page-source">
        {artifact.source.conversation_uuid && <a href={`/?conversation=${encodeURIComponent(artifact.source.conversation_uuid)}${artifact.source.project_uuid ? `&project=${encodeURIComponent(artifact.source.project_uuid)}` : ''}`}><MessageSquare size={14} />Open originating chat</a>}
        {artifact.source.workflow_id && <a href={`/?mode=files&workflow=${encodeURIComponent(artifact.source.workflow_id)}${artifact.source.session_id ? `&run=${encodeURIComponent(artifact.source.session_id)}` : ''}${artifact.source.project_uuid ? `&project=${encodeURIComponent(artifact.source.project_uuid)}` : ''}`}><Workflow size={14} />Open originating workflow run</a>}
        <span>Saved in Files → Pages</span>
      </nav>}
      {artifact?.can_manage && uuid && <>
        {editor && <section className="page-editor" aria-label="HTML editor"><h2>Edit page HTML</h2>{!sharing && !confirmDelete && feedback}<p>Saving creates a new version. Your published page stays unchanged until you publish the update.</p><label>Title<input autoFocus maxLength={200} disabled={busy} value={editor.title} onChange={e => setEditor({ ...editor, title: e.target.value })} /></label><label>HTML<textarea spellCheck={false} disabled={busy} value={editor.html} onChange={e => setEditor({ ...editor, html: e.target.value })} /></label><div className="page-actions"><button className="page-button page-button-primary" disabled={busy} onClick={() => void action(async () => { const saved = await api.reviseArtifact(uuid, editor.title, editor.html, editor.base); await reload(); setSelected(saved.latest_revision); setEditor(null); setNotice('New version saved. Your public link has not changed.') })}>{busy ? 'Saving…' : 'Save new version'}</button><button className="page-button" disabled={busy} onClick={() => setEditor(null)}>Cancel edit</button></div></section>}
        <details className="page-advanced"><summary>Advanced page options</summary><p>Pages support static HTML and CSS. Scripts, forms and remote assets are blocked.</p><div className="page-actions">{!editor && <button className="page-button" disabled={busy} onClick={() => void action(async () => { const source = await api.artifactSource(uuid, selected); setEditor({ ...source, base: artifact.latest_revision }) })}><Code2 size={16} />Edit HTML</button>}<button className="page-button page-button-danger" disabled={busy} onClick={() => { setNotice(''); setError(''); setConfirmDelete(true) }}><Trash2 size={16} />Delete page</button></div></details>
      </>}
    </>}
    {sharing && artifact?.can_manage && uuid && <PageDialog title="Share page" onClose={closeSharing} busy={busy}>
      <p>Choose who can open <strong>{title}</strong>.</p>{feedback}
      <dl className="page-share-summary" aria-label="Current audience versions">
        <div><dt>Your team sees:</dt><dd>{artifact.team_id ? `Version ${versionNumber(savedTeamRevision)}` : 'Not shared with a team'}</dd></div>
        <div><dt>Public link shows:</dt><dd>{publishedVersion ? `Version ${publishedVersion}` : 'Not published'}</dd></div>
        <div><dt>Latest saved:</dt><dd>Version {latestVersion}</dd></div>
      </dl>
      <section className="page-share-section"><h3><LockKeyhole size={17} />Workspace access</h3><p>This link opens the saved page for you{artifact.team_id ? ' and your team' : ''}. It does not make the page public.</p>
        <label>Who can access<select aria-label="Workspace page access" value={team} disabled={busy || teamError} onChange={e => setTeam(e.target.value)}><option value="">Only me</option>{teams.map(t => <option key={t.uuid} value={t.uuid}>{t.name}</option>)}</select></label>
        {team && <><label>Version shared with team<select aria-label="Version shared with team" value={teamRevision} disabled={busy} onChange={e => setTeamRevision(e.target.value)}>{artifact.revisions.map((r, index) => <option key={r.uuid} value={r.uuid}>Version {r.version ?? index + 1}{artifact.team_id && r.uuid === savedTeamRevision ? ' · shared with team' : ''}{r.uuid === artifact.latest_revision ? ' · latest saved' : ''}</option>)}</select></label><p>Team members can view and download only the selected version. Other versions and future drafts stay owner-only until you select a different version and save access. This does not change the public link.</p>{artifact.team_revision && <p>Currently shared: version {versionNumber(artifact.team_revision)}.</p>}</>}
        {teamError && <p role="alert">Team options could not be loaded. <button className="underline" onClick={() => void action(async () => { setTeams(await listTeams()); setTeamError(false) })}>Retry teams</button></p>}
        {accessDirty && <p id="page-unsaved-access" role="status">You have unsaved workspace access changes. Save access or discard these changes before publishing.</p>}
        <div className="page-actions"><button className="page-button" disabled={busy || teamError || !accessDirty} onClick={() => void action(async () => { await api.shareArtifactTeam(uuid, team || null, team ? teamRevision : undefined); await reload(true); setNotice('Workspace access updated.') })}>Save access</button>{accessDirty && <button className="page-button" disabled={busy} onClick={discardAccessChanges}>Discard access changes</button>}<button className="page-button" disabled={busy} onClick={() => copy(`${window.location.origin}/pages/${uuid}`, 'Workspace link copied. The recipient still needs access.')}><Copy size={15} />Copy private link</button></div>
      </section>
      <section className="page-share-section"><h3><Globe2 size={17} />Main public link {publishedVersion > 0 && <PageBadge published>Version {publishedVersion} is live</PageBadge>}</h3>
        <p>Before publishing, compare figures and source notes with the original documents. Saving a page does not verify its accuracy.</p>
        <p>{publishedVersion ? `Anyone with this link can view version ${publishedVersion}. Saving edits does not change this link.` : `Publish version ${publicVersion} so anyone with its link can view it. Check the page for private information before publishing.`}</p>
        {hasDraft && publishedVersion > 0 && <p className="page-revision-note">Version {latestVersion} is newer than the published version.</p>}
        <label>Version to publish<select aria-label="Version to publish" value={publicRevision} disabled={busy || !!editor || !artifact.public_sharing_enabled} onChange={e => setPublicRevision(e.target.value)}>{artifact.revisions.map((r, index) => <option key={r.uuid} value={r.uuid}>Version {r.version ?? index + 1}{r.uuid === artifact.published_revision ? ' · public now' : ''}{r.uuid === artifact.latest_revision ? ' · latest saved' : ''}</option>)}</select></label>
        <p>Publishing updates changes what everyone sees at the main public link. To keep a version available at its own fixed link, choose Publish as separate link below. Team access stays unchanged.</p>
        <a className="page-text-button" href={api.artifactContentUrl(uuid, publicRevision)} target="_blank" rel="noreferrer"><ArrowUpRight size={14} />Preview version {publicVersion}</a>
        {publicLink && <div className="page-share-link"><label>Published page link<input aria-label="Published page link" readOnly value={publicLink} onFocus={e => e.target.select()} /></label><button className="page-icon-button" aria-label="Copy public link" disabled={busy} onClick={() => copy(publicLink, 'Public link copied.')}><Copy size={17} /></button></div>}
        <div className="page-actions"><button className="page-button page-button-primary" disabled={busy || !!editor || !artifact.public_sharing_enabled || publicSelectionIsPublished || accessDirty} aria-describedby={accessDirty ? 'page-unsaved-access' : undefined} onClick={() => void action(async () => { await api.publishArtifact(uuid, publicRevision); await reload(); setNotice(`Version ${publicVersion} published. Anyone with the link can view it.`) })}>{publicSelectionIsPublished ? <><Check size={16} />Published</> : publishedVersion ? `Publish updates · version ${publicVersion}` : `Publish version ${publicVersion}`}</button>{publicLink && <a className="page-button" href={`/a/${artifact.public_token}`} target="_blank" rel="noreferrer"><ArrowUpRight size={16} />Open published page</a>}</div>
        {artifact.public_sharing_enabled === false && <p>Public sharing is disabled on this deployment.</p>}
        {editor && <p>Save or cancel your HTML edits before publishing.</p>}
        {publicLink && <button className="page-text-button mt-3" disabled={busy} onClick={() => void action(async () => { await api.unpublishArtifact(uuid); await reload(); setNotice('Public link removed. Downloaded copies cannot be recalled.') })}><Link2 size={14} />Remove public link</button>}
      </section>
      <PageVersionLinks artifact={artifact} revision={publicRevision} busy={busy}
        publishDisabled={!!editor || !artifact.public_sharing_enabled || accessDirty}
        onPublish={() => void action(async () => {
          await api.publishArtifactVersion(uuid, publicRevision)
          await reload()
          setNotice(`Version ${publicVersion} has its own public link. Other public links are unchanged.`)
        })}
        onRemove={revision => void action(async () => {
          await api.unpublishArtifactVersion(uuid, revision)
          await reload()
          setNotice(`Version ${versionNumber(revision)} link removed. Other public links are unchanged. Downloaded copies cannot be recalled.`)
        })}
        onCopy={url => copy(url, 'Version link copied.')} />
    </PageDialog>}
    {requestChanges && uuid && artifact?.can_manage && <PageDialog title="Request changes" onClose={() => setRequestChanges(false)}>
      <p>Describe what you’d like to change in <strong>{title}</strong>. You’ll review the message in chat before sending it.</p>{feedback}<label className="block text-sm font-medium">What would you like to change?<textarea className="mt-2 min-h-36 w-full rounded-lg border border-slate-300 p-3 text-sm" value={changes} maxLength={8000} onChange={e => setChanges(e.target.value)} placeholder="Make the funding summary easier to scan, add a next-steps section…" autoFocus /></label><div className="page-actions"><button className="page-button page-button-primary" disabled={!changes.trim()} onClick={() => { try { sessionStorage.setItem(`pages:edit-request:${uuid}`, changes.trim()); window.location.assign(chatUrl) } catch { setError('Could not open chat. Copy your request and return to the originating chat.') } }}><MessageSquare size={16} />Continue in chat</button><button className="page-button" onClick={() => setRequestChanges(false)}>Cancel</button></div>
    </PageDialog>}
    {confirmDelete && uuid && artifact?.can_manage && <PageDialog title="Delete this page?" busy={busy} onClose={() => setConfirmDelete(false)}><p>This deletes every saved version of <strong>{title}</strong> and removes all its public links. This cannot be undone.</p>{feedback}<div className="page-actions"><button className="page-button" disabled={busy} autoFocus onClick={() => setConfirmDelete(false)}>Keep page</button><button className="page-button page-button-danger" disabled={busy} onClick={() => void action(async () => { await api.deleteArtifact(uuid); window.location.assign(backUrl) })}>Delete permanently</button></div></PageDialog>}
  </div></main>
}
