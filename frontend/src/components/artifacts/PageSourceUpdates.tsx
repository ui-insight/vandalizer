import { FileSpreadsheet, RefreshCw } from 'lucide-react'
import type { PageSourceDocument } from '../../api/artifacts'

const versionLabel = (doc: { title: string; version_number: number }) =>
  doc.version_number > 1 ? `${doc.title} (version ${doc.version_number})` : doc.title

/** "Built from: …" — the files the latest version of a Page used. */
export function PageBuiltFrom({ sources }: { sources: PageSourceDocument[] }) {
  if (!sources.length) return null
  return <span className="page-built-from"><FileSpreadsheet size={14} />Built from: {sources.map(versionLabel).join(', ')}</span>
}

/** The request chat drafts when the owner clicks Update page. */
export function updateRequest(updated: PageSourceDocument[]): string {
  const lines = updated.map(source => {
    const latest = source.latest!
    const changes = source.changes?.items.length ? ` Changes found: ${source.changes.items.join('; ')}${source.changes.more ? `; and ${source.changes.more} more` : ''}.` : ''
    return `- “${source.title}” was replaced by version ${latest.version_number}, “${latest.title}” (attached).${changes}`
  })
  return `A source file for this page has a new version:\n${lines.join('\n')}\n\nUpdate the page from the new version. Re-read the attached file and change every value, chart, table, total, summary and source line that differs. Keep everything else as it is.`
}

/** "Source updated: review changes" with what changed and an Update page action. */
export function PageSourceUpdates({ sources, disabled, onUpdate }: { sources: PageSourceDocument[]; disabled?: boolean; onUpdate: (updated: PageSourceDocument[]) => void }) {
  const updated = sources.filter(s => s.status === 'updated')
  if (!updated.length) return null
  const usable = updated.filter(s => s.latest)
  const reading = usable.some(s => !s.latest!.ready)
  return <section className="page-source-update" aria-labelledby="page-source-update-title">
    <h2 id="page-source-update-title"><RefreshCw size={16} />Source updated: review changes</h2>
    {updated.map(source => <div key={source.uuid}>
      {source.latest
        ? <p><strong>{source.title}</strong> has a newer version: <strong>{versionLabel(source.latest)}</strong>.</p>
        : <p><strong>{source.title}</strong> has a newer version that you can’t open. Ask its owner for access to update this page.</p>}
      {source.latest && !source.latest.ready && <p>The new version is still being read. Its changes will appear here when it’s ready.</p>}
      {!!source.changes?.items.length && <ul aria-label={`Changes in ${source.latest?.title ?? source.title}`}>
        {source.changes.items.map(item => <li key={item}>{item}</li>)}
        {source.changes.more > 0 && <li>and {source.changes.more} more {source.changes.more === 1 ? 'change' : 'changes'}</li>}
      </ul>}
      {source.changes && !source.changes.items.length && source.latest?.ready && <p>No differences were found in the file’s text.</p>}
    </div>)}
    {!!usable.length && <div className="page-actions">
      <button className="page-button page-button-primary" disabled={disabled || reading} onClick={() => onUpdate(usable)}><RefreshCw size={16} />Update page</button>
      <span>Chat prepares the update from the new file. You review a preview before anything is saved; the public link changes only when you publish.</span>
    </div>}
  </section>
}
