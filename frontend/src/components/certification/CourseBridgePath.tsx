import type { CertificationProgress, CourseDefinition } from '../../types/certification'

export function CourseBridgePath({ course, progress, onAssess }: {
  course: CourseDefinition
  progress: CertificationProgress | null
  onAssess: (moduleId: string) => void
}) {
  const path = course.bridge_path
  if (!path || path.course_version !== course.course_version || path.manifest_sha256 !== course.manifest_sha256
    || path.credit_policy !== 'same_course_same_required_outcomes' || !Array.isArray(path.stages)
    || !Array.isArray(path.rules) || path.rules.some(rule => typeof rule !== 'string')) return null
  const rows = path.stages.flatMap(stage => Array.isArray(stage.modules) ? stage.modules : [])
  const ids = rows.map(row => row.module_id)
  if (ids.length !== course.modules.length || new Set(ids).size !== ids.length
    || ids.some(id => !course.modules.some(module => module.id === id))
    || rows.some(row => !Number.isInteger(row.required_outcomes) || row.required_outcomes <= 0)
    || rows.reduce((sum, row) => sum + row.required_outcomes, 0) !== path.required_outcomes) return null
  const ownedProgress = progress?.enrollment_id === course.enrollment_id
    && progress?.course_version === course.course_version && progress?.manifest_sha256 === course.manifest_sha256
  return <details className="min-w-0 rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700 [overflow-wrap:anywhere]">
    <summary className="min-h-11 cursor-pointer py-2 font-semibold text-gray-900">{path.title}</summary>
    <p className="mt-2">{path.description}</p>
    {path.state === 'design_draft' && <p className="mt-2 font-medium text-gray-900">Unpublished bridge preview. Course credit is not available in this preview.</p>}
    <p className="mt-2">{path.required_outcomes} required outcomes · the same course certificate</p>
    <ol className="mt-4 list-decimal space-y-5 pl-5">{path.stages.map(stage => <li key={stage.id}>
      <h3 className="font-semibold text-gray-900">{stage.title}</h3>
      <p className="mt-1">{stage.purpose}</p>
      <ul className="mt-2 space-y-2">{stage.modules.map(module => <li key={module.module_id}>
        <button type="button" onClick={() => onAssess(module.module_id)} className="min-h-11 w-full rounded-md border border-gray-300 px-3 py-2 text-left font-medium text-gray-900 [overflow-wrap:anywhere]">
          {ownedProgress && progress.modules[module.module_id]?.completed ? 'Review assessment' : 'Open assessment'}: {module.title}
        </button>
        <p className="mt-1 text-xs text-gray-600">{module.required_outcomes} required outcomes{ownedProgress && progress.modules[module.module_id]?.completed ? ' · completed in this course' : ''}</p>
      </li>)}</ul>
    </li>)}</ol>
    <details className="mt-4 border-t border-gray-200 pt-2">
      <summary className="min-h-11 cursor-pointer py-2 font-medium text-gray-900">How this path uses your earlier experience</summary>
      <ul className="list-disc space-y-2 pl-5">{path.rules.map(rule => <li key={rule}>{rule}</li>)}</ul>
    </details>
  </details>
}
