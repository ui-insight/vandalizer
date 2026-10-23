import { useState } from 'react'
import { getCertificationHealth, type CertificationHealthRow, type CertificationJourneySuccess } from '../../api/certificationHealth'
import { useAdminQuery } from './shared/useAdminQuery'

const labels: Record<string, string> = {
  enrollments: 'Enrollment records', module_completions: 'Module completion requests',
  automatic_reviews: 'Automatic reviews', lab_runs: 'Lab runs',
  new_enrollment: 'New enrollment', explicit_upgrade: 'Optional upgrade',
  legacy_version_unknown: 'Historical version unknown', unknown: 'Unknown',
  start_failures: 'Start failures', save_refresh_failures: 'Save and refresh failures',
  grading_disputes: 'Grading disputes', abandonment_rate: 'Abandonment rate',
  resume_success: 'Resume success', bridge_uptake: 'Bridge uptake',
  initial_progress_load_failed: 'Initial progress load failed', progress_refresh_failed: 'Progress refresh failed',
  position_save_failed: 'Reading-place save failed', saved_lesson_displayed: 'Saved lesson restored on display',
  bridge_assessment_requested: 'Bridge assessment entry requested', journey_success_rates: 'Journey success rates',
  saved_lesson_unavailable: 'Saved lesson could not be restored', grading_question_opened: 'Grading question opened from a result',
  dropout: 'Why learners stop (dropout)', grading_question_outcomes: 'Whether a grading question was upheld',
}
const label = (value: string) => labels[value] ?? value.replaceAll('_', ' ')
const percent = (value: number | null) => value === null ? null : `${Math.round(value * 1000) / 10}%`

function courseName(row: { course_title: string | null; course_version: string | null }) {
  if (row.course_title) return `${row.course_title}${row.course_version ? ` (version ${row.course_version})` : ''}`
  return row.course_version ?? 'Historical course, version unknown'
}

function SupportDetails({ manifest }: { manifest: string | null }) {
  return <details style={{ fontSize: 12 }}>
    <summary style={{ cursor: 'pointer' }}>Support details</summary>
    Package: {manifest ?? 'Unknown; not inferred from the installed course'}
  </details>
}

function Measure({ name, value, rate, note }: { name: string; value: string | number; rate?: string | null; note?: string }) {
  return <li style={{ marginTop: 6 }}><strong>{name}:</strong> {value}{rate !== undefined && <> · {rate ?? 'rate withheld (too few records)'}</>}{note && <><br /><span style={{ fontSize: 12 }}>{note}</span></>}</li>
}

function JourneySuccess({ data }: { data: CertificationJourneySuccess }) {
  const days = data.inactive_after_days
  return <section aria-label="Journey outcomes by course" style={{ marginTop: 16 }}>
    <h3 style={{ fontSize: 16 }}>Journey outcomes by course</h3>
    <p>Started means any enrollment past preparation. Rates are shown only when at least {data.min_rate_denominator} records are behind them. “Inactive” means an active enrollment with no server-recorded activity (start, saved reading place or module submission) for {days}+ days. It is not dropout: learners pause self-paced study around deadlines, and these records cannot say why anyone stopped. Grading questions and resume results come from the last {data.journey_window_days} days of browser observations; other counts cover all retained records.</p>
    {!data.courses.length && <p>No started enrollments were found.</p>}
    {data.courses.map(row => <section key={JSON.stringify([row.course_version, row.manifest_sha256])} aria-label={`Journey outcomes: ${courseName(row)}`} style={{ marginTop: 12 }}>
      <h4>{courseName(row)}</h4>
      <SupportDetails manifest={row.manifest_sha256} />
      <ul style={{ paddingLeft: 20 }}>
        <Measure name="Started" value={row.started} />
        <Measure name="Completed" value={row.completed} rate={percent(row.completion_rate)} note={row.transferred ? `${row.transferred} transferred to another course and excluded from the completion rate.` : undefined} />
        <Measure name={`Inactive ${days}+ days`} value={`${row.inactive} of ${row.active} active`} rate={percent(row.inactive_share)} note={row.activity_unknown ? `${row.activity_unknown} active enrollments have no activity date.` : undefined} />
        <Measure name="Resumed at saved place" value={`${row.resumes_restored} of ${row.resumes_restored + row.resumes_unavailable}`} rate={percent(row.resume_success_rate)} />
        <Measure name="Grading questions opened" value={row.grading_questions_opened} note="A learner chose “Question this result”; not a confirmed grading error." />
        <Measure name="Staff grading corrections" value={row.staff_grading_corrections} note="Recorded regrades an administrator ran after reviewing a concern." />
      </ul>
    </section>)}
    <section aria-label="Bridge uptake" style={{ marginTop: 12 }}>
      <h4>Bridge uptake</h4>
      <p>{data.bridge.upgraded_learners} of {data.bridge.legacy_learners} learners with a historical course record started a newer course ({percent(data.bridge.uptake_rate) ?? 'rate withheld (too few records)'}). Prepared but unstarted upgrades are not counted.</p>
      {!!data.bridge.targets.length && <ul style={{ paddingLeft: 20 }}>{data.bridge.targets.map(row => <li key={JSON.stringify([row.course_version, row.manifest_sha256])}>{courseName(row)}: {row.learners}</li>)}</ul>}
    </section>
  </section>
}

function groupByCourse(rows: CertificationHealthRow[]) {
  const courses = new Map<string, CertificationHealthRow[]>()
  for (const row of rows) {
    const key = JSON.stringify([row.course_version, row.manifest_sha256])
    courses.set(key, [...(courses.get(key) ?? []), row])
  }
  return [...courses]
}

function HealthReport() {
  const { data, loading, error, load } = useAdminQuery(getCertificationHealth)
  const courses = groupByCourse(data?.rows ?? [])
  const titles = new Map((data?.journey_success?.courses ?? []).filter(row => row.course_title).map(row => [JSON.stringify([row.course_version, row.manifest_sha256]), courseName(row)]))
  const titleOf = (row: CertificationHealthRow) => titles.get(JSON.stringify([row.course_version, row.manifest_sha256]))
  return <div style={{ marginTop: 12, overflowWrap: 'anywhere' }}>
    <p>All retained records, grouped by course version and exact package. Counts describe saved states, not unique learners or success rates. Reads can observe changes made while this report loads.</p>
    <button type="button" className="admin-open-record" disabled={loading} onClick={load}>Refresh course health</button>
    {loading && <p role="status">Loading course health…</p>}
    {error && <p role="alert">{error}</p>}
    {data && <>
      <p>Observed {new Date(data.observed_at).toLocaleString()}. No enrollment or assessment was changed.</p>
      <p>Prepared enrollments are not starts. Optional upgrades are not proof that a learner used the bridge. Rejected completion requests are not grading disputes; failed lab runs can be part of a recovery exercise. Saved completion states do not independently verify credentials.</p>
      {data.journey_success && <JourneySuccess data={data.journey_success} />}
      {data.rows.length === 0 && <p>No records were found in the four monitored collections.</p>}
      {[...courses].map(([key, rows]) => <section key={key} style={{ marginTop: 16 }} aria-label={`Course health: ${rows[0].course_version ?? 'Unknown version'}`}>
        <h3 style={{ fontSize: 16 }}>{titleOf(rows[0]) ?? rows[0].course_version ?? 'Historical or missing course version'}</h3>
        <SupportDetails manifest={rows[0].manifest_sha256} />
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead><tr><th scope="col" style={{ textAlign: 'left' }}>Record</th><th scope="col" style={{ textAlign: 'left' }}>Saved state</th><th scope="col" style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>Count</th></tr></thead>
          <tbody>{rows.map(row => <tr key={`${row.source}:${row.provenance}:${row.state}`}>
            <th scope="row" style={{ textAlign: 'left', padding: '8px 8px 8px 0', fontWeight: 400 }}>{label(row.source)}{row.provenance && <><br />{label(row.provenance)}</>}</th>
            <td style={{ paddingRight: 8 }}>{label(row.state)}</td><td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>{row.count}</td>
          </tr>)}</tbody>
        </table>
      </section>)}
      <p><strong>Not measured by these records:</strong> {data.unavailable_metrics.map(label).join(', ')}. Missing event history is unavailable, not zero. Inactivity is reported as inactive, never as dropout.</p>
      {data.journey && <section aria-label="Client-reported learning journeys" style={{ marginTop: 16 }}>
        <h3 style={{ fontSize: 16 }}>Client-reported learning journeys · last {data.journey.window_days} days</h3>
        <p>Observations received from this interface, not assessment evidence or unique learners. Initial loads may run before the course is opened. Failed reads/saves describe the browser’s result, which can differ from a saved server result. Offline browsers and older app versions can miss events; these raw counts are not success rates.</p>
        {!data.journey.rows.length && <p>No journey observations were received in this window. This does not mean there were no failures.</p>}
        {groupByCourse(data.journey.rows).map(([key, rows]) => <section key={key} style={{ marginTop: 16 }} aria-label={`Journey observations: ${rows[0].course_version ?? 'Unknown version'}`}>
          <h4>{titleOf(rows[0]) ?? rows[0].course_version ?? 'Historical or unavailable course identity'}</h4>
          <SupportDetails manifest={rows[0].manifest_sha256} />
          <ul style={{ paddingLeft: 20 }}>{rows.map(row => <li key={row.state} style={{ marginTop: 8 }}>
            <strong>{label(row.state)}: {row.count}</strong>
          </li>)}</ul>
        </section>)}
      </section>}
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
