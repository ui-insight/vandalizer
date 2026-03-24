import { useEffect, useState, useMemo } from 'react'
import DOMPurify from 'dompurify'
import { X, Loader2 } from 'lucide-react'
import { marked } from 'marked'
import { pollStatus } from '../../api/documents'

marked.setOptions({ breaks: true, gfm: true })

interface RawTextModalProps {
  docUuid: string
  onClose: () => void
}

export function RawTextModal({ docUuid, onClose }: RawTextModalProps) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)

  const renderedHtml = useMemo(() => {
    if (!text) return ''
    return DOMPurify.sanitize(marked.parse(text) as string)
  }, [text])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    pollStatus(docUuid)
      .then((res) => {
        if (!cancelled) {
          setText(res.raw_text || '')
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setText('Failed to load raw text.')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [docUuid])

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.4)',
      }}
      onClick={onClose}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="raw-text-modal-title"
        style={{
          backgroundColor: '#fff',
          borderRadius: 12,
          maxWidth: 700,
          width: '90%',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 8px 30px rgba(0,0,0,0.2)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            borderBottom: '1px solid #eee',
          }}
        >
          <span id="raw-text-modal-title" style={{ fontWeight: 600, fontSize: 16 }}>Extracted Text</span>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: 4,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X style={{ width: 20, height: 20 }} />
          </button>
        </div>

        {/* Body */}
        <div style={{ overflow: 'auto', padding: 16, flex: 1 }}>
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <Loader2
                style={{ width: 32, height: 32, color: 'var(--highlight-color)', animation: 'spin 1s linear infinite' }}
              />
            </div>
          ) : (
            <div
              className="chat-markdown"
              style={{
                fontSize: 14,
                lineHeight: 1.7,
                color: '#333',
              }}
              dangerouslySetInnerHTML={{ __html: renderedHtml }}
            />
          )}
        </div>
      </div>
    </div>
  )
}
