import { useEffect, useState } from 'react'
import { X, Loader2 } from 'lucide-react'
import { pollStatus } from '../../api/documents'

interface RawTextModalProps {
  docUuid: string
  onClose: () => void
}

export function RawTextModal({ docUuid, onClose }: RawTextModalProps) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)

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
    >
      <div
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
          <span style={{ fontWeight: 600, fontSize: 16 }}>Raw Text</span>
          <button
            onClick={onClose}
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
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontFamily: 'monospace',
                fontSize: 13,
                lineHeight: 1.6,
                margin: 0,
                color: '#333',
              }}
            >
              {text}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}
