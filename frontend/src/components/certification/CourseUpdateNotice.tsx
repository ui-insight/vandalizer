/** Plain update status for the selected course. Package hashes stay in support details. */
export function CourseUpdateNotice({ available, compareHint, className }: {
  available?: boolean | null; compareHint: string; className?: string
}) {
  if (available !== true) return null
  return <p role="note" className={className ?? 'text-xs text-gray-700'}>
    <span className="font-medium text-gray-900">A newer optional course is available.</span>{' '}
    Your current course and earned progress stay as they are. {compareHint}
  </p>
}

export function courseLabel(course: { course_title?: string; course_version?: string } | null | undefined, legacyTitle = 'Vandal Workflow Architect') {
  if (!course?.course_title) return legacyTitle
  return course.course_version ? `${course.course_title} · version ${course.course_version}` : course.course_title
}
