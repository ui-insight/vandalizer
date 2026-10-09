import corrections from './editorialCorrections.json'
import { useEffect, useState } from 'react'

/** Current editorial guidance is separate from the immutable historical lesson. */
export function EditorialCorrection({ manifestSha256, lessonId, content }: { manifestSha256?: string; lessonId?: string; content?: string }) {
  const [fingerprint, setFingerprint] = useState<{ content: string; sha256: string } | null>(null)
  useEffect(() => {
    if (manifestSha256 || !content || !globalThis.crypto?.subtle || typeof TextEncoder === 'undefined') return
    let current = true
    void crypto.subtle.digest('SHA-256', new TextEncoder().encode(content)).then(value => {
      if (current) setFingerprint({ content, sha256: [...new Uint8Array(value)].map(byte => byte.toString(16).padStart(2, '0')).join('') })
    }).catch(() => { /* Do not infer a historical course if its content cannot be matched. */ })
    return () => { current = false }
  }, [manifestSha256, content])
  const notices = corrections.notices.filter(item => manifestSha256
    ? item.manifest_sha256 === manifestSha256 && item.lesson_ids.includes(lessonId ?? '')
    : !!fingerprint && fingerprint.content === content && item.unversioned_content_sha256.includes(fingerprint.sha256))
  return <>{notices.map(notice => <aside key={notice.id} aria-label={notice.title}
    className="my-3 min-w-0 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm leading-relaxed text-amber-950"
    style={{ overflowWrap: 'anywhere' }}>
    <p className="mb-2 font-bold">{notice.title}</p>
    {!manifestSha256 && <p className="mb-2">The original course version is unavailable. This correction matches the preserved lesson text; it does not identify a historical course version.</p>}
    {notice.paragraphs.map((paragraph, index) => <p key={index} className="mb-2">{paragraph}</p>)}
    <p>Issued {notice.issued_at}. Your saved course, assessment requirements and earned credit are preserved.</p>
  </aside>)}</>
}
