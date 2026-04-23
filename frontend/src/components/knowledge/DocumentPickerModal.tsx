import { useState, useEffect, useCallback, useRef } from 'react'
import { X, Search, FileText, Loader2, Check, Upload, FolderIcon } from 'lucide-react'
import { searchDocuments, type SearchResult } from '../../api/documents'
import { listAllFolders, type FolderSummary } from '../../api/folders'
import { uploadFile } from '../../api/files'

interface DocumentPickerModalProps {
  onSubmit: (docUuids: string[]) => void
  onClose: () => void
  existingSourceUuids?: string[]
}

type UploadStatus = 'uploading' | 'done' | 'error'
interface UploadItem {
  name: string
  status: UploadStatus
  uuid?: string
  error?: string
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

export function DocumentPickerModal({ onSubmit, onClose, existingSourceUuids = [] }: DocumentPickerModalProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [folders, setFolders] = useState<FolderSummary[]>([])
  const [folderFilter, setFolderFilter] = useState<string>('')  // '' = all folders
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragCounterRef = useRef(0)

  const doSearch = useCallback(async (q: string, folder: string) => {
    setLoading(true)
    try {
      const folderParam = folder === '' ? undefined : folder
      const data = await searchDocuments(q, 30, folderParam)
      setResults(data.items.filter(d => !existingSourceUuids.includes(d.uuid)))
    } catch (err) {
      console.error('Search failed:', err)
    } finally {
      setLoading(false)
    }
  }, [existingSourceUuids])

  // Load folders on mount
  useEffect(() => {
    listAllFolders()
      .then(setFolders)
      .catch(err => console.error('Failed to load folders:', err))
  }, [])

  // Load initial results and reload when folder filter changes
  useEffect(() => {
    doSearch(query, folderFilter)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folderFilter])

  // Debounced search on query change
  useEffect(() => {
    const timer = setTimeout(() => doSearch(query, folderFilter), 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  const toggleDoc = (uuid: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }

  const handleSubmit = () => {
    if (selected.size > 0) {
      onSubmit(Array.from(selected))
    }
  }

  const folderPathByUuid = useCallback((uuid: string | null | undefined) => {
    if (!uuid || uuid === '0' || uuid === '') return ''
    return folders.find(f => f.uuid === uuid)?.path ?? ''
  }, [folders])

  const handleFiles = async (files: File[]) => {
    if (files.length === 0) return
    const targetFolder = folderFilter && folderFilter !== '__root__' ? folderFilter : undefined
    const initial: UploadItem[] = files.map(f => ({ name: f.name, status: 'uploading' }))
    setUploads(prev => [...prev, ...initial])
    const startIdx = uploads.length
    const newUuids: string[] = []
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      const ext = file.name.split('.').pop() || ''
      try {
        const base64 = await fileToBase64(file)
        const result = await uploadFile({
          contentAsBase64String: base64,
          fileName: file.name,
          extension: ext,
          folder: targetFolder,
        })
        if (result.uuid) {
          newUuids.push(result.uuid)
          setUploads(prev => {
            const next = [...prev]
            next[startIdx + i] = { ...next[startIdx + i], status: 'done', uuid: result.uuid }
            return next
          })
        } else {
          setUploads(prev => {
            const next = [...prev]
            next[startIdx + i] = { ...next[startIdx + i], status: 'error', error: 'Upload failed' }
            return next
          })
        }
      } catch (err) {
        setUploads(prev => {
          const next = [...prev]
          next[startIdx + i] = {
            ...next[startIdx + i],
            status: 'error',
            error: err instanceof Error ? err.message : 'Upload failed',
          }
          return next
        })
      }
    }
    if (newUuids.length > 0) {
      setSelected(prev => {
        const next = new Set(prev)
        newUuids.forEach(u => next.add(u))
        return next
      })
      // Refresh list so uploaded docs are visible in results
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
  const sortedFolders = [...folders].sort((a, b) => a.path.localeCompare(b.path))

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.6)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 560, maxHeight: '85vh',
          backgroundColor: '#1e1e1e', borderRadius: 12,
          border: dragActive ? '1px dashed var(--highlight-color, #eab308)' : '1px solid #3a3a3a',
          padding: 24,
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
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#fff' }}>Add Documents</span>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
          >
            <X size={18} style={{ color: '#888' }} />
          </button>
        </div>

        {/* Upload row */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={onFileInputChange}
            style={{ display: 'none' }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 12px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
              color: '#000', backgroundColor: 'var(--highlight-color, #eab308)',
              border: 'none', borderRadius: 6, cursor: 'pointer',
            }}
          >
            <Upload size={14} />
            Upload files
          </button>
          <span style={{ fontSize: 12, color: '#888' }}>
            or drag &amp; drop anywhere in this dialog
          </span>
        </div>

        {/* Folder filter + Search */}
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#666' }} />
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search by name or content..."
              style={{
                width: '100%', padding: '10px 12px 10px 34px', fontSize: 13, fontFamily: 'inherit',
                backgroundColor: '#2a2a2a', color: '#e5e5e5',
                border: '1px solid #3a3a3a', borderRadius: 8, outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
          <div style={{ position: 'relative', width: 180 }}>
            <FolderIcon size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#666', pointerEvents: 'none' }} />
            <select
              value={folderFilter}
              onChange={e => setFolderFilter(e.target.value)}
              style={{
                width: '100%', padding: '10px 10px 10px 30px', fontSize: 13, fontFamily: 'inherit',
                backgroundColor: '#2a2a2a', color: '#e5e5e5',
                border: '1px solid #3a3a3a', borderRadius: 8, outline: 'none',
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

        {/* Upload progress */}
        {uploads.length > 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 4,
            maxHeight: 100, overflowY: 'auto',
            padding: 8, backgroundColor: '#252525', borderRadius: 6,
            border: '1px solid #333',
          }}>
            {uploads.map((u, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                {u.status === 'uploading' && <Loader2 size={12} style={{ color: '#888', animation: 'spin 1s linear infinite' }} />}
                {u.status === 'done' && <Check size={12} style={{ color: '#6a9955' }} />}
                {u.status === 'error' && <X size={12} style={{ color: '#c75450' }} />}
                <span style={{ color: '#ccc', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {u.name}
                </span>
                {u.status === 'error' && <span style={{ color: '#c75450', fontSize: 11 }}>{u.error}</span>}
                {u.status === 'done' && <span style={{ color: '#6a9955', fontSize: 11 }}>uploaded &amp; selected</span>}
              </div>
            ))}
          </div>
        )}

        {/* Results */}
        <div style={{ flex: 1, overflowY: 'auto', maxHeight: 360, minHeight: 120 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 30, color: '#888' }}>
              <Loader2 style={{ width: 18, height: 18, margin: '0 auto', animation: 'spin 1s linear infinite' }} />
            </div>
          ) : results.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 30, color: '#888', fontSize: 13 }}>
              {query ? 'No documents found' : folderFilter ? 'No documents in this folder' : 'No documents available — upload some above'}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {results.map(doc => {
                const isSelected = selected.has(doc.uuid)
                const folderPath = folderPathByUuid(doc.folder)
                return (
                  <button
                    key={doc.uuid}
                    onClick={() => toggleDoc(doc.uuid)}
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
                      {isSelected && <Check size={12} style={{ color: '#000' }} />}
                    </div>
                    <FileText size={14} style={{ color: '#888', flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13, color: '#e5e5e5', overflow: 'hidden',
                        textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {doc.title}
                      </div>
                      <div style={{
                        fontSize: 11, color: '#888', marginTop: 2,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {doc.extension.toUpperCase()}
                        {doc.num_pages > 0 ? ` · ${doc.num_pages} pages` : ''}
                        {folderPath ? ` · ${folderPath}` : ''}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: '#888' }}>
            {selected.size > 0 ? `${selected.size} selected` : ''}
            {uploadingCount > 0 ? `${selected.size > 0 ? ' · ' : ''}${uploadingCount} uploading` : ''}
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={onClose}
              style={{
                padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
                color: '#ccc', backgroundColor: 'transparent',
                border: '1px solid #3a3a3a', borderRadius: 6, cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={selected.size === 0 || uploadingCount > 0}
              style={{
                padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                color: '#000', backgroundColor: 'var(--highlight-color, #eab308)',
                border: 'none', borderRadius: 6,
                cursor: selected.size > 0 && uploadingCount === 0 ? 'pointer' : 'default',
                opacity: selected.size > 0 && uploadingCount === 0 ? 1 : 0.5,
              }}
            >
              Add {selected.size > 0 ? `(${selected.size})` : ''}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
