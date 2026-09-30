import { usePanelEffect } from '../shared/usePanelEffect'
import { useState, useEffect, useCallback, useRef } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X, Search, FileText, Loader2, Check, Upload, FolderIcon } from 'lucide-react'
import { searchDocuments, type SearchResult } from '../../api/documents'
import { listAllFolders, type FolderSummary } from '../../api/folders'
import { uploadFile } from '../../api/files'
import { useUploadPolicy } from '../../hooks/useUploadPolicy'
import { readUploadPolicy, uploadFileError } from '../../utils/uploadPolicy'

interface DocumentPickerModalProps {
  onSubmit: (docUuids: string[]) => void | Promise<void>
  onClose: () => void
  existingSourceUuids?: string[]
  onSubmitFolder?: (folderUuid: string, includeSubfolders: boolean) => void | Promise<void>
}

type UploadStatus = 'uploading' | 'done' | 'error'
interface UploadItem {
  id: string
  name: string
  status: UploadStatus
  uuid?: string
  error?: string
}

// Rough "this will take a while to index" thresholds. Indexing time scales with
// text volume; token_count is the closest proxy the search API returns, with
// page count as a fallback for documents whose text isn't extracted yet.
const LARGE_DOC_TOKENS = 50_000
const LARGE_DOC_PAGES = 100

function isLargeDoc(doc: SearchResult): boolean {
  return doc.token_count >= LARGE_DOC_TOKENS || doc.num_pages >= LARGE_DOC_PAGES
}

function getExt(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
}

function newId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      resolve(result.split(',')[1])
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export function DocumentPickerModal({ onSubmit, onClose, existingSourceUuids = [], onSubmitFolder }: DocumentPickerModalProps) {
  const uploadPolicy = useUploadPolicy()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [folders, setFolders] = useState<FolderSummary[]>([])
  const [folderFilter, setFolderFilter] = useState<string>('')  // '' = all folders
  const [includeSubfolders, setIncludeSubfolders] = useState(true)
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragCounterRef = useRef(0)
  const submitRef = useRef(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const searchRequest = useRef(0)
  const invalidateSearch = useCallback(() => { searchRequest.current++ }, [])
  const existingIds = useRef(existingSourceUuids)
  existingIds.current = existingSourceUuids

  const doSearch = useCallback(async (q: string, folder: string) => {
    const request = ++searchRequest.current
    setLoading(true)
    setSearchError(null)
    try {
      const folderParam = folder === '' ? undefined : folder
      const data = await searchDocuments(q, 30, folderParam)
      if (request === searchRequest.current) setResults(data.items.filter(d => !existingIds.current.includes(d.uuid)))
    } catch (err) {
      if (request === searchRequest.current) setSearchError(err instanceof Error ? err.message : 'Document search is unavailable')
    } finally {
      if (request === searchRequest.current) setLoading(false)
    }
  }, [])

  // Close on Escape
  usePanelEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitRef.current) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Load folders on mount
  useEffect(() => {
    listAllFolders()
      .then(setFolders)
      .catch(err => console.error('Failed to load folders:', err))
  }, [])

  // One search per scope change; older responses cannot replace newer results.
  useEffect(() => {
    const timer = setTimeout(() => doSearch(query, folderFilter), query ? 300 : 0)
    return () => { clearTimeout(timer); invalidateSearch() }
  }, [query, folderFilter, doSearch, invalidateSearch])

  const toggleDoc = (uuid: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }

  const commit = async (folder = false) => {
    if (submitRef.current || uploads.some(u => u.status === 'uploading')) return
    if (!folder && selected.size === 0) return
    submitRef.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      if (folder) await onSubmitFolder?.(folderFilter, includeSubfolders)
      else await onSubmit(Array.from(selected))
      onClose()
    } catch (error) {
      setSubmitError(`${error instanceof Error ? error.message : 'Could not add documents'}. Your selection is preserved; retry Add.`)
    } finally { submitRef.current = false; setSubmitting(false) }
  }
  const handleSubmit = () => commit()

  const folderPathByUuid = useCallback((uuid: string | null | undefined) => {
    if (!uuid || uuid === '0' || uuid === '') return ''
    return folders.find(f => f.uuid === uuid)?.path ?? ''
  }, [folders])

  const patchUpload = (id: string, patch: Partial<UploadItem>) => {
    setUploads(prev => prev.map(u => (u.id === id ? { ...u, ...patch } : u)))
  }

  const removeUpload = (id: string) => {
    setUploads(prev => {
      const target = prev.find(u => u.id === id)
      if (target?.status === 'done' && target.uuid) {
        setSelected(s => {
          const next = new Set(s)
          next.delete(target.uuid!)
          return next
        })
      }
      return prev.filter(u => u.id !== id)
    })
  }

  const handleFiles = async (files: File[]) => {
    if (files.length === 0 || submitRef.current) return
    const targetFolder = folderFilter && folderFilter !== '__root__' ? folderFilter : undefined
    const policy = await readUploadPolicy()

    type Prepared = { item: UploadItem; file?: File; ext?: string }
    const prepared: Prepared[] = files.map(file => {
      const ext = getExt(file.name)
      const error = uploadFileError(file, policy)
      if (error) {
        return {
          item: {
            id: newId(),
            name: file.name,
            status: 'error',
            error,
          },
        }
      }
      return { item: { id: newId(), name: file.name, status: 'uploading' }, file, ext }
    })
    setUploads(prev => [...prev, ...prepared.map(p => p.item)])

    const newUuids: string[] = []
    for (const p of prepared) {
      if (!p.file || !p.ext) continue
      try {
        const base64 = await fileToBase64(p.file)
        const result = await uploadFile({
          contentAsBase64String: base64,
          fileName: p.file.name,
          extension: p.ext,
          folder: targetFolder,
        })
        if (result.uuid) {
          newUuids.push(result.uuid)
          patchUpload(p.item.id, { status: 'done', uuid: result.uuid })
        } else {
          patchUpload(p.item.id, { status: 'error', error: 'Upload failed' })
        }
      } catch (err) {
        patchUpload(p.item.id, {
          status: 'error',
          error: err instanceof Error ? err.message : 'Upload failed',
        })
      }
    }
    if (newUuids.length > 0) {
      setSelected(prev => {
        const next = new Set(prev)
        newUuids.forEach(u => next.add(u))
        return next
      })
      doSearch(query, folderFilter)
    }
  }

  const onFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : []
    handleFiles(files)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current += 1
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setDragActive(true)
    }
  }
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current -= 1
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0
      setDragActive(false)
    }
  }
  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current = 0
    setDragActive(false)
    const files = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : []
    handleFiles(files)
  }

  const uploadingCount = uploads.filter(u => u.status === 'uploading').length
  // Only counts docs in the current result set; a selection carried over from an
  // earlier search won't warn, which is acceptable for a heads-up.
  const selectedLargeCount = results.filter(d => selected.has(d.uuid) && isLargeDoc(d)).length
  const sortedFolders = [...folders].sort((a, b) => a.path.localeCompare(b.path))

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.6)',
      }}
      onClick={() => { if (!submitting) onClose() }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Add Documents"
        style={{
          width: 560, maxWidth: 'calc(100vw - 24px)', maxHeight: '90dvh', overflow: 'hidden',
          backgroundColor: '#1e1e1e', borderRadius: 12,
          border: dragActive ? '1px dashed var(--highlight-color, #eab308)' : '1px solid #3a3a3a',
          padding: 16,
          display: 'flex', flexDirection: 'column', gap: 14,
          position: 'relative',
        }}
        onClick={e => e.stopPropagation()}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
      >
        {dragActive && (
          <div style={{
            position: 'absolute', inset: 0, borderRadius: 12, pointerEvents: 'none',
            backgroundColor: 'rgba(234, 179, 8, 0.08)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2,
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--highlight-color, #eab308)' }}>
              Drop files to upload
            </div>
          </div>
        )}

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#fff' }}>Add Documents</span>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            disabled={submitting}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
          >
            <X size={18} style={{ color: '#888' }} aria-hidden="true" />
          </button>
        </div>

        <div style={{ overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Upload row */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              aria-label="Upload files"
              accept={uploadPolicy.accept}
              onChange={onFileInputChange}
              style={{ display: 'none' }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={submitting}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 12px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
                color: 'var(--highlight-text-color, #000)', backgroundColor: 'var(--highlight-color, #eab308)',
                border: 'none', borderRadius: 6, cursor: 'pointer',
              }}
            >
              <Upload size={14} aria-hidden="true" />
              Upload files
            </button>
            <span style={{ fontSize: 12, color: '#888' }}>
              or drag &amp; drop anywhere in this dialog
            </span>
          </div>
          <span style={{ fontSize: 12, color: '#b8bec7', lineHeight: 1.6 }}>
            {uploadPolicy.description} Uploaded files are saved in Files; Add attaches the selected documents to this KB for indexing.
          </span>
        </div>

        {/* Folder filter + Search */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <div style={{ position: 'relative', flex: '1 1 160px', minWidth: 0 }}>
            <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#666' }} aria-hidden="true" />
            <input
              type="text"
              aria-label="Search documents by name or content"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search by name or content..."
              style={{
                width: '100%', padding: '10px 12px 10px 34px', fontSize: 13, fontFamily: 'inherit',
                backgroundColor: '#2a2a2a', color: '#e5e5e5',
                border: '1px solid #3a3a3a', borderRadius: 8,
                boxSizing: 'border-box',
              }}
            />
          </div>
          <div style={{ position: 'relative', flex: '1 1 160px', minWidth: 0 }}>
            <FolderIcon size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#666', pointerEvents: 'none' }} aria-hidden="true" />
            <select
              aria-label="Filter by folder"
              value={folderFilter}
              onChange={e => setFolderFilter(e.target.value)}
              style={{
                width: '100%', padding: '10px 10px 10px 30px', fontSize: 13, fontFamily: 'inherit',
                backgroundColor: '#2a2a2a', color: '#e5e5e5',
                border: '1px solid #3a3a3a', borderRadius: 8,
                appearance: 'none', boxSizing: 'border-box', cursor: 'pointer',
              }}
            >
              <option value="">All folders</option>
              <option value="__root__">Root (no folder)</option>
              {sortedFolders.map(f => (
                <option key={f.uuid} value={f.uuid}>{f.path}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Add entire folder */}
        {onSubmitFolder && folderFilter && folderFilter !== '__root__' && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8,
            padding: '8px 12px', backgroundColor: '#252525',
            border: '1px solid #333', borderRadius: 8,
          }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#bbb', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={includeSubfolders}
                onChange={e => setIncludeSubfolders(e.target.checked)}
                style={{ accentColor: 'var(--highlight-color, #eab308)', cursor: 'pointer' }}
              />
              Include subfolders
            </label>
            <button
              type="button"
              onClick={() => commit(true)}
              disabled={submitting || uploadingCount > 0}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                color: 'var(--highlight-text-color, #000)', backgroundColor: 'var(--highlight-color, #eab308)',
                border: 'none', borderRadius: 6, cursor: 'pointer', whiteSpace: 'nowrap',
              }}
            >
              <FolderIcon size={13} aria-hidden="true" />
              Add entire folder
            </button>
          </div>
        )}

        {/* Upload progress */}
        {uploads.length > 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 4,
            maxHeight: 100, overflowY: 'auto',
            padding: 8, backgroundColor: '#252525', borderRadius: 6,
            border: '1px solid #333',
          }}>
            {uploads.map(u => (
              <div key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                {u.status === 'uploading' && <Loader2 size={12} style={{ color: '#888', animation: 'spin 1s linear infinite' }} aria-hidden="true" />}
                {u.status === 'done' && <Check size={12} style={{ color: '#6a9955' }} aria-hidden="true" />}
                {u.status === 'error' && <X size={12} style={{ color: '#c75450' }} aria-hidden="true" />}
                <span style={{ color: '#ccc', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {u.name}
                </span>
                {u.status === 'error' && <span style={{ color: '#c75450', fontSize: 11 }}>{u.error}</span>}
                {u.status === 'done' && <span style={{ color: '#6a9955', fontSize: 11 }}>uploaded &amp; selected</span>}
                {u.status !== 'uploading' && (
                  <button
                    type="button"
                    onClick={() => removeUpload(u.id)}
                    aria-label={`Remove ${u.name}`}
                    title="Remove"
                    style={{
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      padding: 2, display: 'flex', color: '#888',
                    }}
                  >
                    <X size={12} aria-hidden="true" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Results */}
        {searchError && <div role="alert" style={{ fontSize: 13, color: '#fca5a5', lineHeight: 1.6 }}>{searchError} <button type="button" onClick={() => doSearch(query, folderFilter)} style={{ color: '#fff', background: '#333', border: '1px solid #666', borderRadius: 5, padding: '6px 10px' }}>Retry search</button></div>}
        <div role="region" aria-label="Available documents" tabIndex={0} style={{ flex: 1, overflowY: 'auto', maxHeight: 360, minHeight: 120 }}>
          {loading ? (
            <div role="status" aria-live="polite" style={{ textAlign: 'center', padding: 30, color: '#888' }}>
              <Loader2 style={{ width: 18, height: 18, margin: '0 auto', animation: 'spin 1s linear infinite' }} aria-hidden="true" />
              <span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Loading documents…</span>
            </div>
          ) : results.length === 0 ? (
            <div role="status" aria-live="polite" style={{ textAlign: 'center', padding: 30, color: '#888', fontSize: 13 }}>
              {query ? 'No documents found' : folderFilter ? 'No documents in this folder' : 'No documents available. Upload some above.'}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {results.map(doc => {
                const isSelected = selected.has(doc.uuid)
                const folderPath = folderPathByUuid(doc.folder)
                return (
                  <button
                    key={doc.uuid}
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => toggleDoc(doc.uuid)}
                    disabled={submitting}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '10px 12px', width: '100%', textAlign: 'left',
                      backgroundColor: isSelected ? '#2a3a2a' : '#2a2a2a',
                      border: isSelected ? '1px solid #4a7a4a' : '1px solid #3a3a3a',
                      borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
                      transition: 'background-color 0.1s',
                    }}
                  >
                    <div
                      style={{
                        width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                        border: isSelected ? 'none' : '1px solid #555',
                        backgroundColor: isSelected ? 'var(--highlight-color, #eab308)' : 'transparent',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      {isSelected && <Check size={12} style={{ color: '#000' }} aria-hidden="true" />}
                    </div>
                    <FileText size={14} style={{ color: '#888', flexShrink: 0 }} aria-hidden="true" />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13, color: '#e5e5e5', overflowWrap: 'anywhere',
                      }}>
                        {doc.title}
                      </div>
                      <div style={{
                        fontSize: 12, color: '#b8bec7', marginTop: 2,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {doc.extension.toUpperCase()}
                        {doc.num_pages > 0 ? ` · ${doc.num_pages} pages` : ''}
                        {folderPath ? ` · ${folderPath}` : ''}
                        {isLargeDoc(doc) && (
                          <span style={{ color: '#fbbf24' }}> · Large — slower to index</span>
                        )}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Heads-up before committing to a slow index */}
        {selectedLargeCount > 0 && (
          <div role="status" aria-live="polite" style={{
            fontSize: 12, color: '#fbbf24', marginBottom: 10,
            padding: '8px 12px', borderRadius: 6,
            backgroundColor: 'rgba(217, 119, 6, 0.1)',
            border: '1px solid rgba(217, 119, 6, 0.25)',
          }}>
            {selectedLargeCount === 1
              ? "One selected document is large — indexing it can take a few minutes."
              : `${selectedLargeCount} selected documents are large — indexing them can take a few minutes.`}
            {' '}You can keep working while it runs.
          </div>
        )}

        {/* Footer */}
        </div>
        {submitError && <div role="alert" style={{ color: '#fca5a5', fontSize: 13, lineHeight: 1.6, overflowWrap: 'anywhere' }}>{submitError}</div>}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, flexShrink: 0 }}>
          <span role="status" aria-live="polite" style={{ fontSize: 12, color: '#888' }}>
            {selected.size > 0 ? `${selected.size} selected` : ''}
            {uploadingCount > 0 ? `${selected.size > 0 ? ' · ' : ''}${uploadingCount} uploading` : ''}
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              style={{
                padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
                color: '#ccc', backgroundColor: 'transparent',
                border: '1px solid #3a3a3a', borderRadius: 6, cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={selected.size === 0 || uploadingCount > 0 || submitting}
              style={{
                padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                color: 'var(--highlight-text-color, #000)', backgroundColor: 'var(--highlight-color, #eab308)',
                border: 'none', borderRadius: 6,
                cursor: selected.size > 0 && uploadingCount === 0 ? 'pointer' : 'default',
                opacity: selected.size > 0 && uploadingCount === 0 ? 1 : 0.5,
              }}
            >
              {submitting ? 'Adding…' : `Add ${selected.size > 0 ? `(${selected.size})` : ''}`}
            </button>
          </div>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
