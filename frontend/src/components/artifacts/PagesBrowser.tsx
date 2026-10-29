import { useEffect, useRef, useState } from 'react'
import { ArrowUpRight, FileText, FolderOpen, Loader2, MessageSquare, Plus, Search, Workflow } from 'lucide-react'
import { artifactContentUrl, browseArtifacts, createArtifact, type ArtifactPageResult } from '../../api/artifacts'
import { addProjectPin } from '../../api/projects'
import { PageBadge, PageDialog, PagePreview } from './PagePrimitives'
import { announceWorkspaceWrite, useRefreshOnChatWrite } from '../../lib/chatWrites'
import { PageCardActions, type PageCardNotice } from './PageCardActions'

const message = (e: unknown) => e instanceof Error ? e.message : 'Could not load pages. Please try again.'
function readView(key: string) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || '{}')
    return { search: typeof saved.search === 'string' ? saved.search : '', sort: ['updated', 'newest', 'title'].includes(saved.sort) ? saved.sort as string : 'updated', page: Number.isInteger(saved.page) && saved.page > 0 ? saved.page as number : 1 }
  } catch { return { search: '', sort: 'updated', page: 1 } }
}

export function PagesBrowser({ projectUuid, canManage = false }: { projectUuid?: string; canManage?: boolean }) {
  const storageKey = `pages:view:${projectUuid || 'all'}`
  const [initial] = useState(() => readView(storageKey))
  const [search, setSearch] = useState(initial.search)
  const [query, setQuery] = useState(initial.search.trim())
  const [sort, setSort] = useState(initial.sort)
  const [page, setPage] = useState(initial.page)
  const [starting, setStarting] = useState(false)
  const [adding, setAdding] = useState(false)
  const [result, setResult] = useState<ArtifactPageResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState<PageCardNotice | null>(null)
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const request = useRef(crypto.randomUUID())
  const pending = useRef(false)
  useRefreshOnChatWrite('pages', () => setRefresh(n => n + 1))
  useEffect(() => {
    const refreshPages = () => setRefresh(n => n + 1)
    window.addEventListener('focus', refreshPages)
    return () => window.removeEventListener('focus', refreshPages)
  }, [])
  useEffect(() => { const timer = setTimeout(() => { if (search.trim() !== query) { setQuery(search.trim()); setPage(1) } }, 250); return () => clearTimeout(timer) }, [search, query])
  useEffect(() => { if (!adding) { try { sessionStorage.setItem(storageKey, JSON.stringify({ search, sort, page })) } catch { /* Storage is optional. */ } } }, [search, sort, page, storageKey, adding])
  useEffect(() => {
    let live = true
    setLoading(true); setError(''); setResult(null)
    browseArtifacts({ search: query, sort, page, project_uuid: adding ? undefined : projectUuid })
      .then(data => { if (live) { const lastPage = Math.max(1, Math.ceil(data.total / data.page_size)); if (page > lastPage) setPage(lastPage); else setResult(data) } })
      .catch(e => { if (live) setError(message(e)) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [query, sort, page, adding, projectUuid, refresh])
  const act = async (work: () => Promise<void>) => {
    if (pending.current) return
    pending.current = true; setBusy(true); setError('')
    try { await work() } catch (e) { setError(message(e)) }
    finally { pending.current = false; setBusy(false) }
  }
  const newPage = () => void act(async () => {
    const saved = await createArtifact('Untitled page', '<style>body{font:17px/1.7 system-ui;color:#263245;max-width:760px;margin:64px auto;padding:0 28px}h1{font-size:36px;line-height:1.2}</style><main><h1>Your next idea starts here.</h1><p>Use “Request changes” to describe the page you want, or open the HTML editor to make it your own.</p></main>', request.current, projectUuid)
    window.location.assign(`/pages/${saved.uuid}`)
  })
  return <section aria-label={projectUuid ? 'Project pages' : 'Saved pages'} className="pages-library">
    <header className="pages-library-heading"><div><p className="page-eyebrow">{projectUuid ? 'PROJECT LIBRARY' : 'YOUR LIBRARY'}</p><h2>{adding ? 'Add an existing page' : projectUuid ? 'Project pages' : 'Pages'}</h2></div><button className="page-button page-button-primary" disabled={busy} onClick={() => setStarting(true)}><Plus size={16} />{busy ? 'Working…' : 'New page'}</button></header>
    {starting && <PageDialog title="New page" onClose={() => setStarting(false)} busy={busy}><p>Start with a reusable design and a new file, or create a blank Page.</p>{error && <p role="alert">{error}</p>}<div className="page-actions"><a className="page-button page-button-primary" href="/?mode=files&files=templates">Start from template</a><button className="page-button" disabled={busy} onClick={newPage}>Create blank page</button></div></PageDialog>}
    <p className="pages-library-intro">Your finished work, ready to revisit and share. Pages from chat and workflows start private.</p>
    {projectUuid && canManage && <button className="page-button mb-4" disabled={busy} onClick={() => { setAdding(!adding); setSearch(''); setQuery(''); setPage(1) }}><FolderOpen size={16} />{adding ? 'Back to project pages' : 'Add existing page'}</button>}
    <div className="pages-toolbar"><label className="pages-search">Search pages<input type="search" placeholder="Find a page…" value={search} onChange={e => setSearch(e.target.value)} /></label><label>Sort pages<select value={sort} onChange={e => { setSort(e.target.value); setPage(1) }}><option value="updated">Recently updated</option><option value="newest">Newest first</option><option value="title">Title</option></select></label></div>
    {notice && <p role="status" className="page-notice">{notice.message}{notice.href && <> <a className="underline" href={notice.href}>Open copy</a></>}</p>}
    {error && <div role="alert" className="page-alert">{error} <button className="underline" onClick={() => setRefresh(n => n + 1)}>Retry pages</button></div>}
    {loading ? <p role="status" className="pages-loading"><Loader2 size={18} className="animate-spin" />Loading your pages…</p> : result && <>
      {!result.items.length && <div className="pages-empty">{query ? <Search size={30} /> : <FileText size={30} />}<h3>{query ? 'No pages match your search.' : 'A home for your finished work'}</h3><p>{query ? 'Try a different title, or clear the search to see all your pages.' : 'Ask the assistant to create a page, save a workflow result, or start with a blank page.'}</p>{query ? <button className="page-button" onClick={() => setSearch('')}>Clear search</button> : <button className="page-button page-button-primary" disabled={busy} onClick={() => setStarting(true)}><Plus size={16} />Create your first page</button>}</div>}
      <ul className="pages-results">{result.items.map(item => {
        const href = `/pages/${encodeURIComponent(item.uuid)}`
        const date = item.updated_at ? new Date(item.updated_at) : null
        const validDate = date && !Number.isNaN(date.getTime())
        const Origin = item.source?.kind === 'workflow' ? Workflow : MessageSquare
        return <li key={item.uuid} className="page-library-card">
          <a className="page-card-cover" href={href} aria-label={`Preview ${item.title}`}><PagePreview title={item.title} src={artifactContentUrl(item.uuid, item.latest_revision)} thumbnail /><span className="page-card-open">Open page <ArrowUpRight size={13} /></span></a>
          <div className="page-card-body"><a className="page-card-title" href={href}>{item.title}</a>
            <div className="page-card-meta"><PageBadge published={!!item.published_revision || !!item.publications?.length}>{item.published_revision || item.publications?.length ? 'Published' : item.team_id ? 'Team access' : 'Private'}</PageBadge><span className="text-xs text-slate-500">{item.revisions.length} version{item.revisions.length === 1 ? '' : 's'}</span></div>
            <p className="page-card-origin"><Origin size={12} />{item.source?.kind === 'workflow' ? 'From a workflow' : item.source?.kind === 'chat' ? 'From chat' : 'Created in Pages'}{item.source?.project_uuid && ' · Project page'}</p>
            <div className="page-card-footer"><time dateTime={item.updated_at} title={validDate ? date.toLocaleString() : undefined}>{validDate ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'Saved page'}</time><PageCardActions page={item} onError={error => { setNotice(null); setError(error) }} onChanged={(notice, refresh = true) => {
              setError(''); setNotice(notice); if (refresh) announceWorkspaceWrite('pages', 'projects')
            }} /></div>
            {adding && projectUuid && <button className="page-button mt-3 w-full" disabled={busy} onClick={() => void act(async () => { await addProjectPin(projectUuid, { pin_type: 'artifact', target_id: item.uuid }); setAdding(false); setPage(1); setSearch(''); setQuery(''); setRefresh(n => n + 1) })}>Add {item.title} to project</button>}
          </div>
        </li>
      })}</ul>
      {!!result.total && <nav aria-label="Pages pagination" className="pages-pagination"><button className="page-button" disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous</button><span>Page {page} of {Math.max(1, Math.ceil(result.total / result.page_size))} · {result.total} page{result.total === 1 ? '' : 's'}</span><button className="page-button" disabled={page * result.page_size >= result.total} onClick={() => setPage(n => n + 1)}>Next</button></nav>}
    </>}
  </section>
}
