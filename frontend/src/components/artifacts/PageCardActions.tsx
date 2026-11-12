import { useEffect, useRef, useState } from 'react'
import { deleteArtifact, duplicateArtifact, renameArtifact, type Artifact } from '../../api/artifacts'
import { addProjectPin, listProjects } from '../../api/projects'
import type { Project } from '../../types/project'
import { PageCardMenu, type PageCardAction } from './PageCardMenu'
import { PageDeleteDialog } from './PageDeleteDialog'
import { PageDialog } from './PagePrimitives'

export interface PageCardNotice { message: string; href?: string }
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Could not complete this action. Please try again.'

export function PageCardActions({ page, onChanged, onError }: {
  page: Artifact; onChanged: (notice: PageCardNotice, refresh?: boolean) => void; onError: (error: string) => void
}) {
  const [dialog, setDialog] = useState<'rename' | 'project' | 'delete' | null>(null)
  const [title, setTitle] = useState(page.title)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  const duplicateRequest = useRef(crypto.randomUUID())
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [project, setProject] = useState('')
  const [projectAttempt, setProjectAttempt] = useState(0)
  const publicLink = page.public_token ? { token: page.public_token, revision: page.published_revision }
    : [...(page.publications || [])].sort((a, b) => page.revisions.findIndex(r => r.uuid === b.revision) - page.revisions.findIndex(r => r.uuid === a.revision))[0]
  useEffect(() => {
    if (dialog !== 'project') return
    let live = true
    setProjects(null); setProject(''); setError('')
    listProjects().then(items => { if (live) setProjects(items.filter(item => item.role === 'owner' || item.role === 'editor')) })
      .catch(error => { if (live) { setProjects([]); setError(errorMessage(error)) } })
    return () => { live = false }
  }, [dialog, projectAttempt])
  const act = async (work: () => Promise<void>, modal = false) => {
    if (pending.current) return
    pending.current = true; setBusy(true); setError('')
    try { await work() } catch (error) { if (modal) setError(errorMessage(error)); else onError(errorMessage(error)) }
    finally { pending.current = false; setBusy(false) }
  }
  const action = (action: PageCardAction) => {
    setError('')
    if (action === 'duplicate') void act(async () => {
      const saved = await duplicateArtifact(page.uuid, duplicateRequest.current)
      duplicateRequest.current = crypto.randomUUID()
      onChanged({ message: `${saved.title} created as a private page.`, href: `/pages/${encodeURIComponent(saved.uuid)}` })
    })
    else if (action === 'copy' && publicLink) void act(async () => {
      await navigator.clipboard.writeText(`${window.location.origin}/a/${encodeURIComponent(publicLink.token)}`)
      const index = page.revisions.findIndex(r => r.uuid === publicLink.revision)
      const version = page.revisions[index]?.version ?? index + 1
      onChanged({ message: version > 0 ? `Public link for version ${version} copied.` : 'Public link copied.' }, false)
    })
    else if (action === 'rename') { setTitle(page.title); setDialog('rename') }
    else if (action === 'project') { setProject(''); setDialog('project') }
    else if (action === 'delete') setDialog('delete')
  }
  const feedback = error && <p role="alert" className="page-alert">{error}</p>
  return <>
    <PageCardMenu page={page} busy={busy} publicToken={publicLink?.token} onAction={action} />
    {dialog === 'rename' && <PageDialog title="Rename page" busy={busy} onClose={() => setDialog(null)}>
      <form className="page-card-form" onSubmit={event => { event.preventDefault(); if (title.trim()) void act(async () => {
        await renameArtifact(page.uuid, title.trim()); setDialog(null); onChanged({ message: 'Page renamed. No new version was created.' })
      }, true) }}>
        <label>Page name<input autoFocus required maxLength={200} value={title} disabled={busy} onChange={event => setTitle(event.target.value)} /></label>
        <p>This changes the name in your library. Saved versions and published copies keep their titles.</p>
        {feedback}<div className="page-actions"><button type="button" className="page-button" disabled={busy} onClick={() => setDialog(null)}>Cancel</button><button className="page-button page-button-primary" disabled={busy || !title.trim()}>{busy ? 'Renaming…' : 'Save name'}</button></div>
      </form>
    </PageDialog>}
    {dialog === 'project' && <PageDialog title="Add to project" busy={busy} onClose={() => setDialog(null)}>
      <form className="page-card-form" onSubmit={event => { event.preventDefault(); if (project) void act(async () => {
        await addProjectPin(project, { pin_type: 'artifact', target_id: page.uuid }); setDialog(null); onChanged({ message: 'Page added to project.' })
      }, true) }}>
        <p>Add <strong>{page.title}</strong> to a project you can edit. Project members still need access to the page.</p>
        {projects === null ? <p role="status">Loading projects…</p> : projects.length ? <label>Project<select autoFocus required value={project} disabled={busy} onChange={event => setProject(event.target.value)}><option value="">Choose a project</option>{projects.map(item => <option key={item.uuid} value={item.uuid}>{item.title}</option>)}</select></label> : !error && <p>No projects you can edit are available.</p>}
        {feedback}{error && <button type="button" className="page-text-button" disabled={busy} onClick={() => setProjectAttempt(n => n + 1)}>Reload projects</button>}
        <div className="page-actions"><button type="button" className="page-button" disabled={busy} onClick={() => setDialog(null)}>Cancel</button><button className="page-button page-button-primary" disabled={busy || !project || !projects?.length}>{busy ? 'Adding…' : 'Add page'}</button></div>
      </form>
    </PageDialog>}
    {dialog === 'delete' && <PageDeleteDialog title={page.title} busy={busy} feedback={feedback} onClose={() => setDialog(null)} onConfirm={() => void act(async () => {
      await deleteArtifact(page.uuid); setDialog(null); onChanged({ message: 'Page deleted.' })
    }, true)} />}
  </>
}
