import { useEffect, useRef, useState } from 'react'
import { FileText, Layers, Plus } from 'lucide-react'
import * as api from '../../api/pageTemplates'
import { searchDocuments, type SearchResult } from '../../api/documents'
import { listTeams } from '../../api/teams'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { PageBadge, PageDialog, PagePreview } from './PagePrimitives'

const message = (e: unknown) => e instanceof Error ? e.message : 'Could not complete this action.'

export function TemplatesBrowser() {
  const { sendChatMessage, triggerNewChat, setWorkspaceMode } = useWorkspace()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.browsePageTemplates>> | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [using, setUsing] = useState<api.PageTemplate | null>(null)
  const [sharing, setSharing] = useState<api.PageTemplate | null>(null)
  const [removing, setRemoving] = useState<api.PageTemplate | null>(null)
  const [teams, setTeams] = useState<{ uuid: string; name: string }[]>([])
  const [team, setTeam] = useState('')
  const [teamsReady, setTeamsReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  useEffect(() => {
    let live = true
    setError(''); setResult(null)
    const timer = setTimeout(() => { api.browsePageTemplates(search, page).then(r => { if (live) { const last = Math.max(1, Math.ceil(r.total / r.page_size)); if (page > last) setPage(last); else setResult(r) } }).catch(e => { if (live) setError(message(e)) }) }, 200)
    return () => { live = false; clearTimeout(timer) }
  }, [search, page, refresh])
  useEffect(() => {
    const reload = () => setRefresh(n => n + 1)
    window.addEventListener('focus', reload)
    return () => window.removeEventListener('focus', reload)
  }, [])
  useEffect(() => {
    if (!sharing) return
    let live = true
    setTeam(sharing.team_id || ''); setTeamsReady(false); setError('')
    listTeams().then(value => { if (live) { setTeams(value); setTeamsReady(true) } }).catch(e => { if (live) setError(message(e)) })
    return () => { live = false }
  }, [sharing])
  const act = async (work: () => Promise<void>) => {
    if (pending.current) return
    pending.current = true; setBusy(true); setError('')
    try { await work(); setRefresh(n => n + 1) } catch (e) { setError(message(e)) }
    finally { pending.current = false; setBusy(false) }
  }
  return <section className="pages-library" aria-label="Page templates">
    <header className="pages-library-heading"><div><p className="page-eyebrow">REUSABLE DESIGNS</p><h2>Templates</h2></div><a className="page-button" href="/?mode=files&files=pages"><Plus size={16} />Save a Page as template</a></header>
    <p className="pages-library-intro">Keep a design, then build a new private Page from a different file. Templates contain empty data fields.</p>
    <div className="pages-toolbar"><label className="pages-search">Search templates<input type="search" value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder="Find a design…" /></label></div>
    {error && !sharing && !removing && <p role="alert" className="page-alert">{error} <button onClick={() => setRefresh(n => n + 1)}>Retry templates</button></p>}
    {!result && !error && <p role="status">Loading templates…</p>}
    {result && <>
      {!result.items.length && <div className="pages-empty"><Layers size={30} /><h3>{search ? 'No matching templates' : 'Save a design you want to use again'}</h3><p>Choose Save as template on a chat Page preview or a saved Page.</p></div>}
      <ul className="pages-results">{result.items.map(item => <li key={item.uuid} className="page-library-card">
        <div className="page-card-cover"><PagePreview title={item.name} src={api.pageTemplateContentUrl(item.uuid)} thumbnail /></div>
        <div className="page-card-body"><h3 className="page-card-title">{item.name}</h3><p>{item.description || 'Reusable Page design'}</p><div className="page-card-meta"><PageBadge>{item.team_id ? 'Team' : 'Private'}</PageBadge><span>By {item.owner_name}</span></div>
          <button className="page-button page-button-primary mt-3" onClick={() => setUsing(item)}>Use template</button>
          {item.can_manage && <div className="page-actions mt-3"><button className="page-text-button" onClick={() => setSharing(item)}>Share template</button><button className="page-text-button" onClick={() => setRemoving(item)}>Delete template</button></div>}
        </div>
      </li>)}</ul>
      {result.total > 20 && <nav className="pages-pagination" aria-label="Templates pagination"><button className="page-button" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous</button><span>Page {page} of {Math.ceil(result.total / 20)}</span><button className="page-button" disabled={page * 20 >= result.total} onClick={() => setPage(n => n + 1)}>Next</button></nav>}
    </>}
    {using && <UsePageTemplate template={using} onClose={() => setUsing(null)} onUse={file => {
      const template = using
      triggerNewChat()
      setWorkspaceMode('chat')
      sendChatMessage(`Use [the selected Page template](?mode=files&files=templates&template=${encodeURIComponent(template.uuid)}) with the attached file. Fill values only from this file, mark missing information “Not in this file”, and show the checked preview before saving a new private Page.`, { documentUuids: [file.uuid] })
      setUsing(null)
    }} />}
    {sharing && <PageDialog title="Share template" onClose={() => setSharing(null)} busy={busy}><p>Choose who can use {sharing.name}. Sharing this design does not share its original Page or files.</p>{error && <p role="alert">{error}</p>}<div className="page-card-form"><label>Template access<select value={team} disabled={busy || !teamsReady} onChange={e => setTeam(e.target.value)}><option value="">Only me</option>{teams.map(t => <option key={t.uuid} value={t.uuid}>{t.name}</option>)}</select></label></div><button className="page-button page-button-primary" disabled={busy || !teamsReady} onClick={() => void act(async () => { await api.sharePageTemplate(sharing.uuid, team || null); setSharing(null) })}>Save access</button></PageDialog>}
    {removing && <PageDialog title="Delete template?" onClose={() => setRemoving(null)} busy={busy}><p>Delete {removing.name}? Pages already made from it stay available.</p>{error && <p role="alert">{error}</p>}<button className="page-button" disabled={busy} onClick={() => setRemoving(null)}>Keep template</button><button className="page-button page-button-danger" disabled={busy} onClick={() => void act(async () => { await api.deletePageTemplate(removing.uuid); setRemoving(null) })}>Delete template</button></PageDialog>}
  </section>
}

function UsePageTemplate({ template, onClose, onUse }: { template: api.PageTemplate; onClose: () => void; onUse: (file: SearchResult) => void }) {
  const [search, setSearch] = useState('')
  const [files, setFiles] = useState<SearchResult[]>([])
  const started = useRef(false)
  const [selected, setSelected] = useState<SearchResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let live = true
    setLoading(true); setError('')
    const timer = setTimeout(() => { searchDocuments(search, 100).then(r => { if (live) setFiles(r.items) }).catch(e => { if (live) setError(message(e)) }).finally(() => { if (live) setLoading(false) }) }, 200)
    return () => { live = false; clearTimeout(timer) }
  }, [search, attempt])
  return <PageDialog title={`Use ${template.name}`} onClose={onClose}>
    <p>Choose the new file. A new chat will build a private preview using this design and values from that file only.</p>
    <label>Search files<input className="block border p-2 rounded w-full" type="search" value={search} onChange={e => setSearch(e.target.value)} /></label>
    {loading ? <p role="status">Loading files…</p> : error ? <p role="alert">{error} <button onClick={() => setAttempt(n => n + 1)}>Retry files</button></p> : <ul className="max-h-64 overflow-auto my-3">{files.map(file => <li key={file.uuid}><label className="flex gap-2 p-2"><input type="radio" name="template-file" checked={selected?.uuid === file.uuid} onChange={() => setSelected(file)} /><FileText size={16} />{file.title}</label></li>)}{!files.length && <li>No files found. Upload a file in Documents first.</li>}</ul>}
    {!loading && files.length >= 100 && <p>Showing up to 100 files. Search by name to narrow the list.</p>}
    {selected && <p>Selected: {selected.title}</p>}
    <div className="page-actions"><button className="page-button page-button-primary" disabled={!selected} onClick={() => { if (selected && !started.current) { started.current = true; onUse(selected) } }}>Build Page preview</button><button className="page-button" onClick={onClose}>Cancel</button></div>
  </PageDialog>
}
