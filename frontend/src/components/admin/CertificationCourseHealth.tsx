import { useState } from 'react'
import { getCertificationHealth, type CertificationHealthRow } from '../../api/certificationHealth'
import { useAdminQuery } from './shared/useAdminQuery'

const labels: Record<string, string> = {
  enrollments: 'Enrollment records', module_completions: 'Module completion requests',
  automatic_reviews: 'Automatic reviews', lab_runs: 'Lab runs',
  new_enrollment: 'New enrollment', explicit_upgrade: 'Optional upgrade',
  legacy_version_unknown: 'Historical version unknown', unknown: 'Unknown',
  start_failures: 'Start failures', save_refresh_failures: 'Save and refresh failures',
  grading_disputes: 'Grading disputes', abandonment_rate: 'Abandonment rate',
  resume_success: 'Resume success', bridge_uptake: 'Bridge uptake',
}
const label = (value: string) => labels[value] ?? value.replaceAll('_', ' ')

function HealthReport() {
  const { data, loading, error, load } = useAdminQuery(getCertificationHealth)
  const courses = new Map<string, CertificationHealthRow[]>()
  for (const row of data?.rows ?? []) {
    const key = JSON.stringify([row.course_version, row.manifest_sha256])
    courses.set(key, [...(courses.get(key) ?? []), row])
  }
  return <div style={{ marginTop: 12, overflowWrap: 'anywhere' }}>
    <p>All retained records, grouped by course version and exact package. Counts describe saved states, not unique learners or success rates. Reads can observe changes made while this report loads.</p>
    <button type="button" className="admin-open-record" disabled={loading} onClick={load}>Refresh course health</button>
    {loading && <p role="status">Loading course health…</p>}
    {error && <p role="alert">{error}</p>}
    {data && <>
      <p>Observed {new Date(data.observed_at).toLocaleString()}. No enrollment or assessment was changed.</p>
      <p>Prepared enrollments are not starts. Optional upgrades are not proof that a learner used the bridge. Rejected completion requests are not grading disputes; failed lab runs can be part of a recovery exercise. Saved completion states do not independently verify credentials.</p>
      {data.rows.length === 0 && <p>No records were found in the four monitored collections.</p>}
      {[...courses].map(([key, rows]) => <section key={key} style={{ marginTop: 16 }} aria-label={`Course health: ${rows[0].course_version ?? 'Unknown version'}`}>
        <h3 style={{ fontSize: 16 }}>{rows[0].course_version ?? 'Historical or missing course version'}</h3>
        <p style={{ fontSize: 12 }}>Package: {rows[0].manifest_sha256 ?? 'Unknown; not inferred from the installed course'}</p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead><tr><th scope="col" style={{ textAlign: 'left' }}>Record</th><th scope="col" style={{ textAlign: 'left' }}>Saved state</th><th scope="col" style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>Count</th></tr></thead>
          <tbody>{rows.map(row => <tr key={`${row.source}:${row.provenance}:${row.state}`}>
            <th scope="row" style={{ textAlign: 'left', padding: '8px 8px 8px 0', fontWeight: 400 }}>{label(row.source)}{row.provenance && <><br />{label(row.provenance)}</>}</th>
            <td style={{ paddingRight: 8 }}>{label(row.state)}</td><td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>{row.count}</td>
          </tr>)}</tbody>
        </table>
      </section>)}
      <p><strong>Not measured by these records:</strong> {data.unavailable_metrics.map(label).join(', ')}. Missing event history is unavailable, not zero. Inactivity is not classified as abandonment.</p>
    </>}
  </div>
}

export function CertificationCourseHealth() {
  const [open, setOpen] = useState(false)
  return <details onToggle={event => setOpen(event.currentTarget.open)} style={{ border: '1px solid #d1d5db', borderRadius: 8, padding: 12, color: '#374151' }}>
    <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Course health by version</summary>
    {open && <HealthReport />}
  </details>
}
