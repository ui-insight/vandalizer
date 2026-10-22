export function CourseDraftNotice({ status }: { status: 'empty' | 'stored' | 'unavailable' | 'invalid' }) {
  return <p role="status" className="text-sm text-gray-700">
    {status === 'stored' ? 'Draft kept in this browser tab for this course and exercise. Use the save action to submit it.'
      : status === 'unavailable' ? 'This tab cannot retain your draft. Keep this form open until you save your answers to the course.'
        : status === 'invalid' ? 'This tab could not restore a valid draft for this exercise. Your saved course work is unchanged.'
          : 'Unsubmitted answers stay in this browser tab for this course and exercise. They are not saved to your course until you submit them.'}
  </p>
}
