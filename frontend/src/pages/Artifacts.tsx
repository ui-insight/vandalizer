import { useEffect, useRef, useState } from 'react'
import * as api from '../api/artifacts'
import { PagesBrowser } from '../components/artifacts/PagesBrowser'
import { listTeams } from '../api/teams'

const buttonStyle = 'rounded border border-gray-300 bg-white px-3 py-2 text-sm hover:bg-gray-100 disabled:opacity-50'
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Could not complete this action. Please try again.'

export function ArtifactsHome() {
  return <main className="mx-auto max-w-5xl p-4 text-gray-900"><a href="/?mode=files" className="underline">Back to Files</a><PagesBrowser /></main>
}

export default function ArtifactPage({ uuid, publicToken }: { uuid?: string; publicToken?: string }) {
  const [artifact, setArtifact] = useState<api.Artifact | null>(null)
  const [publicInfo, setPublicInfo] = useState<{ title: string; revision: string } | null>(null)
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  const [loading, setLoading] = useState(true)
  const [editor, setEditor] = useState<{ title: string; html: string; base: string } | null>(null)
  const [teams, setTeams] = useState<{ uuid: string; name: string }[]>([])
  const [team, setTeam] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  useEffect(() => {
    let live = true
    setLoading(true); setError(''); setArtifact(null); setPublicInfo(null); setEditor(null)
    const load = async () => {
      try {
        if (publicToken) { const info = await api.getPublicArtifact(publicToken); if (live) setPublicInfo(info) }
        else if (uuid) { const item = await api.getArtifact(uuid); if (live) { setArtifact(item); setSelected(item.latest_revision); setTeam(item.team_id || '') }
          if (item.can_manage) { const all = await listTeams(); if (live) setTeams(all) }
        }
      } catch (e) { if (live) setError(errorMessage(e)) }
      finally { if (live) setLoading(false) }
    }
    void load(); return () => { live = false }
  }, [uuid, publicToken])
  const action = async (fn: () => Promise<void>) => {
    if (pending.current) return
    pending.current = true; setBusy(true); setError(''); setNotice('')
    try { await fn() } catch (e) { setError(errorMessage(e)) } finally { pending.current = false; setBusy(false) }
  }
  const reload = async () => { if (uuid) { const item = await api.getArtifact(uuid); setArtifact(item); setTeam(item.team_id || ''); return item } }
  const revision = artifact?.revisions.find(r => r.uuid === selected)
  const contentUrl = publicToken ? api.publicArtifactContentUrl(publicToken) : uuid && selected ? api.artifactContentUrl(uuid, selected) : ''
  const title = publicInfo?.title || revision?.title || artifact?.title || 'Artifact'
  return <main className="mx-auto max-w-7xl p-4 text-gray-900 sm:p-6">
    {!publicToken && <a href="/artifacts" className="underline">All artifacts</a>}
    <h1 className="my-4 text-2xl font-semibold">{title}</h1>
    {loading && <p role="status">Loading artifact…</p>}
    {error && <p role="alert" className="my-3 rounded border border-red-200 bg-red-50 p-3">{error}</p>}
    {notice && <p role="status" className="my-3 rounded bg-green-50 p-3">{notice}</p>}
    {!loading && (artifact || publicInfo) && <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {artifact && <label>Revision <select aria-label="Artifact revision" className="rounded border p-2" disabled={busy || !!editor} value={selected} onChange={e => setSelected(e.target.value)}>{artifact.revisions.map((r, index) => <option key={r.uuid} value={r.uuid}>{index + 1}{r.uuid === artifact.published_revision ? ' · published' : ''}{r.uuid === artifact.latest_revision ? ' · latest' : ''}</option>)}</select></label>}
        <a className={buttonStyle} href={`${contentUrl}?download=true`}>Download HTML</a>
        <a className={buttonStyle} href={contentUrl} target="_blank" rel="noreferrer">Open full page</a>
        {!publicToken && <button className={buttonStyle} onClick={() => void action(async () => { await navigator.clipboard.writeText(`${window.location.origin}/artifacts/${uuid}`); setNotice('Private link copied. Only you and the team you grant access can open it.') })}>Copy private link</button>}
        <span className="text-sm text-gray-600">{publicToken ? 'Published page · anyone with the link' : artifact?.team_id ? 'Private · team access enabled' : 'Private · only you'}</span>
      </div>
      {revision?.warnings.map(w => <p key={w} className="mb-3 text-sm text-amber-800">{w}</p>)}
      {artifact?.source && <nav aria-label="Page source" className="mb-3 flex flex-wrap gap-3 text-sm">
        {artifact.source.conversation_uuid && <a className="underline" href={`/?conversation=${encodeURIComponent(artifact.source.conversation_uuid)}${artifact.source.project_uuid ? `&project=${encodeURIComponent(artifact.source.project_uuid)}` : ''}`}>Open originating chat</a>}
        {artifact.source.workflow_id && <a className="underline" href={`/?mode=files&workflow=${encodeURIComponent(artifact.source.workflow_id)}${artifact.source.session_id ? `&run=${encodeURIComponent(artifact.source.session_id)}` : ''}${artifact.source.project_uuid ? `&project=${encodeURIComponent(artifact.source.project_uuid)}` : ''}`}>Open originating workflow run</a>}
      </nav>}
      <iframe key={contentUrl} src={contentUrl} title="Artifact preview" sandbox="" referrerPolicy="no-referrer" className="h-[65vh] min-h-80 w-full rounded-xl border bg-white" />
      {artifact?.can_manage && uuid && <section className="mt-6 space-y-4 rounded-xl border p-4">
        <p className="text-sm text-gray-600">Static HTML/CSS only. Scripts, forms, and remote assets are blocked. Review the preview before sharing. Public links show only the revision you publish; later edits require publishing again.</p>
        {!editor && <button className={buttonStyle} disabled={busy} onClick={() => void action(async () => { const source = await api.artifactSource(uuid, selected); setEditor({ ...source, base: artifact.latest_revision }) })}>Edit HTML</button>}
        {editor && <div className="space-y-3">
          <label className="block">Title<input className="mt-1 block w-full rounded border p-2" maxLength={200} value={editor.title} onChange={e => setEditor({ ...editor, title: e.target.value })} /></label>
          <label className="block">HTML<textarea className="mt-1 block h-80 w-full rounded border p-2 font-mono text-sm" value={editor.html} onChange={e => setEditor({ ...editor, html: e.target.value })} /></label>
          <div className="flex gap-2"><button className={buttonStyle} disabled={busy} onClick={() => void action(async () => { const saved = await api.reviseArtifact(uuid, editor.title, editor.html, editor.base); await reload(); setSelected(saved.latest_revision); setEditor(null); setNotice('New revision saved. Review it before publishing.') })}>Save new revision</button><button className={buttonStyle} disabled={busy} onClick={() => setEditor(null)}>Cancel edit</button></div>
        </div>}
        <div className="flex flex-wrap items-center gap-3"><label>Private access <select aria-label="Private artifact access" className="rounded border p-2" value={team} onChange={e => setTeam(e.target.value)}><option value="">Only me</option>{teams.map(t => <option key={t.uuid} value={t.uuid}>{t.name}</option>)}</select></label><button className={buttonStyle} disabled={busy} onClick={() => void action(async () => { await api.shareArtifactTeam(uuid, team || null); await reload(); setNotice('Private access updated.') })}>Save access</button></div>
        <div className="space-y-3 border-t pt-4"><h2 className="font-semibold">Public link</h2><p className="text-sm">Publishing exposes this selected page to anyone with the link, including any source quotations you included. It does not grant access to the source workspace.</p>
          <button className={buttonStyle} disabled={busy || !!editor || !artifact.public_sharing_enabled} onClick={() => void action(async () => { await api.publishArtifact(uuid, selected); await reload(); setNotice('Selected revision published.') })}>Publish selected revision</button>
          {artifact.public_sharing_enabled === false && <p className="text-sm">Public sharing is disabled on this deployment.</p>}
          {artifact.public_token && <div className="flex flex-wrap gap-3"><a className="break-all underline" href={`/a/${artifact.public_token}`} target="_blank" rel="noreferrer">Open published page</a><button className={buttonStyle} disabled={busy} onClick={() => void action(async () => { await navigator.clipboard.writeText(`${window.location.origin}/a/${artifact.public_token}`); setNotice('Public link copied.') })}>Copy public link</button><button className={buttonStyle} disabled={busy} onClick={() => void action(async () => { await api.unpublishArtifact(uuid); await reload(); setNotice('Public link revoked. Previously downloaded copies cannot be recalled.') })}>Unpublish and revoke link</button></div>}
        </div>
        <div className="border-t pt-4">{confirmDelete ? <><p className="mb-2">Delete every revision and revoke all links? This cannot be undone.</p><button className={buttonStyle} disabled={busy} onClick={() => void action(async () => { await api.deleteArtifact(uuid); window.location.assign('/artifacts') })}>Delete permanently</button><button className={buttonStyle} disabled={busy} onClick={() => setConfirmDelete(false)}>Keep artifact</button></> : <button className={buttonStyle} disabled={busy} onClick={() => setConfirmDelete(true)}>Delete artifact</button>}</div>
      </section>}
    </>}
  </main>
}
