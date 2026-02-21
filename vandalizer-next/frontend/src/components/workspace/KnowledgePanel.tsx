import { useState, useEffect, useCallback } from 'react'
import { Plus, Loader2, BookOpen, ArrowLeft, Trash2, X, FileText, Globe, MessageSquare, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useKnowledgeBases } from '../../hooks/useKnowledgeBases'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import * as api from '../../api/knowledge'
import type { KnowledgeBaseDetail, KnowledgeBaseSource } from '../../types/knowledge'
import { AddUrlsModal } from '../knowledge/AddUrlsModal'
import { DocumentPickerModal } from '../knowledge/DocumentPickerModal'

const STATUS_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  empty: { label: 'Empty', color: '#6b7280', bg: '#f3f4f6' },
  building: { label: 'Building', color: '#d97706', bg: '#fef3c7' },
  ready: { label: 'Ready', color: '#15803d', bg: '#dcfce7' },
  error: { label: 'Error', color: '#b91c1c', bg: '#fef2f2' },
}

const SOURCE_STATUS: Record<string, { icon: typeof CheckCircle2; color: string }> = {
  pending: { icon: Loader2, color: '#6b7280' },
  processing: { icon: Loader2, color: '#d97706' },
  ready: { icon: CheckCircle2, color: '#15803d' },
  error: { icon: AlertCircle, color: '#b91c1c' },
}

export function KnowledgePanel() {
  const { activateKB } = useWorkspace()
  const { knowledgeBases, loading, create, remove, refresh } = useKnowledgeBases()
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedKB, setSelectedKB] = useState<KnowledgeBaseDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showUrlModal, setShowUrlModal] = useState(false)
  const [showDocPicker, setShowDocPicker] = useState(false)
  const [addingDocs, setAddingDocs] = useState(false)

  const handleCreate = async () => {
    setCreating(true)
    setError(null)
    try {
      const kb = await create('New Knowledge Base')
      loadDetail(kb.uuid)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create')
    } finally {
      setCreating(false)
    }
  }

  const loadDetail = useCallback(async (uuid: string) => {
    setDetailLoading(true)
    try {
      const detail = await api.getKnowledgeBase(uuid)
      setSelectedKB(detail)
    } catch (err) {
      console.error('Failed to load KB:', err)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  // Poll status when building
  useEffect(() => {
    if (!selectedKB || selectedKB.status !== 'building') return
    const interval = setInterval(async () => {
      try {
        const detail = await api.getKnowledgeBase(selectedKB.uuid)
        setSelectedKB(detail)
        if (detail.status !== 'building') {
          refresh()
        }
      } catch { /* ignore */ }
    }, 3000)
    return () => clearInterval(interval)
  }, [selectedKB?.uuid, selectedKB?.status, refresh])

  const handleDelete = async (uuid: string) => {
    try {
      await remove(uuid)
      if (selectedKB?.uuid === uuid) setSelectedKB(null)
    } catch (err) {
      console.error('Failed to delete KB:', err)
    }
  }

  const handleAddDocuments = async (docUuids: string[]) => {
    if (!selectedKB || docUuids.length === 0) return
    setAddingDocs(true)
    setShowDocPicker(false)
    try {
      await api.addDocumentsToKB(selectedKB.uuid, docUuids)
      loadDetail(selectedKB.uuid)
      refresh()
    } catch (err) {
      console.error('Failed to add documents:', err)
    } finally {
      setAddingDocs(false)
    }
  }

  const handleAddUrls = async (urls: string[]) => {
    if (!selectedKB) return
    try {
      await api.addUrlsToKB(selectedKB.uuid, urls)
      loadDetail(selectedKB.uuid)
      refresh()
    } catch (err) {
      console.error('Failed to add URLs:', err)
    }
  }

  const handleRemoveSource = async (sourceUuid: string) => {
    if (!selectedKB) return
    try {
      await api.removeKBSource(selectedKB.uuid, sourceUuid)
      loadDetail(selectedKB.uuid)
      refresh()
    } catch (err) {
      console.error('Failed to remove source:', err)
    }
  }

  const handleChat = () => {
    if (!selectedKB) return
    activateKB(selectedKB.uuid, selectedKB.title)
  }

  // Detail view
  if (selectedKB) {
    const badge = STATUS_BADGE[selectedKB.status] || STATUS_BADGE.empty
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#1e1e1e' }}>
        {/* Header */}
        <div
          style={{
            height: 50,
            backgroundColor: '#191919',
            boxShadow: '0 0px 23px -8px rgb(211, 211, 211)',
            padding: '0 12px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexShrink: 0,
            zIndex: 300,
            position: 'relative',
          }}
        >
          <button
            onClick={() => { setSelectedKB(null); refresh() }}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
          >
            <ArrowLeft size={18} style={{ color: '#888' }} />
          </button>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#fff', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {selectedKB.title}
          </span>
          <span
            style={{
              fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
              color: badge.color, backgroundColor: badge.bg,
            }}
          >
            {badge.label}
          </span>
        </div>

        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#888' }}>
            <Loader2 style={{ width: 20, height: 20, margin: '0 auto', animation: 'spin 1s linear infinite' }} />
          </div>
        ) : (
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px' }}>
            {/* Description */}
            {selectedKB.description && (
              <div style={{ fontSize: 13, color: '#aaa', marginBottom: 12, lineHeight: 1.5 }}>
                {selectedKB.description}
              </div>
            )}

            {/* Stats */}
            <div style={{ display: 'flex', gap: 12, marginBottom: 16, fontSize: 12, color: '#999' }}>
              <span>{selectedKB.total_sources} sources</span>
              <span>{selectedKB.total_chunks} chunks</span>
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
              <button
                onClick={() => setShowDocPicker(true)}
                disabled={addingDocs}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: '#e5e5e5',
                  backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
                  cursor: addingDocs ? 'default' : 'pointer',
                  opacity: addingDocs ? 0.5 : 1,
                }}
              >
                <FileText size={13} />
                {addingDocs ? 'Adding...' : 'Add Documents'}
              </button>
              <button
                onClick={() => setShowUrlModal(true)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: '#e5e5e5', backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a',
                  borderRadius: 6, cursor: 'pointer',
                }}
              >
                <Globe size={13} />
                Add URLs
              </button>
              <button
                onClick={handleChat}
                disabled={selectedKB.status !== 'ready'}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: selectedKB.status === 'ready' ? '#000' : '#666',
                  backgroundColor: selectedKB.status === 'ready' ? 'var(--highlight-color, #eab308)' : '#2a2a2a',
                  border: selectedKB.status === 'ready' ? 'none' : '1px solid #3a3a3a',
                  borderRadius: 6,
                  cursor: selectedKB.status === 'ready' ? 'pointer' : 'default',
                  opacity: selectedKB.status === 'ready' ? 1 : 0.5,
                }}
              >
                <MessageSquare size={13} />
                Chat with this KB
              </button>
            </div>

            {/* Sources list */}
            <div style={{ fontSize: 13, fontWeight: 600, color: '#ccc', marginBottom: 8 }}>Sources</div>
            {selectedKB.sources.length === 0 ? (
              <div style={{ fontSize: 12, color: '#888', padding: '20px 0' }}>
                No sources added yet. Add documents or URLs above.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {selectedKB.sources.map((source: KnowledgeBaseSource) => {
                  const st = SOURCE_STATUS[source.status] || SOURCE_STATUS.pending
                  const StatusIcon = st.icon
                  return (
                    <div
                      key={source.uuid}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '8px 10px', backgroundColor: '#2a2a2a',
                        border: '1px solid #3a3a3a', borderRadius: 6,
                      }}
                    >
                      {source.source_type === 'document' ? (
                        <FileText size={14} style={{ color: '#888', flexShrink: 0 }} />
                      ) : (
                        <Globe size={14} style={{ color: '#888', flexShrink: 0 }} />
                      )}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, color: '#e5e5e5', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {source.source_type === 'url' ? (source.url_title || source.url) : source.document_uuid}
                        </div>
                        {source.error_message && (
                          <div style={{ fontSize: 11, color: '#ef4444', marginTop: 2 }}>{source.error_message}</div>
                        )}
                        {source.status === 'ready' && (
                          <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>{source.chunk_count} chunks</div>
                        )}
                      </div>
                      <StatusIcon
                        size={14}
                        style={{
                          color: st.color, flexShrink: 0,
                          ...(source.status === 'processing' || source.status === 'pending' ? { animation: 'spin 1s linear infinite' } : {}),
                        }}
                      />
                      <button
                        onClick={() => handleRemoveSource(source.uuid)}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, display: 'flex' }}
                      >
                        <X size={12} style={{ color: '#666' }} />
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {showUrlModal && (
          <AddUrlsModal
            onSubmit={(urls) => { handleAddUrls(urls); setShowUrlModal(false) }}
            onClose={() => setShowUrlModal(false)}
          />
        )}
        {showDocPicker && (
          <DocumentPickerModal
            onSubmit={handleAddDocuments}
            onClose={() => setShowDocPicker(false)}
            existingSourceUuids={selectedKB.sources
              .filter(s => s.source_type === 'document' && s.document_uuid)
              .map(s => s.document_uuid!)}
          />
        )}
      </div>
    )
  }

  // List view
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#1e1e1e' }}>
      {/* Header */}
      <div
        style={{
          height: 50,
          backgroundColor: '#191919',
          boxShadow: '0 0px 23px -8px rgb(211, 211, 211)',
          padding: '0 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
          zIndex: 300,
          position: 'relative',
        }}
      >
        <span style={{ fontSize: 18, fontWeight: 600, color: '#fff' }}>Knowledge Bases</span>
        <button
          onClick={handleCreate}
          disabled={creating}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 14px',
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'inherit',
            color: '#000',
            backgroundColor: 'var(--highlight-color, #eab308)',
            border: 'none',
            borderRadius: 6,
            cursor: creating ? 'default' : 'pointer',
            opacity: creating ? 0.6 : 1,
          }}
        >
          {creating ? <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} /> : <Plus style={{ width: 14, height: 14 }} />}
          New
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          margin: '8px 12px 0', padding: '8px 12px', fontSize: 12,
          color: '#b91c1c', backgroundColor: '#fef2f2', borderRadius: 6,
          border: '1px solid #fecaca',
        }}>
          {error}
        </div>
      )}

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#888' }}>
            <Loader2 style={{ width: 20, height: 20, margin: '0 auto', animation: 'spin 1s linear infinite' }} />
          </div>
        ) : knowledgeBases.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#888' }}>
            <BookOpen style={{ width: 32, height: 32, margin: '0 auto 12px', opacity: 0.4 }} />
            <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>No knowledge bases yet</div>
            <div style={{ fontSize: 12 }}>Click "+ New" to create your first knowledge base</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {knowledgeBases.map(kb => {
              const badge = STATUS_BADGE[kb.status] || STATUS_BADGE.empty
              return (
                <button
                  key={kb.uuid}
                  onClick={() => loadDetail(kb.uuid)}
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: '14px 16px',
                    backgroundColor: '#2a2a2a',
                    border: '1px solid #3a3a3a',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    transition: 'background-color 0.15s',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#333')}
                  onMouseLeave={e => (e.currentTarget.style.backgroundColor = '#2a2a2a')}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#e5e5e5', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {kb.title}
                    </span>
                    <span
                      style={{
                        fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
                        color: badge.color, backgroundColor: badge.bg,
                      }}
                    >
                      {badge.label}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: '#999' }}>
                    <span>{kb.total_sources} sources</span>
                    <span>{kb.total_chunks} chunks</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
                    {kb.status === 'ready' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); activateKB(kb.uuid, kb.title) }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 4,
                          padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                          color: '#000', backgroundColor: 'var(--highlight-color, #eab308)',
                          border: 'none', borderRadius: 4, cursor: 'pointer',
                        }}
                      >
                        <MessageSquare size={11} />
                        Chat
                      </button>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(kb.uuid) }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4,
                        padding: '4px 8px', fontSize: 11, fontFamily: 'inherit',
                        color: '#888', backgroundColor: 'transparent',
                        border: '1px solid #3a3a3a', borderRadius: 4, cursor: 'pointer',
                      }}
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
