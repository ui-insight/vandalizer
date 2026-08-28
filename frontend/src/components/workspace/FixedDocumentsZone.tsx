import { useRef, useState } from 'react'
import { FileText, FolderSearch, Loader2, Plus, Upload, X } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useToast } from '../../contexts/ToastContext'
import { uploadFile } from '../../api/files'
import { searchDocuments } from '../../api/documents'
import { DocumentPickerDialog } from '../shared/DocumentPickerDialog'

/**
 * A fixed document on the Input tab. `missing` is set by the server on read
 * when the document has been deleted from Files; it is never saved back.
 */
export interface FixedDocument { uuid: string; title: string; missing?: boolean }

export function stripFixedDocumentFlags(doc: FixedDocument): { uuid: string; title: string } {
  return { uuid: doc.uuid, title: doc.title }
}

/** Red "Deleted from Files" pill shown next to a fixed document whose source was deleted. */
export function DeletedDocumentBadge() {
  return (
    <span
      role="status"
      title="This document was deleted from Files. Runs will fail until it is removed here or replaced."
      style={{
        fontSize: 10, fontWeight: 700, color: '#b91c1c', backgroundColor: '#fee2e2',
        border: '1px solid #fecaca', borderRadius: 999, padding: '1px 6px', whiteSpace: 'nowrap',
      }}
    >
      Deleted from Files
    </span>
  )
}

/**
 * The "Fixed Documents" picker on a workflow's Input tab: documents pinned
 * to every run. Two explicit ways in, each saying where it looks — **Choose
 * from Vandalizer** (the library picker) and **Upload from your computer**
 * (a file dialog; the file becomes a Vandalizer document and is pinned) —
 * plus a drop zone that takes both an OS file and a document dragged from the
 * file browser. Before this the only click target opened the library picker
 * with no label saying so, and a local file could only arrive by drag-drop,
 * which nothing advertised (support ticket). Upload failures were swallowed;
 * they now toast.
 */
export function FixedDocumentsZone({
  fixedDocs,
  onAddDocs,
  onRemoveDoc,
  readOnly = false,
}: {
  fixedDocs: FixedDocument[]
  onAddDocs: (docs: FixedDocument[]) => Promise<void> | void
  onRemoveDoc: (uuid: string) => void
  // View-only workflows: list the pinned documents, hide every way to change them.
  readOnly?: boolean
}) {
  const { selectedDocUuids, selectedDocNames } = useWorkspace()
  const { toast } = useToast()
  const [dragOver, setDragOver] = useState(false)
  const [uploadingName, setUploadingName] = useState<string | null>(null)
  const [showPicker, setShowPicker] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const existingUuids = new Set(fixedDocs.map(d => d.uuid))
  const addableSelected = selectedDocUuids.filter(uuid => !existingUuids.has(uuid))
  const uploading = uploadingName !== null

  const readAsBase64 = (file: File) => new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      resolve(result.split(',')[1] || result)
    }
    reader.onerror = () => reject(reader.error ?? new Error('Could not read file'))
    reader.readAsDataURL(file)
  })

  /** Upload one local file as a Vandalizer document and pin it. */
  const handleFileUpload = async (file: File) => {
    setUploadingName(file.name)
    try {
      const base64 = await readAsBase64(file)
      const ext = file.name.split('.').pop() || ''
      const res = await uploadFile({ contentAsBase64String: base64, fileName: file.name, extension: ext })
      if (!res.uuid) {
        toast(`Could not upload ${file.name}`, 'error')
        return
      }
      await onAddDocs([{ uuid: res.uuid, title: file.name }])
      toast(res.exists ? `${file.name} was already in Vandalizer — pinned the existing copy` : `Uploaded ${file.name}`, 'success')
    } catch (err) {
      toast(err instanceof Error ? `Could not upload ${file.name}: ${err.message}` : `Could not upload ${file.name}`, 'error')
    } finally {
      setUploadingName(null)
    }
  }

  const handleFiles = async (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      await handleFileUpload(file)
    }
  }

  const handleDroppedUuid = async (uuid: string) => {
    // Look up title via search; fall back to a stub if lookup fails.
    let title = `Document ${uuid.slice(0, 8)}`
    try {
      const res = await searchDocuments('', 100)
      const match = res.items.find(d => d.uuid === uuid)
      if (match) title = match.title
    } catch { /* keep stub title */ }
    await onAddDocs([{ uuid, title }])
  }

  const actionButton: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px',
    fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
    border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
    color: '#374151', cursor: uploading ? 'wait' : 'pointer', opacity: uploading ? 0.6 : 1,
  }

  return (
    <>
      {fixedDocs.length > 0 && (
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden',
          backgroundColor: '#fff', marginBottom: 8,
        }}>
          {fixedDocs.map((doc, idx) => (
            <div
              key={doc.uuid}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
                borderBottom: idx < fixedDocs.length - 1 ? '1px solid #f3f4f6' : 'none',
                fontSize: 13,
                backgroundColor: doc.missing ? '#fef2f2' : undefined,
              }}
            >
              <FileText style={{ width: 13, height: 13, color: doc.missing ? '#b91c1c' : '#6b7280', flexShrink: 0 }} />
              <span style={{
                flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                color: doc.missing ? '#991b1b' : undefined,
                textDecoration: doc.missing ? 'line-through' : 'none',
              }}>
                {doc.title}
              </span>
              {doc.missing && <DeletedDocumentBadge />}
              {!readOnly && (
                <button
                  type="button"
                  onClick={() => onRemoveDoc(doc.uuid)}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer', padding: 2,
                    color: '#6b7280', display: 'flex',
                  }}
                  aria-label={doc.missing ? `Remove deleted document ${doc.title}` : `Remove ${doc.title}`}
                >
                  <X style={{ width: 14, height: 14 }} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {readOnly && fixedDocs.length === 0 && (
        <div style={{ fontSize: 12, color: '#9ca3af' }}>No fixed documents.</div>
      )}

      {!readOnly && (
        <>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
            <button
              type="button"
              onClick={() => { if (!uploading) setShowPicker(true) }}
              disabled={uploading}
              style={actionButton}
              title="Pick documents already in your Vandalizer library"
            >
              <FolderSearch style={{ width: 14, height: 14 }} />
              Choose from Vandalizer
            </button>
            <button
              type="button"
              onClick={() => { if (!uploading) fileInputRef.current?.click() }}
              disabled={uploading}
              style={actionButton}
              title="Upload a file from this computer; it is added to Vandalizer and pinned here"
            >
              <Upload style={{ width: 14, height: 14 }} />
              Upload from your computer
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              aria-label="Upload files from your computer"
              style={{ display: 'none' }}
              onChange={async e => {
                const files = e.target.files
                // Reset first so picking the same file again re-fires onChange.
                e.target.value = ''
                if (files && files.length) await handleFiles(files)
              }}
            />
          </div>

          <div
            data-testid="fixed-docs-dropzone"
            onDragOver={e => {
              e.preventDefault()
              e.stopPropagation()
              if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
              setDragOver(true)
            }}
            onDragLeave={e => { e.preventDefault(); e.stopPropagation(); setDragOver(false) }}
            onDrop={async e => {
              e.preventDefault()
              e.stopPropagation()
              setDragOver(false)
              if (uploading) return
              // Internal drag from FileBrowser: text/plain = doc uuid
              const uuid = e.dataTransfer.getData('text/plain')
              if (uuid && !e.dataTransfer.files.length) {
                await handleDroppedUuid(uuid)
                return
              }
              // OS file drop: upload each as a new document
              await handleFiles(e.dataTransfer.files)
            }}
            style={{
              border: `2px dashed ${dragOver ? 'var(--highlight-color, #eab308)' : '#d1d5db'}`,
              borderRadius: 8, padding: '16px', textAlign: 'center',
              color: '#6b7280', fontSize: 12,
              backgroundColor: dragOver ? '#fefce8' : '#fff',
              transition: 'all 0.15s ease',
            }}
          >
            {uploading ? (
              <div role="status" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <Loader2 aria-hidden="true" style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} />
                Uploading {uploadingName}…
              </div>
            ) : (
              <div>Or drop files from your computer, or a document from the file browser, here</div>
            )}
          </div>
        </>
      )}

      {!readOnly && addableSelected.length > 0 && (
        <button
          type="button"
          onClick={async () => {
            const docs = addableSelected.map(uuid => ({
              uuid,
              title: selectedDocNames[uuid] || `Document ${uuid.slice(0, 8)}`,
            }))
            await onAddDocs(docs)
          }}
          style={{
            marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '6px 12px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
            borderRadius: 6, border: '1px dashed #93c5fd', backgroundColor: '#eff6ff',
            color: '#1d4ed8', cursor: 'pointer',
          }}
        >
          <Plus style={{ width: 12, height: 12 }} />
          Add {addableSelected.length} selected document{addableSelected.length !== 1 ? 's' : ''}
        </button>
      )}

      {showPicker && (
        <DocumentPickerDialog
          title="Choose from your Vandalizer documents"
          onSelect={async docs => { await onAddDocs(docs) }}
          onClose={() => setShowPicker(false)}
          excludeUuids={fixedDocs.map(d => d.uuid)}
        />
      )}
    </>
  )
}
