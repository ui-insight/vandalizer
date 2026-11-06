import { useEffect, useState } from 'react'
import { ArrowRight, Paintbrush } from 'lucide-react'
import * as api from '../../api/artifacts'

type Revision = api.Artifact['revisions'][number]

/** Pick two saved versions of a Page and see what changed between them. */
export function PageCompare({ uuid, revisions, versionNumber }: { uuid: string; revisions: Revision[]; versionNumber: (id: string) => number }) {
  const [base, setBase] = useState(revisions[revisions.length - 2]?.uuid ?? '')
  const [target, setTarget] = useState(revisions[revisions.length - 1]?.uuid ?? '')
  const [result, setResult] = useState<api.PageComparison | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    if (!base || !target || base === target) { setResult(null); return }
    let live = true
    setLoading(true); setError('')
    api.compareArtifactVersions(uuid, base, target)
      .then(r => { if (live) setResult(r) })
      .catch(e => { if (live) { setResult(null); setError(e instanceof Error ? e.message : 'Could not compare these versions.') } })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [uuid, base, target])
  const option = (r: Revision) => <option key={r.uuid} value={r.uuid}>Version {versionNumber(r.uuid)}</option>
  const nothing = result && !result.numbers.length && !result.sections_added.length && !result.sections_removed.length && !result.text.length && !result.design.length && !result.title
  return <section className="page-compare" aria-label="Compare versions">
    <div className="page-compare-pick">
      <label>From<select aria-label="Compare from version" value={base} onChange={e => setBase(e.target.value)}>{revisions.map(option)}</select></label>
      <ArrowRight size={16} aria-hidden />
      <label>To<select aria-label="Compare to version" value={target} onChange={e => setTarget(e.target.value)}>{revisions.map(option)}</select></label>
    </div>
    {base === target && <p className="page-compare-note">Choose two different versions.</p>}
    {loading && <p role="status" className="page-compare-note">Comparing…</p>}
    {error && <p role="alert" className="page-alert">{error}</p>}
    {result && !loading && <div aria-live="polite">
      <p className="page-compare-summary"><strong>Version {result.base.version} → Version {result.target.version}:</strong> {result.summary}</p>
      {nothing && <p className="page-compare-note">These versions look the same.</p>}
      {result.title && <p>Title: <del>{result.title.old}</del> → <ins>{result.title.new}</ins></p>}
      {!!result.numbers.length && <>
        <h3>Changed figures</h3>
        <table className="page-compare-table">
          <thead><tr><th scope="col">Figure</th><th scope="col">Version {result.base.version}</th><th scope="col">Version {result.target.version}</th></tr></thead>
          <tbody>{result.numbers.map((n, i) => <tr key={`${n.label}-${i}`}>
            <th scope="row">{n.label}{n.section ? <span className="page-compare-section"> · {n.section}</span> : null}</th>
            <td><del>{n.old}</del></td><td><ins>{n.new}</ins></td>
          </tr>)}</tbody>
        </table>
      </>}
      {(!!result.sections_added.length || !!result.sections_removed.length) && <>
        <h3>Sections</h3>
        <ul>
          {result.sections_added.map(s => <li key={`a-${s}`}><ins>Added: {s}</ins></li>)}
          {result.sections_removed.map(s => <li key={`r-${s}`}><del>Removed: {s}</del></li>)}
        </ul>
      </>}
      {!!result.text.length && <>
        <h3>Text changes</h3>
        <ul>{result.text.map((t, i) => <li key={i}>
          <span className="page-compare-label">{t.label}{t.section ? ` · ${t.section}` : ''}</span>
          {t.old && <> <del>{t.old}</del></>}{t.old && t.new && ' → '}{t.new && <ins>{t.new}</ins>}
        </li>)}</ul>
      </>}
      {!!result.design.length && <>
        <h3><Paintbrush size={14} aria-hidden /> Design only</h3>
        <ul>{result.design.map(d => <li key={d}>{d}</li>)}</ul>
      </>}
      {result.truncated && <p className="page-compare-note">Showing the first 60 changes of each kind.</p>}
    </div>}
  </section>
}
