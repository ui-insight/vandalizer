import { useEffect, useRef, useState } from 'react'
import { useSearch } from '@tanstack/react-router'
import { useCertificationPanel } from '../../contexts/CertificationPanelContext'

export function CourseEditorReturn() {
  const { courseEditor } = useSearch({ from: '/' })
  const { openPanel } = useCertificationPanel()
  const [blocked, setBlocked] = useState(false)
  const [closing, setClosing] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])
  if (courseEditor !== '1') return null
  return <section aria-label="Return from course editor" className="shrink-0 space-y-2 border-b border-gray-300 bg-white p-3 text-sm text-gray-900 [overflow-wrap:anywhere]">
    <p>Save your editor changes, then close this tab to return to the course tab you left open. Editing here does not replace saved assessment evidence.</p>
    {blocked ? <><p role="status">Your browser kept this tab open. Switch to your original course tab to continue; this editor stays open.</p>
      <button type="button" className="min-h-11 rounded-lg border border-gray-300 px-3 py-2 font-semibold" onClick={() => openPanel()}>Open learning panel here</button></>
      : <button type="button" className="min-h-11 rounded-lg border border-gray-300 px-3 py-2 font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" disabled={closing} onClick={() => {
        if (timer.current) return
        setClosing(true)
        window.close()
        timer.current = setTimeout(() => { setBlocked(true); setClosing(false); timer.current = null }, 300)
      }}>{closing ? 'Closing editor tab…' : 'Close editor tab and return to course'}</button>}
  </section>
}
