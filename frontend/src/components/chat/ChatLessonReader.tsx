import { useContext, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { BookOpen } from 'lucide-react'
import { AuthContext } from '../../contexts/AuthContext'
import { useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'
import { MODULES } from '../certification/modules'
import { LessonExtras } from '../certification/LessonContent'
import { EditorialCorrection } from '../certification/EditorialCorrection'
import type { KnowledgeCheckData } from '../../types/certification'
import { renderMarkdown } from './markdown'

const button = 'min-h-11 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50'

/** Browsing is local. Only the explicit save action changes the reading cursor. */
export function ChatLessonReader({ content, readOnly = false }: { content: Record<string, unknown>; readOnly?: boolean }) {
  const certification = useCertificationPanelOptional()
  const auth = useContext(AuthContext)
  const moduleId = String(content.module_id)
  const enrollmentId = typeof content.enrollment_id === 'string' ? content.enrollment_id : undefined
  const progress = certification?.progress
  const course = certification?.course
  const identityMatches = !!progress && (enrollmentId
    ? progress.enrollment_id === enrollmentId && course?.enrollment_id === enrollmentId
      && course.course_version === content.course_version && course.manifest_sha256 === content.manifest_sha256
      && progress.manifest_sha256 === course.manifest_sha256
    : !progress.enrollment_id && !course)
  const module = identityMatches ? (enrollmentId ? course?.modules : MODULES)?.find(item => item.id === moduleId) : undefined
  const lessons = module?.lessons ?? []
  const original = lessons.find(item => item.id === content.lesson_id)
  const available = !readOnly && !!original && original.revision === content.lesson_revision && original.content === content.content
    && lessons.every(item => typeof item.id === 'string' && item.id.length > 0)
    && new Set(lessons.map(item => item.id)).size === lessons.length
  const [selectedId, setSelectedId] = useState(String(content.lesson_id ?? ''))
  const selected = available ? lessons.find(item => item.id === selectedId) : undefined
  const index = selected ? lessons.indexOf(selected) : Number(content.lesson_number) - 1
  const title = selected?.title ?? String(content.title ?? 'Lesson')
  const body = selected?.content ?? String(content.content ?? '')
  const objective = selected ? selected.objective ?? '' : String(content.objective ?? '')
  const heading = useRef<HTMLHeadingElement>(null)
  const focusHeading = useRef(false)
  const savePending = useRef(false)
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const storageKey = `cert-lesson:${auth?.user?.user_id || ''}:${moduleId}`
  const [legacyPlace, setLegacyPlace] = useState(() => {
    try { const value = localStorage.getItem(storageKey); return value === null ? null : Number(value) } catch { return null }
  })
  const savedId = enrollmentId ? progress?.modules[moduleId]?.learning_position?.lesson_id
    : legacyPlace !== null && Number.isInteger(legacyPlace) ? lessons[legacyPlace]?.id : undefined
  const html = useMemo(() => renderMarkdown(body), [body])
  useLayoutEffect(() => {
    if (focusHeading.current) { focusHeading.current = false; heading.current?.focus() }
  }, [selectedId])
  function navigate(id: string) {
    if (!available || !lessons.some(item => item.id === id) || savePending.current) return
    focusHeading.current = true
    setSelectedId(id)
    setStatus('idle')
    // A return to the already displayed lesson still gives keyboard focus.
    if (id === selectedId) { focusHeading.current = false; heading.current?.focus() }
  }
  async function save() {
    if (!available || !selected?.id || savePending.current) return
    savePending.current = true; setStatus('saving')
    try {
      if (enrollmentId) await certification!.savePosition(moduleId, selected.id)
      else {
        localStorage.setItem(storageKey, String(index))
        localStorage.setItem(`cert-active-module:${auth?.user?.user_id || ''}`, moduleId)
        setLegacyPlace(index)
      }
      setStatus('saved')
    } catch { setStatus('error') }
    finally { savePending.current = false }
  }
  return <>
    <div className="cert-lesson-heading">
      <BookOpen aria-hidden="true" size={15} className="shrink-0" />
      <h3 ref={heading} tabIndex={-1} className="font-bold outline-offset-4">{title}</h3>
      <span className="cert-lesson-position text-gray-700">Lesson {index + 1}/{selected ? lessons.length : Number(content.lesson_count)} · {String(content.module_title ?? moduleId)}</span>
    </div>
    {objective && <p className="mb-2 italic leading-relaxed text-gray-700">{objective}</p>}
    <EditorialCorrection manifestSha256={typeof content.manifest_sha256 === 'string' ? content.manifest_sha256 : undefined}
      lessonId={selected?.id ?? (typeof content.lesson_id === 'string' ? content.lesson_id : undefined)} content={body} />
    <div className="select-text chat-markdown" style={{ lineHeight: 1.6 }} dangerouslySetInnerHTML={{ __html: html }} />
    <LessonExtras practiceDisabled={readOnly} key={`${selected?.id ?? content.lesson_id}:${selected?.revision ?? content.lesson_revision}`}
      practiceScope={selected?.id && selected.revision ? { userId: auth?.user?.user_id || '', enrollmentId, moduleId, lessonId: selected.id, revision: selected.revision } : undefined}
      diagram={selected ? selected.diagram : typeof content.diagram === 'string' ? content.diagram : undefined}
      knowledgeCheck={selected ? selected.knowledgeCheck : content.knowledge_check as KnowledgeCheckData | undefined} />
    {available && selected ? <nav aria-label="Chat lesson navigation" className="mt-4 min-w-0 space-y-3">
      <label className="block text-sm font-medium text-gray-900">Lessons in this module
        <select className="mt-1 block min-h-11 w-full min-w-0 max-w-full rounded-lg border border-gray-300 bg-white p-2" value={selectedId} disabled={status === 'saving'} onChange={event => navigate(event.target.value)}>
          {lessons.map((item, i) => <option key={item.id} value={item.id}>{i + 1}. {item.title}</option>)}
        </select>
      </label>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={button} disabled={index === 0 || status === 'saving'} onClick={() => navigate(lessons[index - 1].id!)}>Previous lesson</button>
        <button type="button" className={button} disabled={index === lessons.length - 1 || status === 'saving'} onClick={() => navigate(lessons[index + 1].id!)}>Next lesson</button>
        {savedId && lessons.some(item => item.id === savedId) && <button type="button" className={button} disabled={status === 'saving'} onClick={() => navigate(savedId)}>Return to saved lesson</button>}
        <button type="button" className={button} disabled={status === 'saving'} onClick={() => void save()}>Save my place</button>
      </div>
      <p role="status" className="text-sm text-gray-700">{status === 'saving' ? 'Saving your place…' : status === 'saved' ? enrollmentId ? 'Place saved across devices.' : 'Place saved on this browser.' : status === 'error' ? 'Your place could not be saved. Refresh progress before trying again.' : 'Browse lessons here. Use Save my place to update where you resume. Reading and practice do not award credit.'}</p>
      {status === 'error' && <button type="button" className={button} onClick={() => void certification?.refresh()}>Refresh progress</button>}
      {index === lessons.length - 1 && <p className="text-sm text-gray-700">You have reached the last lesson. Open the learning panel to review the module challenge.</p>}
    </nav> : <p className="mt-4 text-sm text-gray-700">This saved card is available to read. Open the learning panel for the current course lessons.</p>}
    {certification && <button type="button" className={`${button} mt-3`} disabled={status === 'saving'} onClick={certification.openPanel}>Open learning panel</button>}
  </>
}
