import { useEffect, useRef, useState } from 'react'
import { FileText, Loader2, Plus, Search, Upload, X } from 'lucide-react'
import { searchDocuments, pollStatus as pollDocumentStatus } from '../../api/documents'
import { uploadFile } from '../../api/files'
import { updateWorkflow } from '../../api/workflows'
import { useToast } from '../../contexts/ToastContext'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { DeletedDocumentBadge, stripFixedDocumentFlags, type FixedDocument } from './FixedDocumentsZone'
import { toggleSource, type StepInputValue, type TaskInputSource } from './stepInputConfig'

/**
 * The data-source picker for one step.
 *
 * Lives at the step level because that is where it takes effect: the step's
 * tasks all receive the same payload. The same control is reused, bound to a
 * task instead, behind the advanced per-task override.
 */
export function StepInputSources({
  value, onChange, workflowId, workflowInputConfig, onRefreshWorkflow, disabled = false,
}: {
  value: StepInputValue
  onChange: (next: StepInputValue) => void
  workflowId: string | null
  workflowInputConfig: Record<string, unknown> | undefined
  onRefreshWorkflow: () => void
  disabled?: boolean
}) {
  const { toast } = useToast()
  const { selectedDocUuids, selectedDocNames } = useWorkspace()

  const sources = value.sources
  const wantsSelectDocument = sources.includes('select_document')
  const wantsWorkflowDocs = sources.includes('workflow_documents')

  const toggle = (src: TaskInputSource) => {
    if (disabled) return
    onChange({ ...value, sources: toggleSource(sources, src) })
  }

  // --- Single pinned document ------------------------------------------------
  const [docSearchQuery, setDocSearchQuery] = useState('')
  const [selectedDocTitle, setSelectedDocTitle] = useState('')
  const [docSearchResults, setDocSearchResults] = useState<{ uuid: string; title: string }[]>([])
  const [showDocDropdown, setShowDocDropdown] = useState(false)
  const [docHighlight, setDocHighlight] = useState(0)

  // Only the UUID is stored — fetch the title so the chip reads as a filename
  // instead of a raw UUID when the editor reopens.
  useEffect(() => {
    if (!value.selectedDocUuid) { setSelectedDocTitle(''); return }
    let cancelled = false
    pollDocumentStatus(value.selectedDocUuid)
      .then(res => { if (!cancelled && res?.title) setSelectedDocTitle(res.title) })
      .catch(() => { /* leave title empty; chip falls back to the UUID */ })
    return () => { cancelled = true }
  }, [value.selectedDocUuid])

  // Document search debounce — uses searchDocuments so files in any folder
  // (personal subfolders, team folders) are findable, not just the root.
  // Empty query loads recent docs so the field doubles as a browsable picker.
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!wantsSelectDocument) return
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current)
    const query = docSearchQuery.trim()
    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const res = await searchDocuments(query, 20)
        setDocSearchResults(res.items.map(d => ({ uuid: d.uuid, title: d.title })))
      } catch (err) {
        console.error('Document search failed', err)
        setDocSearchResults([])
      }
    }, query ? 250 : 0)
    return () => { if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current) }
  }, [docSearchQuery, wantsSelectDocument])

  const pickDocument = (doc: { uuid: string; title: string }) => {
    onChange({ ...value, selectedDocUuid: doc.uuid })
    setSelectedDocTitle(doc.title)
    setDocSearchQuery(doc.title)
    setShowDocDropdown(false)
  }

  // --- Fixed documents (workflow-level) -------------------------------------
  const [fixedDocs, setFixedDocs] = useState<FixedDocument[]>(
    () => ((workflowInputConfig?.fixed_documents as FixedDocument[]) || [])
  )
  const [fixedDocSearch, setFixedDocSearch] = useState('')
  const [fixedDocResults, setFixedDocResults] = useState<{ uuid: string; title: string }[]>([])
  const [showFixedDocDropdown, setShowFixedDocDropdown] = useState(false)
  const [fixedDocHighlight, setFixedDocHighlight] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const saveFixedDocs = async (docs: FixedDocument[]) => {
    const previous = fixedDocs
    setFixedDocs(docs)  // optimistic — refresh reconciles on success
    if (!workflowId) return
    try {
      await updateWorkflow(workflowId, {
        input_config: { ...workflowInputConfig, fixed_documents: docs.map(stripFixedDocumentFlags) },
      })
      onRefreshWorkflow()
    } catch (err) {
      setFixedDocs(previous)
      toast(err instanceof Error && err.message ? err.message : "Couldn't save fixed documents. Please try again.", 'error')
    }
  }

  const addFixedDoc = (doc: { uuid: string; title: string }) => {
    if (fixedDocs.some(d => d.uuid === doc.uuid)) return
    void saveFixedDocs([...fixedDocs, doc])
  }

  const removeFixedDoc = (uuid: string) => {
    void saveFixedDocs(fixedDocs.filter(d => d.uuid !== uuid))
  }

  const handleFileUpload = async (file: File) => {
    setUploading(true)
    try {
      const reader = new FileReader()
      const base64 = await new Promise<string>((resolve, reject) => {
        reader.onload = () => {
          const result = reader.result as string
          resolve(result.split(',')[1] || result)
        }
        reader.onerror = reject
        reader.readAsDataURL(file)
      })
      const ext = file.name.split('.').pop() || ''
      const { uuid } = await uploadFile({
        contentAsBase64String: base64,
        fileName: file.name,
        extension: ext,
      })
      if (uuid) addFixedDoc({ uuid, title: file.name })
    } catch { /* ignore upload errors */ }
    finally { setUploading(false) }
  }

  // Fixed doc search debounce — empty query loads recent docs so the field
  // doubles as a browsable picker.
  const fixedSearchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!wantsWorkflowDocs) return
    if (fixedSearchTimeoutRef.current) clearTimeout(fixedSearchTimeoutRef.current)
    const query = fixedDocSearch.trim()
    fixedSearchTimeoutRef.current = setTimeout(async () => {
      try {
        const res = await searchDocuments(query, 20)
        setFixedDocResults(
          res.items
            .filter(d => !fixedDocs.some(fd => fd.uuid === d.uuid))
            .map(d => ({ uuid: d.uuid, title: d.title }))
        )
      } catch (err) {
        console.error('Document search failed', err)
        setFixedDocResults([])
      }
    }, query ? 250 : 0)
    return () => { if (fixedSearchTimeoutRef.current) clearTimeout(fixedSearchTimeoutRef.current) }
  }, [fixedDocSearch, wantsWorkflowDocs, fixedDocs])

  const cardStyle = (on: boolean) => ({
    display: 'flex' as const, alignItems: 'flex-start' as const, gap: 10, padding: 12,
    border: on ? '2px solid var(--highlight-color, #eab308)' : '1px solid #e5e7eb',
    borderRadius: 8, cursor: disabled ? 'default' : 'pointer', backgroundColor: '#fff',
    opacity: disabled ? 0.7 : 1,
  })

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
        Data Sources
      </div>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        Pick one or more. Multiple selections are combined in labeled sections — e.g.,
        check Step Input + Workflow Documents to give this step both the prior output and the original documents.
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {/* Step Input */}
        <label style={cardStyle(sources.includes('step_input'))}>
          <input
            type="checkbox"
            checked={sources.includes('step_input')}
            disabled={disabled}
            onChange={() => toggle('step_input')}
            style={{ marginTop: 2 }}
          />
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>Step Input</div>
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
              Only the output of the immediately previous step — no documents, no earlier
              steps. Pair with another source to also include document context.
            </div>
          </div>
        </label>

        {/* Select a Document */}
        <label style={cardStyle(wantsSelectDocument)}>
          <input
            type="checkbox"
            checked={wantsSelectDocument}
            disabled={disabled}
            onChange={() => toggle('select_document')}
            style={{ marginTop: 2 }}
          />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>Select a Document</div>
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
              A single document pinned to this step now — used every run, regardless of
              what triggered the workflow.
            </div>
            {wantsSelectDocument && (
              <div style={{ marginTop: 8, position: 'relative' }} onClick={e => e.stopPropagation()}>
                <input
                  aria-label="Search documents"
                  role="combobox"
                  aria-expanded={showDocDropdown}
                  aria-controls="doc-search-listbox"
                  aria-autocomplete="list"
                  aria-haspopup="listbox"
                  aria-activedescendant={showDocDropdown && docSearchResults.length > 0 ? `doc-search-opt-${Math.min(docHighlight, docSearchResults.length - 1)}` : undefined}
                  type="text"
                  value={docSearchQuery}
                  disabled={disabled}
                  onChange={e => { setDocSearchQuery(e.target.value); setDocHighlight(0) }}
                  placeholder="Search documents..."
                  style={{
                    width: '100%', padding: '8px 12px', fontSize: 13,
                    fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                    outline: 'none', boxSizing: 'border-box',
                  }}
                  onFocus={() => setShowDocDropdown(true)}
                  onBlur={() => setTimeout(() => setShowDocDropdown(false), 200)}
                  onKeyDown={e => {
                    if (e.key === 'Escape') {
                      setShowDocDropdown(false)
                    } else if (e.key === 'ArrowDown') {
                      e.preventDefault()
                      setShowDocDropdown(true)
                      setDocHighlight(h => Math.min(h + 1, docSearchResults.length - 1))
                    } else if (e.key === 'ArrowUp') {
                      e.preventDefault()
                      setDocHighlight(h => Math.max(h - 1, 0))
                    } else if (e.key === 'Enter' && showDocDropdown && docSearchResults.length > 0) {
                      e.preventDefault()
                      pickDocument(docSearchResults[Math.min(docHighlight, docSearchResults.length - 1)])
                    }
                  }}
                />
                {showDocDropdown && (
                  <div id="doc-search-listbox" role="listbox" aria-label="Document search results" style={{
                    position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4,
                    backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
                    boxShadow: '0 8px 24px rgba(0,0,0,0.12)', zIndex: 10,
                    maxHeight: 200, overflowY: 'auto',
                  }}>
                    {docSearchResults.length === 0 ? (
                      <div style={{ padding: '8px 12px', fontSize: 13, color: '#6b7280' }}>
                        No documents found
                      </div>
                    ) : docSearchResults.map((doc, i) => (
                      <div
                        key={doc.uuid}
                        id={`doc-search-opt-${i}`}
                        role="option"
                        aria-selected={doc.uuid === value.selectedDocUuid}
                        onMouseEnter={() => setDocHighlight(i)}
                        onMouseDown={() => pickDocument(doc)}
                        style={{
                          padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                          display: 'flex', alignItems: 'center', gap: 8,
                          backgroundColor: i === Math.min(docHighlight, docSearchResults.length - 1) || doc.uuid === value.selectedDocUuid ? '#f3f4f6' : '#fff',
                        }}
                      >
                        <FileText style={{ width: 14, height: 14, color: '#6b7280', flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {doc.title}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {value.selectedDocUuid && !showDocDropdown && (
                  <div style={{
                    marginTop: 6, display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 10px', backgroundColor: '#f3f4f6', borderRadius: 6, fontSize: 12,
                  }}>
                    <FileText style={{ width: 12, height: 12, color: '#6b7280' }} />
                    <span
                      style={{ color: '#374151', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={selectedDocTitle ? `${selectedDocTitle} (${value.selectedDocUuid})` : value.selectedDocUuid}
                    >
                      {selectedDocTitle || value.selectedDocUuid}
                    </span>
                    <button
                      type="button"
                      aria-label="Clear selected document"
                      disabled={disabled}
                      onClick={() => { onChange({ ...value, selectedDocUuid: '' }); setSelectedDocTitle(''); setDocSearchQuery('') }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#6b7280', display: 'flex' }}
                    >
                      <X style={{ width: 12, height: 12 }} />
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </label>

        {/* Workflow Documents */}
        <label style={cardStyle(wantsWorkflowDocs)}>
          <input
            type="checkbox"
            checked={wantsWorkflowDocs}
            disabled={disabled}
            onChange={() => toggle('workflow_documents')}
            style={{ marginTop: 2 }}
          />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#202124' }}>Workflow Documents</div>
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
              The documents the workflow was triggered with this run, plus any fixed
              documents pinned below at the workflow level.
            </div>

            {wantsWorkflowDocs && (
              <div style={{ marginTop: 10 }} onClick={e => e.stopPropagation()}>
                {/* Fixed documents list */}
                {fixedDocs.length > 0 && (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                      Fixed Documents
                    </div>
                    {fixedDocs.map(doc => (
                      <div key={doc.uuid} style={{
                        display: 'flex', alignItems: 'center', gap: 6, padding: '5px 8px',
                        backgroundColor: doc.missing ? '#fef2f2' : '#f3f4f6',
                        border: `1px solid ${doc.missing ? '#fecaca' : 'transparent'}`,
                        borderRadius: 6, fontSize: 12, marginBottom: 4,
                      }}>
                        <FileText style={{ width: 12, height: 12, color: doc.missing ? '#b91c1c' : '#6b7280', flexShrink: 0 }} />
                        <span style={{
                          color: doc.missing ? '#991b1b' : '#374151', flex: 1, overflow: 'hidden',
                          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          textDecoration: doc.missing ? 'line-through' : 'none',
                        }}>
                          {doc.title}
                        </span>
                        {doc.missing && <DeletedDocumentBadge />}
                        <button
                          type="button"
                          aria-label={doc.missing ? `Remove deleted document ${doc.title}` : 'Remove document'}
                          disabled={disabled}
                          onClick={() => removeFixedDoc(doc.uuid)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#6b7280', display: 'flex' }}
                        >
                          <X style={{ width: 12, height: 12 }} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Search existing documents */}
                <div style={{ position: 'relative', marginBottom: 8 }}>
                  <div style={{ position: 'relative' }}>
                    <Search style={{ width: 13, height: 13, position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: '#6b7280' }} />
                    <input
                      aria-label="Search documents by name"
                      role="combobox"
                      aria-expanded={showFixedDocDropdown}
                      aria-controls="fixed-doc-listbox"
                      aria-autocomplete="list"
                      aria-haspopup="listbox"
                      aria-activedescendant={showFixedDocDropdown && fixedDocResults.length > 0 ? `fixed-doc-opt-${Math.min(fixedDocHighlight, fixedDocResults.length - 1)}` : undefined}
                      type="text"
                      value={fixedDocSearch}
                      disabled={disabled}
                      onChange={e => { setFixedDocSearch(e.target.value); setFixedDocHighlight(0) }}
                      placeholder="Search documents by name..."
                      style={{
                        width: '100%', padding: '7px 10px 7px 28px', fontSize: 12,
                        fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6,
                        outline: 'none', boxSizing: 'border-box',
                      }}
                      onFocus={() => setShowFixedDocDropdown(true)}
                      onBlur={() => setTimeout(() => setShowFixedDocDropdown(false), 200)}
                      onKeyDown={e => {
                        if (e.key === 'Escape') {
                          setShowFixedDocDropdown(false)
                        } else if (e.key === 'ArrowDown') {
                          e.preventDefault()
                          setShowFixedDocDropdown(true)
                          setFixedDocHighlight(h => Math.min(h + 1, fixedDocResults.length - 1))
                        } else if (e.key === 'ArrowUp') {
                          e.preventDefault()
                          setFixedDocHighlight(h => Math.max(h - 1, 0))
                        } else if (e.key === 'Enter' && showFixedDocDropdown && fixedDocResults.length > 0) {
                          e.preventDefault()
                          addFixedDoc(fixedDocResults[Math.min(fixedDocHighlight, fixedDocResults.length - 1)])
                          setFixedDocSearch('')
                          setShowFixedDocDropdown(false)
                        }
                      }}
                    />
                  </div>
                  {showFixedDocDropdown && (
                    <div id="fixed-doc-listbox" role="listbox" aria-label="Document search results" style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4,
                      backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
                      boxShadow: '0 8px 24px rgba(0,0,0,0.12)', zIndex: 10,
                      maxHeight: 160, overflowY: 'auto',
                    }}>
                      {fixedDocResults.length === 0 ? (
                        <div style={{ padding: '7px 10px', fontSize: 12, color: '#6b7280' }}>
                          No documents found
                        </div>
                      ) : fixedDocResults.map((doc, i) => (
                        <div
                          key={doc.uuid}
                          id={`fixed-doc-opt-${i}`}
                          role="option"
                          aria-selected={i === Math.min(fixedDocHighlight, fixedDocResults.length - 1)}
                          onMouseEnter={() => setFixedDocHighlight(i)}
                          onMouseDown={() => {
                            addFixedDoc(doc)
                            setFixedDocSearch('')
                            setShowFixedDocDropdown(false)
                          }}
                          style={{
                            padding: '7px 10px', fontSize: 12, cursor: 'pointer',
                            display: 'flex', alignItems: 'center', gap: 6,
                            backgroundColor: i === Math.min(fixedDocHighlight, fixedDocResults.length - 1) ? '#f3f4f6' : '#fff',
                          }}
                        >
                          <FileText style={{ width: 13, height: 13, color: '#6b7280', flexShrink: 0 }} />
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {doc.title}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Drag & drop zone + upload button */}
                <div
                  onDragOver={e => { e.preventDefault(); e.stopPropagation(); setDragOver(true) }}
                  onDragLeave={e => { e.preventDefault(); e.stopPropagation(); setDragOver(false) }}
                  onDrop={async e => {
                    e.preventDefault()
                    e.stopPropagation()
                    setDragOver(false)
                    if (disabled) return
                    const files = Array.from(e.dataTransfer.files)
                    for (const file of files) {
                      await handleFileUpload(file)
                    }
                  }}
                  style={{
                    border: `2px dashed ${dragOver ? 'var(--highlight-color, #eab308)' : '#d1d5db'}`,
                    borderRadius: 8, padding: '14px 12px', textAlign: 'center',
                    backgroundColor: dragOver ? '#fefce8' : '#fafafa',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {uploading ? (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                      <Loader2 aria-hidden="true" style={{ width: 14, height: 14, animation: 'spin 1s linear infinite', color: '#6b7280' }} />
                      <span style={{ fontSize: 12, color: '#6b7280' }}>Uploading...</span>
                    </div>
                  ) : (
                    <>
                      <Upload style={{ width: 18, height: 18, color: '#6b7280', margin: '0 auto 4px' }} />
                      <div style={{ fontSize: 12, color: '#6b7280' }}>
                        Drag &amp; drop files here
                      </div>
                      <button
                        type="button"
                        disabled={disabled}
                        onClick={() => fileInputRef.current?.click()}
                        style={{
                          marginTop: 6, padding: '4px 12px', fontSize: 12, fontWeight: 500,
                          fontFamily: 'inherit', borderRadius: 5, border: '1px solid #d1d5db',
                          backgroundColor: '#fff', color: '#374151', cursor: 'pointer',
                        }}
                      >
                        Browse Files
                      </button>
                      <input
                        aria-label="Upload files"
                        ref={fileInputRef}
                        type="file"
                        multiple
                        style={{ display: 'none' }}
                        onChange={async e => {
                          const files = Array.from(e.target.files || [])
                          for (const file of files) {
                            await handleFileUpload(file)
                          }
                          e.target.value = ''
                        }}
                      />
                    </>
                  )}
                </div>

                {/* Quick add selected docs from file browser */}
                {(() => {
                  const existing = new Set(fixedDocs.map(d => d.uuid))
                  const addable = selectedDocUuids.filter(uuid => !existing.has(uuid))
                  if (addable.length === 0 || disabled) return null
                  return (
                    <button
                      type="button"
                      onClick={() => {
                        for (const uuid of addable) {
                          addFixedDoc({
                            uuid,
                            title: selectedDocNames[uuid] || `Document ${uuid.slice(0, 8)}`,
                          })
                        }
                      }}
                      style={{
                        marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 4,
                        padding: '6px 12px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
                        borderRadius: 6, border: '1px dashed #93c5fd', backgroundColor: '#eff6ff',
                        color: '#1d4ed8', cursor: 'pointer',
                      }}
                    >
                      <Plus style={{ width: 12, height: 12 }} />
                      Add {addable.length} selected document{addable.length !== 1 ? 's' : ''}
                    </button>
                  )
                })()}
              </div>
            )}
          </div>
        </label>
      </div>
    </div>
  )
}
