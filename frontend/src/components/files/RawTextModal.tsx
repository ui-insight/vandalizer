import { useEffect, useState, useMemo, useCallback } from 'react'
import DOMPurify from 'dompurify'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X, Loader2, AlertCircle, RefreshCw, Download, Square } from 'lucide-react'
import { marked } from 'marked'
import { cancelExtraction, pollStatus, retryExtraction } from '../../api/documents'
import { ApiError } from '../../api/client'

marked.setOptions({ breaks: true, gfm: true })

interface RawTextModalProps {
  docUuid: string
  onClose: () => void
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ok'; text: string; lowQuality: boolean; isPdf: boolean; title: string }
  | { kind: 'error'; message: string; canRetry: boolean; stopped?: boolean }
  | { kind: 'processing'; status: string | null }

export function RawTextModal({ docUuid, onClose }: RawTextModalProps) {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [retrying, setRetrying] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [stopError, setStopError] = useState<string | null>(null)
  // Shown after stopping a re-read whose previous text was put back.
  const [stopNotice, setStopNotice] = useState<string | null>(null)

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
            // A damaged or misnamed file fails the same way every time.
            canRetry: res.error_retryable !== false,
            stopped: Boolean(res.extraction_stopped),
          })
        } else {
          setState({
            kind: 'ok',
            text: res.raw_text || '',
            lowQuality: Boolean(res.extraction_low_quality),
            isPdf: (res.extension || '').toLowerCase() === 'pdf',
            title: res.title || '',
          })
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

  const handleRetry = useCallback(async (forceOcr = false) => {
    setRetrying(true)
    setStopNotice(null)
    try {
      await retryExtraction(docUuid, { forceOcr })
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

  const handleRerunOcr = useCallback(() => {
    if (
      !window.confirm(
        'Re-run OCR on this document? Its current text will be replaced with a fresh OCR reading, and it will be re-indexed for search.',
      )
    ) {
      return
    }
    void handleRetry(true)
  }, [handleRetry])

  const handleStop = useCallback(async () => {
    if (
      !window.confirm(
        'Stop reading this document? If it already had text, that text is kept. You can retry the extraction afterwards.',
      )
    ) {
      return
    }
    setStopping(true)
    setStopError(null)
    try {
      const res = await cancelExtraction(docUuid)
      setStopNotice(res.restored_previous_text ? 'Stopped. This document still has the text it had before.' : null)
    } catch (err) {
      // A 409 means it finished or failed on its own meanwhile — reloading
      // shows whichever it was.
      if (!(err instanceof ApiError && err.status === 409)) {
        setStopError(err instanceof Error ? err.message : 'Failed to stop extraction.')
      }
    } finally {
      setStopping(false)
    }
    load()
  }, [docUuid, load])

  const handleExportMarkdown = useCallback(() => {
    if (state.kind !== 'ok') return
    const base = (state.title || 'document').replace(/\.[^./\\]+$/, '').replace(/[\\/:*?"<>|]+/g, '_').trim() || 'document'
    const blob = new Blob([state.text], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${base}.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }, [state])

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
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="raw-text-modal-title"
        style={{
          backgroundColor: '#fff',
          borderRadius: 'var(--workspace-radius-large)',
          maxWidth: 700,
          width: '90%',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: 'var(--workspace-shadow-dialog)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: "var(--workspace-space-12) var(--workspace-space-16)",
            borderBottom: '1px solid #eee',
          }}
        >
          <span id="raw-text-modal-title" style={{ fontWeight: 600, fontSize: 'var(--workspace-font-card-title)' }}>Extracted Text</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {state.kind === 'ok' && state.text && (
            <button
              onClick={handleExportMarkdown}
              title="Download the extracted text as a Markdown file"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '5px 10px',
                fontSize: 13,
                fontWeight: 500,
                backgroundColor: 'transparent',
                color: '#333',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                cursor: 'pointer',
              }}
            >
              <Download style={{ width: 13, height: 13 }} />
              Export Markdown
            </button>
          )}
          {state.kind === 'ok' && state.isPdf && (
            <button
              onClick={handleRerunOcr}
              disabled={retrying}
              title="Read this document again with OCR and replace its stored text"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '5px 10px',
                fontSize: 13,
                fontWeight: 500,
                backgroundColor: 'transparent',
                color: retrying ? '#9ca3af' : '#333',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                cursor: retrying ? 'not-allowed' : 'pointer',
              }}
            >
              <RefreshCw
                style={{
                  width: 13,
                  height: 13,
                  animation: retrying ? 'spin 1s linear infinite' : undefined,
                }}
              />
              {retrying ? 'Starting...' : 'Re-run OCR'}
            </button>
          )}
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: 'var(--workspace-space-4)',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X style={{ width: 20, height: 20 }} />
          </button>
          </div>
        </div>

        {/* Body */}
        <div role="region" aria-label="Extracted text content" tabIndex={0} style={{ overflow: 'auto', minHeight: 0, padding: 'var(--workspace-space-16)', flex: 1 }}>
          {state.kind === 'loading' && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <Loader2
                style={{ width: 32, height: 32, color: 'var(--highlight-color)', animation: 'spin 1s linear infinite' }}
              />
            </div>
          )}

          {state.kind === 'processing' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--workspace-space-12)', padding: 40 }}>
              <Loader2
                style={{ width: 32, height: 32, color: 'var(--highlight-color)', animation: 'spin 1s linear infinite' }}
              />
              <div style={{ fontSize: 'var(--workspace-font-body)', color: '#555' }}>
                {state.status === 'readying'
                  ? 'Indexing document...'
                  : 'Extracting text from your document...'}
              </div>
              <button
                onClick={() => void handleStop()}
                disabled={stopping}
                title="Stop this extraction so it can be restarted"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '5px 10px',
                  fontSize: 13,
                  fontWeight: 500,
                  backgroundColor: 'transparent',
                  color: stopping ? '#9ca3af' : '#b91c1c',
                  border: '1px solid #fca5a5',
                  borderRadius: 6,
                  cursor: stopping ? 'not-allowed' : 'pointer',
                }}
              >
                <Square style={{ width: 12, height: 12 }} />
                {stopping ? 'Stopping...' : 'Stop'}
              </button>
              {stopError && (
                <div role="alert" style={{ fontSize: 13, color: '#b91c1c' }}>
                  {stopError}
                </div>
              )}
            </div>
          )}

          {stopNotice && state.kind === 'ok' && (
            <div role="status" style={{ marginBottom: 'var(--workspace-space-12)', padding: 'var(--workspace-space-8) var(--workspace-space-12)', borderRadius: 6, border: '1px solid #d1d5db', background: '#f9fafb', color: '#374151', fontSize: 'var(--workspace-font-body)' }}>
              {stopNotice}
            </div>
          )}

          {state.kind === 'error' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--workspace-space-16)', padding: 'var(--workspace-space-32)', textAlign: 'center' }}>
              {/* Stopped by a person is not a failure: no red, and it says so. */}
              {state.stopped
                ? <Square style={{ width: 36, height: 36, color: '#6b7280' }} />
                : <AlertCircle style={{ width: 40, height: 40, color: '#dc2626' }} />}
              <div style={{ fontSize: 'var(--workspace-font-card-title)', fontWeight: 600, color: '#111' }}>
                {state.stopped ? 'Text extraction stopped' : 'Text extraction failed'}
              </div>
              <div style={{ fontSize: 'var(--workspace-font-body)', color: '#555', maxWidth: 480, lineHeight: 1.5 }}>
                {state.message}
              </div>
              {state.canRetry && (
                <button
                  onClick={() => void handleRetry()}
                  disabled={retrying}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--workspace-space-6)',
                    padding: "var(--workspace-space-8) var(--workspace-space-16)",
                    fontSize: 'var(--workspace-font-body)',
                    fontWeight: 500,
                    backgroundColor: retrying ? '#9ca3af' : 'var(--highlight-color)',
                    color: 'var(--highlight-text-color, #000)',
                    border: 'none',
                    borderRadius: 'var(--workspace-radius-small)',
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
            <>
              {/* The extraction succeeded, so nothing above shows an error —
                  but the text below is mojibake. Without this the only way
                  to reach Retry extraction was to be in the error branch. */}
              {state.lowQuality && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--workspace-space-12)',
                    padding: "var(--workspace-space-12) var(--workspace-space-12)",
                    marginBottom: 'var(--workspace-space-12)',
                    fontSize: 'var(--workspace-font-control)',
                    lineHeight: 1.4,
                    color: '#92400e',
                    backgroundColor: '#fffbeb',
                    border: '1px solid #fcd34d',
                    borderRadius: 'var(--workspace-radius-small)',
                  }}
                >
                  <AlertCircle style={{ width: 16, height: 16, flexShrink: 0 }} />
                  <span style={{ flex: 1 }}>
                    Text extracted poorly &mdash; most of the stored text is unreadable.
                  </span>
                  <button
                    onClick={() => void handleRetry()}
                    disabled={retrying}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--workspace-space-6)',
                      flexShrink: 0,
                      padding: "var(--workspace-space-6) var(--workspace-space-12)",
                      fontSize: 'var(--workspace-font-control)',
                      fontWeight: 500,
                      backgroundColor: retrying ? '#9ca3af' : 'var(--highlight-color)',
                      color: 'var(--highlight-text-color, #000)',
                      border: 'none',
                      borderRadius: 'var(--workspace-radius-small)',
                      cursor: retrying ? 'not-allowed' : 'pointer',
                    }}
                  >
                    <RefreshCw
                      style={{
                        width: 13,
                        height: 13,
                        animation: retrying ? 'spin 1s linear infinite' : undefined,
                      }}
                    />
                    {retrying ? 'Retrying...' : 'Retry extraction'}
                  </button>
                </div>
              )}
              <div
                className="chat-markdown"
                style={{
                  fontSize: 'var(--workspace-font-body)',
                  lineHeight: 1.7,
                  color: '#333',
                }}
                dangerouslySetInnerHTML={{ __html: renderedHtml }}
              />
            </>
          )}
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
