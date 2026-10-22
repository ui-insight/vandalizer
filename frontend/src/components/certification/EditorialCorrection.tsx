import corrections from './editorialCorrections.json'
import { useEffect, useState } from 'react'

/** Current editorial guidance is separate from the immutable historical lesson. */
export function EditorialCorrection({ manifestSha256, lessonId, moduleId, content }: { manifestSha256?: string; lessonId?: string; moduleId?: string; content?: string }) {
  const [fingerprint, setFingerprint] = useState<{ content: string; sha256: string } | null>(null)
  useEffect(() => {
    if (manifestSha256 || !content || !globalThis.crypto?.subtle || typeof TextEncoder === 'undefined') return
    let current = true
    void crypto.subtle.digest('SHA-256', new TextEncoder().encode(content)).then(value => {
      if (current) setFingerprint({ content, sha256: [...new Uint8Array(value)].map(byte => byte.toString(16).padStart(2, '0')).join('') })
    }).catch(() => { /* Do not infer a historical course if its content cannot be matched. */ })
    return () => { current = false }
  }, [manifestSha256, content])
  const candidates = moduleId
    ? corrections.module_notices.map(item => ({ ...item, targetIds: item.module_ids }))
    : corrections.notices.map(item => ({ ...item, targetIds: item.lesson_ids }))
  const notices = candidates.filter(item => manifestSha256
    ? item.manifest_sha256 === manifestSha256 && item.targetIds.includes(moduleId ?? lessonId ?? '')
    : !!fingerprint && fingerprint.content === content && item.unversioned_content_sha256.includes(fingerprint.sha256))
  return <>{notices.map(notice => <aside key={notice.id} aria-label={notice.title}
    className="my-3 min-w-0 rounded-lg border border-amber-300 bg-amber-50 px-[8px] py-3 text-sm leading-relaxed text-amber-950 sm:p-3"
    style={{ overflowWrap: 'anywhere' }}>
    <p className="mb-2 font-bold">{notice.title}</p>
    {!manifestSha256 && <p className="mb-2">The original course version is unavailable. This correction matches the preserved {moduleId ? 'module description' : 'lesson text'}; it does not identify a historical course version.</p>}
    {notice.paragraphs.map((paragraph, index) => <p key={index} className="mb-2">{paragraph}</p>)}
    <p>Issued {notice.issued_at}. Your saved course, assessment requirements and earned credit are preserved.</p>
  </aside>)}</>
}
