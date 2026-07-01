import { useEffect, useState, useMemo, useCallback } from 'react'
import DOMPurify from 'dompurify'
import { FocusTrap } from 'focus-trap-react'
import { X, Loader2, AlertCircle, RefreshCw } from 'lucide-react'
import { marked } from 'marked'
import { pollStatus, retryExtraction } from '../../api/documents'

marked.setOptions({ breaks: true, gfm: true })

interface RawTextModalProps {
  docUuid: string
  onClose: () => void
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ok'; text: string }
  | { kind: 'error'; message: string; canRetry: boolean }
  | { kind: 'processing'; status: string | null }

export function RawTextModal({ docUuid, onClose }: RawTextModalProps) {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [retrying, setRetrying] = useState(false)

  const renderedHtml = useMemo(() => {
    if (state.kind !== 'ok' || !state.text) return ''
    return DOMPurify.sanitize(marked.parse(state.text) as string)
  }, [state])

  const load = useCallback(() => {
    let cancelled = false
    setState({ kind: 'loading' })
    pollStatus(docUuid)
      .then((res) => {
        if (cancelled) return
        if (res.processing || res.status === 'extracting' || res.status === 'readying') {
          setState({ kind: 'processing', status: res.status })
        } else if (res.status === 'error' || (res.complete && !res.raw_text)) {
          setState({
            kind: 'error',
            message:
              res.error_message ||
              "We couldn't extract any text from this document.",
            canRetry: true,
          })
        } else {
          setState({ kind: 'ok', text: res.raw_text || '' })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({
            kind: 'error',
            message: 'Failed to load extracted text.',
            canRetry: false,
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [docUuid])

  useEffect(() => {
    const cleanup = load()
    return cleanup
  }, [load])

  const handleRetry = useCallback(async () => {
    setRetrying(true)
    try {
      await retryExtraction(docUuid)
      setState({ kind: 'processing', status: 'extracting' })
      // Poll for completion every 3s until done.
      const interval = setInterval(async () => {
        try {
          const res = await pollStatus(docUuid)
          if (res.complete || (!res.processing && res.status !== 'extracting' && res.status !== 'readying')) {
            clearInterval(interval)
            load()
          }
        } catch {
          clearInterval(interval)
        }
      }, 3000)
    } catch (err) {
      setState({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Retry failed.',
        canRetry: true,
      })
    } finally {
      setRetrying(false)
    }
  }, [docUuid, load])

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
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false }}>
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
          {state.kind === 'loading' && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <Loader2
                style={{ width: 32, height: 32, color: 'var(--highlight-color)', animation: 'spin 1s linear infinite' }}
              />
            </div>
          )}

          {state.kind === 'processing' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: 40 }}>
              <Loader2
                style={{ width: 32, height: 32, color: 'var(--highlight-color)', animation: 'spin 1s linear infinite' }}
              />
              <div style={{ fontSize: 14, color: '#555' }}>
                {state.status === 'readying'
                  ? 'Indexing document...'
                  : 'Extracting text from your document...'}
              </div>
            </div>
          )}

          {state.kind === 'error' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: 32, textAlign: 'center' }}>
              <AlertCircle style={{ width: 40, height: 40, color: '#dc2626' }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: '#111' }}>
                Text extraction failed
              </div>
              <div style={{ fontSize: 14, color: '#555', maxWidth: 480, lineHeight: 1.5 }}>
                {state.message}
              </div>
              {state.canRetry && (
                <button
                  onClick={handleRetry}
                  disabled={retrying}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '8px 14px',
                    fontSize: 14,
                    fontWeight: 500,
                    backgroundColor: retrying ? '#9ca3af' : 'var(--highlight-color)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 6,
                    cursor: retrying ? 'not-allowed' : 'pointer',
                  }}
                >
                  <RefreshCw
                    style={{
                      width: 14,
                      height: 14,
                      animation: retrying ? 'spin 1s linear infinite' : undefined,
                    }}
                  />
                  {retrying ? 'Retrying...' : 'Retry extraction'}
                </button>
              )}
            </div>
          )}

          {state.kind === 'ok' && (
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
      </FocusTrap>
    </div>
  )
}
