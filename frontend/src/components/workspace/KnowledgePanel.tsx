import { useState, useEffect, useCallback } from 'react'
import { Plus, Loader2, ArrowLeft, Trash2, X, FileText, Globe, MessageSquare, AlertCircle, CheckCircle2, Users, ShieldCheck, Send, Tag, Pencil, Check } from 'lucide-react'
import { useKnowledgeBases } from '../../hooks/useKnowledgeBases'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useAuth } from '../../hooks/useAuth'
import * as api from '../../api/knowledge'
import { listGroups } from '../../api/library'
import type { KnowledgeBaseDetail, KnowledgeBaseSource } from '../../types/knowledge'
import type { Group } from '../../types/library'
import { AddUrlsModal } from '../knowledge/AddUrlsModal'
import { DocumentPickerModal } from '../knowledge/DocumentPickerModal'
import { KnowledgeTutorial } from './KnowledgeTutorial'

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
  const { user } = useAuth()
  const { knowledgeBases, loading, create, remove, refresh } = useKnowledgeBases()
  const [creating, setCreating] = useState(false)
  const [allGroups, setAllGroups] = useState<Group[]>([])
  const [showGroupsModal, setShowGroupsModal] = useState(false)
  const [savingGroups, setSavingGroups] = useState(false)
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>([])

  const isExaminerOrAdmin = !!(user?.is_examiner || user?.is_admin)

  // Load groups for badges/assignment
  useEffect(() => {
    if (isExaminerOrAdmin) {
      listGroups().then(data => setAllGroups(data.groups)).catch(() => {})
    }
  }, [isExaminerOrAdmin])
  const [error, setError] = useState<string | null>(null)
  const [selectedKB, setSelectedKB] = useState<KnowledgeBaseDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showUrlModal, setShowUrlModal] = useState(false)
  const [showDocPicker, setShowDocPicker] = useState(false)
  const [addingDocs, setAddingDocs] = useState(false)
  const [addingUrls, setAddingUrls] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')

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

  const handleAddUrls = (urls: string[], crawlEnabled = false, maxCrawlPages = 5, allowedDomains = '') => {
    if (!selectedKB) return
    setAddingUrls(true)
    // Optimistically set status to building so the poller starts
    setSelectedKB(prev => prev ? { ...prev, status: 'building' } : prev)
    api.addUrlsToKB(selectedKB.uuid, urls, crawlEnabled, maxCrawlPages, allowedDomains)
      .then(() => {
        loadDetail(selectedKB.uuid)
        refresh()
      })
      .catch(err => console.error('Failed to add URLs:', err))
      .finally(() => setAddingUrls(false))
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

  const handleToggleShare = async () => {
    if (!selectedKB) return
    try {
      await api.shareKnowledgeBase(selectedKB.uuid)
      loadDetail(selectedKB.uuid)
      refresh()
    } catch (err) {
      console.error('Failed to toggle sharing:', err)
    }
  }

  const handleOpenGroupsModal = () => {
    if (!selectedKB) return
    setSelectedGroupIds(selectedKB.group_ids || [])
    setShowGroupsModal(true)
  }

  const handleSaveGroups = async () => {
    if (!selectedKB) return
    setSavingGroups(true)
    try {
      await api.setKBGroups(selectedKB.uuid, selectedGroupIds)
      loadDetail(selectedKB.uuid)
      refresh()
      setShowGroupsModal(false)
    } catch (err) {
      console.error('Failed to update groups:', err)
    } finally {
      setSavingGroups(false)
    }
  }

  // Verification modal state
  const [showVerifyModal, setShowVerifyModal] = useState(false)
  const [verifySummary, setVerifySummary] = useState('')
  const [verifyDescription, setVerifyDescription] = useState('')
  const [verifyCategory, setVerifyCategory] = useState('')
  const [submittingVerify, setSubmittingVerify] = useState(false)

  const handleSubmitVerification = async () => {
    if (!selectedKB) return
    setSubmittingVerify(true)
    try {
      await api.submitKBForVerification(selectedKB.uuid, {
        summary: verifySummary || undefined,
        description: verifyDescription || undefined,
        category: verifyCategory || undefined,
      })
      setShowVerifyModal(false)
      setVerifySummary('')
      setVerifyDescription('')
      setVerifyCategory('')
      loadDetail(selectedKB.uuid)
    } catch (err) {
      console.error('Failed to submit for verification:', err)
    } finally {
      setSubmittingVerify(false)
    }
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
            onClick={() => { setSelectedKB(null); setEditingTitle(false); refresh() }}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
          >
            <ArrowLeft size={18} style={{ color: '#888' }} />
          </button>
          {editingTitle ? (
            <form
              style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}
              onSubmit={async (e) => {
                e.preventDefault()
                const t = titleDraft.trim()
                if (t && t !== selectedKB.title) {
                  await api.updateKnowledgeBase(selectedKB.uuid, { title: t })
                  setSelectedKB(prev => prev ? { ...prev, title: t } : prev)
                  refresh()
                }
                setEditingTitle(false)
              }}
            >
              <input
                autoFocus
                value={titleDraft}
                onChange={e => setTitleDraft(e.target.value)}
                onBlur={() => setEditingTitle(false)}
                onKeyDown={e => { if (e.key === 'Escape') setEditingTitle(false) }}
                style={{
                  flex: 1, fontSize: 16, fontWeight: 600, fontFamily: 'inherit',
                  color: '#fff', backgroundColor: '#2a2a2a',
                  border: '1px solid #555', borderRadius: 4,
                  padding: '2px 8px', outline: 'none', minWidth: 0,
                }}
              />
              <button
                type="submit"
                onMouseDown={e => e.preventDefault()}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
              >
                <Check size={16} style={{ color: '#15803d' }} />
              </button>
            </form>
          ) : (
            <span
              onClick={() => { setTitleDraft(selectedKB.title); setEditingTitle(true) }}
              title="Click to rename"
              style={{
                fontSize: 16, fontWeight: 600, color: '#fff', flex: 1,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                cursor: 'text', borderRadius: 4, padding: '2px 0',
              }}
            >
              {selectedKB.title}
            </span>
          )}
          {selectedKB.shared_with_team && (
            <span style={{
              fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
              color: 'rgb(0, 128, 128)', backgroundColor: 'rgba(0, 128, 128, 0.1)',
            }}>
              Team
            </span>
          )}
          {selectedKB.verified && (
            <span style={{
              fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
              color: '#15803d', backgroundColor: '#dcfce7',
              display: 'flex', alignItems: 'center', gap: 3,
            }}>
              <ShieldCheck size={10} />
              Verified
            </span>
          )}
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

            {/* Crawling / adding URLs progress banner */}
            {addingUrls && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 14px', marginBottom: 16, borderRadius: 8,
                backgroundColor: 'rgba(217, 119, 6, 0.1)',
                border: '1px solid rgba(217, 119, 6, 0.25)',
              }}>
                <Loader2 size={16} style={{ color: '#d97706', animation: 'spin 1s linear infinite', flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#e5e5e5' }}>
                    Adding URLs & crawling pages...
                  </div>
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                    Sources will appear below as they are processed.
                  </div>
                </div>
              </div>
            )}

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
                disabled={addingUrls}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: '#e5e5e5', backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a',
                  borderRadius: 6,
                  cursor: addingUrls ? 'default' : 'pointer',
                  opacity: addingUrls ? 0.5 : 1,
                }}
              >
                {addingUrls ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Globe size={13} />}
                {addingUrls ? 'Adding...' : 'Add URLs'}
              </button>
              <button
                onClick={handleChat}
                disabled={selectedKB.status !== 'ready'}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: selectedKB.status === 'ready' ? 'var(--highlight-text-color, #000)' : '#666',
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
              <button
                onClick={handleToggleShare}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: selectedKB.shared_with_team ? 'rgb(0, 128, 128)' : '#e5e5e5',
                  backgroundColor: selectedKB.shared_with_team ? 'rgba(0, 128, 128, 0.1)' : '#2a2a2a',
                  border: selectedKB.shared_with_team ? '1px solid rgba(0, 128, 128, 0.3)' : '1px solid #3a3a3a',
                  borderRadius: 6, cursor: 'pointer',
                }}
              >
                <Users size={13} />
                {selectedKB.shared_with_team ? 'Shared with Team' : 'Share with Team'}
              </button>
              {selectedKB.status === 'ready' && !selectedKB.verified && (
                <button
                  onClick={() => setShowVerifyModal(true)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                    color: '#e5e5e5', backgroundColor: '#2a2a2a',
                    border: '1px solid #3a3a3a', borderRadius: 6, cursor: 'pointer',
                  }}
                >
                  <Send size={13} />
                  Submit for Verification
                </button>
              )}
              {selectedKB.verified && isExaminerOrAdmin && (
                <button
                  onClick={handleOpenGroupsModal}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                    color: (selectedKB.group_ids?.length ?? 0) > 0 ? '#2563eb' : '#e5e5e5',
                    backgroundColor: (selectedKB.group_ids?.length ?? 0) > 0 ? 'rgba(37, 99, 235, 0.1)' : '#2a2a2a',
                    border: (selectedKB.group_ids?.length ?? 0) > 0 ? '1px solid rgba(37, 99, 235, 0.3)' : '1px solid #3a3a3a',
                    borderRadius: 6, cursor: 'pointer',
                  }}
                >
                  <Tag size={13} />
                  Manage Groups
                </button>
              )}
            </div>

            {/* Group badges */}
            {(selectedKB.group_ids?.length ?? 0) > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
                {selectedKB.group_ids.map(gid => {
                  const group = allGroups.find(g => g.uuid === gid)
                  return (
                    <span
                      key={gid}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 8,
                        color: '#2563eb', backgroundColor: 'rgba(37, 99, 235, 0.1)',
                        border: '1px solid rgba(37, 99, 235, 0.2)',
                      }}
                    >
                      <Tag size={10} />
                      {group?.name || gid}
                    </span>
                  )
                })}
              </div>
            )}

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
            onSubmit={(urls, crawlEnabled, maxCrawlPages, allowedDomains) => { handleAddUrls(urls, crawlEnabled, maxCrawlPages, allowedDomains); setShowUrlModal(false) }}
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
        {showVerifyModal && (
          <div style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          }}>
            <div style={{
              backgroundColor: '#1e1e1e', borderRadius: 12, padding: 24, width: 400,
              border: '1px solid #3a3a3a', maxHeight: '80vh', overflowY: 'auto',
            }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#fff', marginBottom: 16 }}>
                Submit for Verification
              </div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#aaa', marginBottom: 4 }}>Summary</label>
              <input
                value={verifySummary}
                onChange={e => setVerifySummary(e.target.value)}
                placeholder="Brief summary of this knowledge base"
                style={{
                  width: '100%', padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
                  backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
                  color: '#e5e5e5', outline: 'none', marginBottom: 12, boxSizing: 'border-box',
                }}
              />
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#aaa', marginBottom: 4 }}>Description</label>
              <textarea
                value={verifyDescription}
                onChange={e => setVerifyDescription(e.target.value)}
                placeholder="Detailed description, intended use, etc."
                rows={3}
                style={{
                  width: '100%', padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
                  backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
                  color: '#e5e5e5', outline: 'none', marginBottom: 12, resize: 'vertical',
                  boxSizing: 'border-box',
                }}
              />
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#aaa', marginBottom: 4 }}>Category</label>
              <input
                value={verifyCategory}
                onChange={e => setVerifyCategory(e.target.value)}
                placeholder="e.g. Legal, Medical, Research"
                style={{
                  width: '100%', padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
                  backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
                  color: '#e5e5e5', outline: 'none', marginBottom: 16, boxSizing: 'border-box',
                }}
              />
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button
                  onClick={() => setShowVerifyModal(false)}
                  style={{
                    padding: '6px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                    color: '#aaa', backgroundColor: 'transparent', border: '1px solid #3a3a3a',
                    borderRadius: 6, cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmitVerification}
                  disabled={submittingVerify}
                  style={{
                    padding: '6px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                    color: 'var(--highlight-text-color, #000)',
                    backgroundColor: 'var(--highlight-color, #eab308)',
                    border: 'none', borderRadius: 6,
                    cursor: submittingVerify ? 'default' : 'pointer',
                    opacity: submittingVerify ? 0.6 : 1,
                  }}
                >
                  {submittingVerify ? 'Submitting...' : 'Submit'}
                </button>
              </div>
            </div>
          </div>
        )}
        {showGroupsModal && (
          <div style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          }}>
            <div style={{
              backgroundColor: '#1e1e1e', borderRadius: 12, padding: 24, width: 400,
              border: '1px solid #3a3a3a', maxHeight: '80vh', overflowY: 'auto',
            }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#fff', marginBottom: 8 }}>
                Manage Groups
              </div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 16 }}>
                No groups selected = visible to everyone. Selected groups restrict visibility to group members only.
              </div>
              {allGroups.length === 0 ? (
                <div style={{ fontSize: 13, color: '#888', padding: '20px 0', textAlign: 'center' }}>
                  No groups available. Create groups in the Verification page.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
                  {allGroups.map(group => (
                    <label
                      key={group.uuid}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '8px 10px', borderRadius: 6,
                        backgroundColor: selectedGroupIds.includes(group.uuid) ? 'rgba(37, 99, 235, 0.1)' : '#2a2a2a',
                        border: selectedGroupIds.includes(group.uuid)
                          ? '1px solid rgba(37, 99, 235, 0.3)'
                          : '1px solid #3a3a3a',
                        cursor: 'pointer',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedGroupIds.includes(group.uuid)}
                        onChange={() => {
                          setSelectedGroupIds(prev =>
                            prev.includes(group.uuid)
                              ? prev.filter(id => id !== group.uuid)
                              : [...prev, group.uuid]
                          )
                        }}
                        style={{ accentColor: '#2563eb' }}
                      />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#e5e5e5' }}>{group.name}</div>
                        {group.description && (
                          <div style={{ fontSize: 11, color: '#888' }}>{group.description}</div>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button
                  onClick={() => setShowGroupsModal(false)}
                  style={{
                    padding: '6px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                    color: '#aaa', backgroundColor: 'transparent', border: '1px solid #3a3a3a',
                    borderRadius: 6, cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveGroups}
                  disabled={savingGroups}
                  style={{
                    padding: '6px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                    color: 'var(--highlight-text-color, #000)',
                    backgroundColor: 'var(--highlight-color, #eab308)',
                    border: 'none', borderRadius: 6,
                    cursor: savingGroups ? 'default' : 'pointer',
                    opacity: savingGroups ? 0.6 : 1,
                  }}
                >
                  {savingGroups ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          </div>
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
            color: 'var(--highlight-text-color, #000)',
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
          <KnowledgeTutorial />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {knowledgeBases.map(kb => {
              const badge = STATUS_BADGE[kb.status] || STATUS_BADGE.empty
              const isReady = kb.status === 'ready'
              return (
                <button
                  key={kb.uuid}
                  onClick={() => isReady ? activateKB(kb.uuid, kb.title) : loadDetail(kb.uuid)}
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
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#e5e5e5', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {kb.title}
                    </span>
                    {kb.shared_with_team && (
                      <span style={{
                        fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
                        color: 'rgb(0, 128, 128)', backgroundColor: 'rgba(0, 128, 128, 0.1)',
                        whiteSpace: 'nowrap',
                      }}>
                        Team
                      </span>
                    )}
                    {kb.verified && (
                      <span style={{
                        fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
                        color: '#15803d', backgroundColor: '#dcfce7',
                        display: 'flex', alignItems: 'center', gap: 3, whiteSpace: 'nowrap',
                      }}>
                        <ShieldCheck size={10} />
                        Verified
                      </span>
                    )}
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
                  {(kb.group_ids?.length ?? 0) > 0 && (
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                      {kb.group_ids.map(gid => {
                        const group = allGroups.find(g => g.uuid === gid)
                        return (
                          <span
                            key={gid}
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: 3,
                              fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
                              color: '#2563eb', backgroundColor: 'rgba(37, 99, 235, 0.1)',
                            }}
                          >
                            <Tag size={9} />
                            {group?.name || gid}
                          </span>
                        )
                      })}
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); loadDetail(kb.uuid) }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4,
                        padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                        color: '#ccc', backgroundColor: 'transparent',
                        border: '1px solid #3a3a3a', borderRadius: 4, cursor: 'pointer',
                      }}
                    >
                      <Pencil size={11} />
                      Edit
                    </button>
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
