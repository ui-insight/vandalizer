import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getPracticalHistoryCourse, getPracticalHistoryCourses } from '../../api/certification'
import type { PracticalHistoryCourse, PracticalHistoryCourses } from '../../types/certification'
import { PracticalReview } from './PracticalReview'
import { SavedScenarioHistory } from './SavedScenarioHistory'
import { ProcessDesign } from './ProcessDesign'
import { WorkflowDesign } from './WorkflowDesign'
import { ConnectedWorkflow } from './ConnectedWorkflow'
import { BudgetWorkflow } from './BudgetWorkflow'
import { OutputWorkflow } from './OutputWorkflow'
import { BatchAssessment } from './BatchAssessment'
import { GovernanceAssessment } from './GovernanceAssessment'
import { ValidationSuite } from './ValidationSuite'

const button = 'min-h-11 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50'
const control = 'mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900'

export function CourseHistory() {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [listing, setListing] = useState<PracticalHistoryCourses | null>(null)
  const [course, setCourse] = useState<PracticalHistoryCourse | null>(null)
  const [enrollmentId, setEnrollmentId] = useState('')
  const [moduleId, setModuleId] = useState('')
  const [reference, setReference] = useState('')
  const [error, setError] = useState('')
  const request = useRef(0)
  const opener = useRef<HTMLButtonElement>(null)
  const courseRef = useRef<HTMLDivElement>(null)
  const restoreFocus = useRef(false)
  useEffect(() => () => { ++request.current }, [])
  useLayoutEffect(() => {
    if (course) courseRef.current?.focus()
    if (!open && restoreFocus.current) { restoreFocus.current = false; opener.current?.focus() }
  }, [course, open])

  async function load() {
    const token = ++request.current
    setOpen(true); setBusy(true); setListing(null); setCourse(null); setEnrollmentId(''); setModuleId(''); setError('')
    try {
      const result = await getPracticalHistoryCourses()
      if (token !== request.current) return
      if (result.read_only !== true) throw new Error('Invalid history response')
      setListing(result)
    } catch { if (token === request.current) setError('Saved courses could not be loaded. Try loading history again.') }
    finally { if (token === request.current) setBusy(false) }
  }
  async function inspect(id: string) {
    const token = ++request.current
    setEnrollmentId(id); setCourse(null); setModuleId(''); setError('')
    if (!id) { setBusy(false); return }
    setBusy(true)
    try {
      const result = await getPracticalHistoryCourse(id)
      if (token !== request.current) return
      if (result.enrollment_id !== id || result.read_only !== true || !/^[a-f0-9]{64}$/.test(result.manifest_sha256)
        || result.modules.some(module => module.decision_prompts.some(prompt => prompt.module_id !== module.module_id) || (module.scenario_definition && module.scenario_definition.module_id !== module.module_id) || (module.process_definition && module.process_definition.module_id !== module.module_id) || (module.workflow_design_definition && module.workflow_design_definition.module_id !== module.module_id) || (module.connected_workflow_definition && module.connected_workflow_definition.module_id !== module.module_id) || (module.budget_workflow_definition && module.budget_workflow_definition.module_id !== module.module_id) || (module.validation_definition && module.validation_definition.module_id !== module.module_id) || (module.governance_definition && module.governance_definition.module_id !== module.module_id) || (module.batch_definition && module.batch_definition.module_id !== module.module_id) || (module.output_workflow_definition && module.output_workflow_definition.module_id !== module.module_id))) throw new Error('Mismatched history')
      setCourse(result)
    } catch { if (token === request.current) setError('This original course could not be opened. Its saved work has not been replaced. Check the reference or reload history.') }
    finally { if (token === request.current) setBusy(false) }
  }
  function close() { ++request.current; restoreFocus.current = true; setOpen(false); setBusy(false); setCourse(null); setListing(null); setError('') }
  const module = course?.modules.find(item => item.module_id === moduleId)
  return <section aria-label="Saved course work" className="my-4 min-w-0 space-y-3 rounded-lg border border-gray-200 bg-white p-2 [overflow-wrap:anywhere] sm:p-4">
    <h3 className="text-sm font-semibold text-gray-900">Your saved course work</h3>
    <p className="text-sm text-gray-700">Open process maps, scenario answers, sources, decisions and automatic feedback from an original course. Your selected course stays the same.</p>
    {!open ? <button ref={opener} type="button" className={button} onClick={() => { void load() }}>Browse saved course work</button> : <>
      <button type="button" className={button} onClick={close}>Close saved course work</button>
      {busy && <p role="status" className="text-sm text-gray-700">Loading saved course work…</p>}
      {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
      <button type="button" className={button} onClick={() => { void load() }}>Reload course history</button>
      {listing && <>
        {listing.courses.length ? <label className="block text-sm text-gray-900">Saved course<select className={control} value={listing.courses.some(item => item.enrollment_id === enrollmentId) ? enrollmentId : ''} onChange={event => { void inspect(event.target.value) }}>
          <option value="">Choose a saved course</option>
          {listing.courses.map(item => <option key={item.enrollment_id} value={item.enrollment_id}>{item.course_title} · {item.course_version} · {selectionLabel(item.selection_status)} · {item.enrollment_id.slice(0, 8)}{item.definition_available ? '' : ' · definition unavailable'}</option>)}
        </select></label> : <p className="text-sm text-gray-700">No saved course enrollments are available yet.</p>}
        {listing.older_courses_available && <p className="text-sm text-gray-700">Showing the 50 most recent courses. Open older work using its full enrollment reference.</p>}
      </>}
      <details className="min-w-0 border-t border-gray-200 pt-2"><summary className="min-h-11 cursor-pointer py-2 text-sm font-medium text-gray-900">Open a course by reference</summary>
        <form onSubmit={event => { event.preventDefault(); void inspect(reference.trim()) }} className="space-y-3">
          <label className="block text-sm text-gray-900">Full enrollment reference<input className={control} value={reference} onChange={event => setReference(event.target.value)} required pattern="[a-f0-9]{32}" /></label>
          <button className={button}>Open original course</button>
        </form>
      </details>
      {course && <div ref={courseRef} tabIndex={-1} role="region" aria-label="Original course history" className="min-w-0 space-y-3 border-t border-gray-200 pt-3 outline-offset-4">
        <h4 className="text-base font-semibold text-gray-900">{course.course_title}</h4>
        <p className="text-sm text-gray-700">{course.course_version} · {selectionLabel(course.selection_status)}</p>
        {course.enrollment_state === 'completed' && <p className="text-sm text-gray-700">Recorded as completed. Your original earned work stays in this course; a newer course has its own requirements.</p>}
        {course.enrollment_state === 'transferred' && <p className="text-sm text-gray-700">Closed transfer history. This enrollment is read-only. Its saved work and original certificates remain preserved.</p>}
        {course.enrollment_state === 'abandoned' && <p className="text-sm text-gray-700">Closed course history. This enrollment is no longer open for learning. Its saved work and original certificates remain preserved.</p>}
        {course.selection_status === 'prepared' && <p className="text-sm text-gray-700">This course was prepared for an optional upgrade and has not been selected. Your current course remains available. Preparation does not award credit.</p>}
        {course.selection_status === 'confirmation_pending' && <p className="text-sm text-gray-700">This course choice was saved. Finish confirming it using the notice at the top of the learning panel before starting new work.</p>}
        {course.provenance === 'legacy_version_unknown' && <p className="text-sm text-gray-700">Your earlier course version was not recorded. This retained definition is a continuation baseline; it does not identify the lessons you previously completed.</p>}
        <p className="text-sm text-gray-700">History is read-only. Continue new work from your selected course.</p>
        <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-700">Original enrollment reference</summary><p className="break-all text-sm text-gray-700">{course.enrollment_id}</p></details>
        {course.modules.length ? <label className="block text-sm text-gray-900">Saved module<select className={control} value={moduleId} onChange={event => setModuleId(event.target.value)}>
          <option value="">Choose a module</option>{course.modules.map(item => <option key={item.module_id} value={item.module_id}>{item.title}</option>)}
        </select></label> : <p className="text-sm text-gray-700">This course has no saved assessment review modules. Any earned certificates remain available separately in certificate history.</p>}
        {module?.decision_prompts.length ? <PracticalReview key={`practical:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} moduleId={module.module_id} prompts={module.decision_prompts} historyOnly /> : null}
        {module?.workflow_design_definition && <WorkflowDesign key={`workflow:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} definition={module.workflow_design_definition} historyOnly />}
        {module?.governance_definition && <GovernanceAssessment key={`governance:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} definition={module.governance_definition} historyOnly />}
        {module?.batch_definition && <BatchAssessment key={`batch:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} definition={module.batch_definition} historyOnly />}
        {module?.validation_definition && <ValidationSuite key={`validation:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} definition={module.validation_definition} historyOnly />}
        {module?.output_workflow_definition && <OutputWorkflow key={`output:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} definition={module.output_workflow_definition} historyOnly />}
        {module?.budget_workflow_definition && <BudgetWorkflow key={`budget:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} definition={module.budget_workflow_definition} historyOnly />}
        {module?.connected_workflow_definition && <ConnectedWorkflow key={`connected:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} definition={module.connected_workflow_definition} historyOnly />}
        {module?.process_definition && <ProcessDesign key={`process:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} definition={module.process_definition} historyOnly />}
        {module?.scenario_definition && <SavedScenarioHistory key={`scenario:${course.enrollment_id}:${module.module_id}`} enrollmentId={course.enrollment_id} definition={module.scenario_definition} />}
      </div>}
    </>}
  </section>
}
function selectionLabel(status?: string) {
  return status === 'prepared' ? 'Prepared course — not started'
    : status === 'current' ? 'Current course'
    : status === 'confirmation_pending' ? 'Selection awaiting confirmation'
    : status === 'retained' ? 'Retained course' : 'Saved course'
}
