import { useState, useEffect, useCallback, useRef } from 'react'
import { Plus, Loader2, ArrowLeft, X, FileText, Globe, MessageSquare, AlertCircle, CheckCircle2, Users, ShieldCheck, Send, Tag, Check, Download, Upload, Sparkles, HelpCircle, Pencil } from 'lucide-react'
import { useKnowledgeBases, useScopedKnowledgeBases } from '../../hooks/useKnowledgeBases'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useAuth } from '../../hooks/useAuth'
import * as api from '../../api/knowledge'
import { listOrganizationsFlat } from '../../api/organizations'
import { MAX_NAME_LENGTH, normalizeName } from '../../utils/nameValidation'
import type { Organization } from '../../api/organizations'
import type { KnowledgeBase, KnowledgeBaseDetail, KnowledgeBaseSource, KBScope } from '../../types/knowledge'
import { AddUrlsModal } from '../knowledge/AddUrlsModal'
import { DocumentPickerModal } from '../knowledge/DocumentPickerModal'
import { KBSearchBar } from '../knowledge/KBSearchBar'
import { KBGridView } from '../knowledge/KBGridView'
import { KBValidationPanel } from '../knowledge/KBValidationPanel'
import { KBSourceInspectorModal } from '../knowledge/KBSourceInspectorModal'
import { KBExploreTab } from '../knowledge/KBExploreTab'
import { CreateKBModal } from '../knowledge/CreateKBModal'
import { KBTrustBanner } from '../knowledge/KBTrustBanner'
import { KnowledgeExplainer } from './KnowledgeExplainer'
import { ShareWithTeamDialog } from '../library/ShareWithTeamDialog'
import { useToast } from '../../contexts/ToastContext'
import { useConfirm } from '../shared/useConfirm'
import { SharedKBDeleteDialog, type SharedKBDeleteChoice } from '../shared/SharedKBDeleteDialog'

type TabKey = 'mine' | 'team' | 'explore'
const TABS: { key: TabKey; label: string }[] = [
  { key: 'mine', label: 'My KBs' },
  { key: 'team', label: 'Team' },
  { key: 'explore', label: 'Explore' },
]

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
  const { toast } = useToast()
  const { create, remove, transferToTeam, refresh } = useKnowledgeBases()
  const [sharedDeleteTarget, setSharedDeleteTarget] = useState<KnowledgeBase | null>(null)
  const confirm = useConfirm()
  const [activeTab, setActiveTab] = useState<TabKey>('mine')
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [allOrgs, setAllOrgs] = useState<Organization[]>([])
  const [showOrgsModal, setShowOrgsModal] = useState(false)
  const [savingOrgs, setSavingOrgs] = useState(false)
  const [selectedOrgIds, setSelectedOrgIds] = useState<string[]>([])

  // Used for adopt/removeRef in the scoped views
  const scopedMine = useScopedKnowledgeBases({ scope: 'mine' })

  const isExaminerOrAdmin = !!(user?.is_examiner || user?.is_admin)

  // Load orgs for badges/assignment
  useEffect(() => {
    if (isExaminerOrAdmin) {
      listOrganizationsFlat().then(data => setAllOrgs(data.organizations)).catch(() => {})
    }
  }, [isExaminerOrAdmin])
  const [error, setError] = useState<string | null>(null)
  const [selectedKB, setSelectedKB] = useState<KnowledgeBaseDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showUrlModal, setShowUrlModal] = useState(false)
  const [showDocPicker, setShowDocPicker] = useState(false)
  const [showExplainer, setShowExplainer] = useState(false)
  const [addingDocs, setAddingDocs] = useState(false)
  const [addingUrls, setAddingUrls] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [editingDescription, setEditingDescription] = useState(false)
  const [descriptionDraft, setDescriptionDraft] = useState('')
  const [savingDescription, setSavingDescription] = useState(false)
  const [inspectingSource, setInspectingSource] = useState<KnowledgeBaseSource | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const titleInputRef = useRef<HTMLInputElement | null>(null)
  const cancelTitleEdit = useRef(false)
  // Single commit path for the inline KB title editor: every exit from edit
  // mode (Enter, the check button, or tabbing/clicking away) routes through the
  // input's onBlur to here, so the edit is saved instead of silently discarded.
  // Escape sets cancelTitleEdit to bail out without saving.
  const commitTitle = async () => {
    setEditingTitle(false)
    if (cancelTitleEdit.current) {
      cancelTitleEdit.current = false
      return
    }
    const t = normalizeName(titleDraft)
    if (selectedKB && t && t !== selectedKB.title) {
      try {
        await api.updateKnowledgeBase(selectedKB.uuid, { title: t })
        setSelectedKB(prev => prev ? { ...prev, title: t } : prev)
        toast('Title updated', 'success')
        refresh()
      } catch (err) {
        console.error('Failed to rename KB:', err)
        toast(err instanceof Error ? err.message : 'Failed to rename', 'error')
      }
    }
  }

  const handleCreate = async (title: string, description: string) => {
    setCreating(true)
    setError(null)
    try {
      const kb = await create(title, description || undefined)
      setShowCreateModal(false)
      loadDetail(kb.uuid)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create')
      throw err
    } finally {
      setCreating(false)
    }
  }

  const loadDetail = useCallback(async (uuid: string) => {
    setDetailLoading(true)
    setVerificationSubmitted(false)
    try {
      const detail = await api.getKnowledgeBase(uuid)
      setSelectedKB(detail)
    } catch (err) {
      console.error('Failed to load KB:', err)
      toast(err instanceof Error ? err.message : 'Failed to open knowledge base', 'error')
    } finally {
      setDetailLoading(false)
    }
  }, [toast])

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
    const kb = scopedMine.knowledgeBases.find((k: KnowledgeBase) => k.uuid === uuid)
    if (kb?.shared_with_team) {
      setSharedDeleteTarget(kb)
      return
    }
    const ok = await confirm({
      title: 'Delete knowledge base?',
      message: (
        <>
          Are you sure you want to delete <strong>{kb?.title || 'this knowledge base'}</strong>? Indexed content will be removed and chats referencing it may lose context. This cannot be undone.
        </>
      ),
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    try {
      await remove(uuid)
      if (selectedKB?.uuid === uuid) setSelectedKB(null)
      toast('Knowledge base deleted', 'success')
    } catch (err) {
      console.error('Failed to delete KB:', err)
      toast(err instanceof Error ? err.message : 'Failed to delete knowledge base', 'error')
    }
  }

  const handleSharedDeleteChoice = async (choice: SharedKBDeleteChoice) => {
    const kb = sharedDeleteTarget
    if (!kb) return
    try {
      if (choice === 'transfer') {
        await transferToTeam(kb.uuid)
        if (selectedKB?.uuid === kb.uuid) setSelectedKB(null)
        toast('Moved to Team Library', 'success')
      } else {
        await remove(kb.uuid, 'unshare_and_delete')
        if (selectedKB?.uuid === kb.uuid) setSelectedKB(null)
        toast('Knowledge base deleted', 'success')
      }
      setSharedDeleteTarget(null)
    } catch (err) {
      console.error('Failed to delete/transfer KB:', err)
      toast(err instanceof Error ? err.message : 'Operation failed', 'error')
    }
  }

  const handleAddDocuments = async (docUuids: string[]) => {
    if (!selectedKB || docUuids.length === 0) return
    setAddingDocs(true)
    setShowDocPicker(false)
    try {
      const result = await api.addDocumentsToKB(selectedKB.uuid, docUuids)
      const n = result?.added ?? docUuids.length
      toast(`Added ${n} document${n === 1 ? '' : 's'}`, 'success')
      loadDetail(selectedKB.uuid)
      refresh()
    } catch (err) {
      console.error('Failed to add documents:', err)
      toast(err instanceof Error ? err.message : 'Failed to add documents', 'error')
    } finally {
      setAddingDocs(false)
    }
  }

  const handleAddFolder = async (folderUuid: string, includeSubfolders: boolean) => {
    if (!selectedKB) return
    setAddingDocs(true)
    setShowDocPicker(false)
    try {
      const result = await api.addFolderToKB(selectedKB.uuid, folderUuid, includeSubfolders)
      const n = result?.added ?? 0
      if (n === 0) {
        toast('No new documents found in that folder', 'info')
      } else {
        toast(`Added ${n} document${n === 1 ? '' : 's'} from folder`, 'success')
      }
      loadDetail(selectedKB.uuid)
      refresh()
    } catch (err) {
      console.error('Failed to add folder:', err)
      toast(err instanceof Error ? err.message : 'Failed to add folder', 'error')
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
      .then((result) => {
        const n = result?.added ?? urls.length
        toast(`Added ${n} URL${n === 1 ? '' : 's'} — crawling in background`, 'success')
        loadDetail(selectedKB.uuid)
        refresh()
      })
      .catch(err => {
        console.error('Failed to add URLs:', err)
        toast(err instanceof Error ? err.message : 'Failed to add URLs', 'error')
      })
      .finally(() => setAddingUrls(false))
  }

  const handleRemoveSource = async (sourceUuid: string) => {
    if (!selectedKB) return
    try {
      await api.removeKBSource(selectedKB.uuid, sourceUuid)
      toast('Source removed', 'success')
      loadDetail(selectedKB.uuid)
      refresh()
    } catch (err) {
      console.error('Failed to remove source:', err)
      toast(err instanceof Error ? err.message : 'Failed to remove source', 'error')
    }
  }

  const [renamingSourceUuid, setRenamingSourceUuid] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [savingRename, setSavingRename] = useState(false)

  const beginRenameSource = (source: KnowledgeBaseSource) => {
    const current =
      source.custom_name
      || (source.source_type === 'url' ? (source.url_title || source.url || '') : (source.document_title || ''))
    setRenamingSourceUuid(source.uuid)
    setRenameDraft(current || '')
  }

  const cancelRenameSource = () => {
    setRenamingSourceUuid(null)
    setRenameDraft('')
    setSavingRename(false)
  }

  const handleRenameSource = async () => {
    if (!selectedKB || !renamingSourceUuid) return
    const sourceUuid = renamingSourceUuid
    const current = selectedKB.sources.find(s => s.uuid === sourceUuid)
    const previous = current?.custom_name || ''
    const next = renameDraft.trim()
    if (next === previous) {
      cancelRenameSource()
      return
    }
    setSavingRename(true)
    // Optimistic update so the row reflects the new name immediately
    setSelectedKB(prev => prev ? {
      ...prev,
      sources: prev.sources.map(s => s.uuid === sourceUuid ? { ...s, custom_name: next || null } : s),
    } : prev)
    try {
      const updated = await api.renameKBSource(selectedKB.uuid, sourceUuid, next)
      setSelectedKB(prev => prev ? {
        ...prev,
        sources: prev.sources.map(s => s.uuid === sourceUuid ? {
          ...s,
          custom_name: updated.custom_name ?? null,
        } : s),
      } : prev)
      toast(next ? 'Source renamed' : 'Custom name cleared', 'success')
    } catch (err) {
      console.error('Failed to rename source:', err)
      toast(err instanceof Error ? err.message : 'Failed to rename source', 'error')
      // Revert on failure
      setSelectedKB(prev => prev ? {
        ...prev,
        sources: prev.sources.map(s => s.uuid === sourceUuid ? { ...s, custom_name: previous || null } : s),
      } : prev)
    } finally {
      cancelRenameSource()
    }
  }

  const handleChat = () => {
    if (!selectedKB) return
    activateKB(selectedKB.uuid, selectedKB.title)
  }

  const [shareDialogKB, setShareDialogKB] = useState<KnowledgeBase | null>(null)

  const handleToggleShare = async (kb: KnowledgeBase) => {
    // Sharing for the first time → prompt for a note.
    if (!kb.shared_with_team) {
      setShareDialogKB(kb)
      return
    }
    try {
      const result = await api.shareKnowledgeBase(kb.uuid)
      toast(result.shared_with_team ? 'Shared with team' : 'Unshared from team', 'success')
      if (selectedKB?.uuid === kb.uuid) loadDetail(kb.uuid)
      refresh()
    } catch (err) {
      console.error('Failed to toggle sharing:', err)
      toast(err instanceof Error ? err.message : 'Failed to update team sharing', 'error')
    }
  }

  const confirmShareKB = async (comment: string) => {
    if (!shareDialogKB) return
    const kbUuid = shareDialogKB.uuid
    try {
      await api.shareKnowledgeBase(kbUuid, comment || undefined)
      toast('Shared with team', 'success')
      if (selectedKB?.uuid === kbUuid) loadDetail(kbUuid)
      refresh()
    } catch (err) {
      console.error('Failed to share KB:', err)
      toast('Failed to share knowledge base', 'error')
    } finally {
      setShareDialogKB(null)
    }
  }

  const handleOpenOrgsModal = () => {
    if (!selectedKB) return
    setSelectedOrgIds(selectedKB.organization_ids || [])
    setShowOrgsModal(true)
  }

  const handleSaveOrgs = async () => {
    if (!selectedKB) return
    setSavingOrgs(true)
    try {
      await api.setKBOrganizations(selectedKB.uuid, selectedOrgIds)
      toast('Org visibility updated', 'success')
      loadDetail(selectedKB.uuid)
      refresh()
      setShowOrgsModal(false)
    } catch (err) {
      console.error('Failed to update org visibility:', err)
      toast(err instanceof Error ? err.message : 'Failed to update org visibility', 'error')
    } finally {
      setSavingOrgs(false)
    }
  }

  // Export / Import state
  const [exporting, setExporting] = useState(false)
  const [importing, setImporting] = useState(false)
  const importInputRef = useRef<HTMLInputElement | null>(null)

  const handleExport = async () => {
    if (!selectedKB) return
    setExporting(true)
    try {
      await api.downloadKBExport(selectedKB.uuid, selectedKB.title)
    } catch (err) {
      console.error('Failed to export KB:', err)
      toast(err instanceof Error ? err.message : 'Failed to export knowledge base', 'error')
    } finally {
      setExporting(false)
    }
  }

  const handleImportFile = async (file: File) => {
    setImporting(true)
    try {
      const text = await file.text()
      let payload: api.KBExportPayload
      try {
        payload = JSON.parse(text) as api.KBExportPayload
      } catch {
        throw new Error('Invalid JSON file')
      }
      if (!payload || typeof payload !== 'object' || !Array.isArray(payload.sources)) {
        throw new Error('File is not a valid knowledge base export')
      }
      const result = await api.importKnowledgeBase(payload)
      toast(`Imported "${result.title}" with ${result.imported_sources} source${result.imported_sources === 1 ? '' : 's'}`, 'success')
      refresh()
      loadDetail(result.uuid)
    } catch (err) {
      console.error('Failed to import KB:', err)
      toast(err instanceof Error ? err.message : 'Failed to import knowledge base', 'error')
    } finally {
      setImporting(false)
      if (importInputRef.current) importInputRef.current.value = ''
    }
  }

  // Verification modal state
  const [verifyKB, setVerifyKB] = useState<KnowledgeBase | null>(null)
  const [verifySummary, setVerifySummary] = useState('')
  const [verifyDescription, setVerifyDescription] = useState('')
  const [verifyCategory, setVerifyCategory] = useState('')
  const [submittingVerify, setSubmittingVerify] = useState(false)
  const [verificationSubmitted, setVerificationSubmitted] = useState(false)

  const openVerifyModal = (kb: KnowledgeBase) => {
    setVerifySummary('')
    setVerifyDescription('')
    setVerifyCategory('')
    setVerifyKB(kb)
  }

  const handleSubmitVerification = async () => {
    if (!verifyKB) return
    const kbUuid = verifyKB.uuid
    setSubmittingVerify(true)
    try {
      await api.submitKBForVerification(kbUuid, {
        summary: verifySummary || undefined,
        description: verifyDescription || undefined,
        category: verifyCategory || undefined,
      })
      setVerifyKB(null)
      setVerifySummary('')
      setVerifyDescription('')
      setVerifyCategory('')
      setVerificationSubmitted(true)
      toast('Submitted for verification', 'success')
      if (selectedKB?.uuid === kbUuid) loadDetail(kbUuid)
      refresh()
    } catch (err) {
      console.error('Failed to submit for verification:', err)
      toast(err instanceof Error ? err.message : 'Failed to submit for verification', 'error')
    } finally {
      setSubmittingVerify(false)
    }
  }

  const shareDialogJSX = shareDialogKB ? (
    <ShareWithTeamDialog
      itemName={shareDialogKB.title}
      onCancel={() => setShareDialogKB(null)}
      onConfirm={confirmShareKB}
    />
  ) : null

  const verifyModalJSX = verifyKB ? (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        backgroundColor: '#1e1e1e', borderRadius: 12, padding: 24, width: 400,
        border: '1px solid #3a3a3a', maxHeight: '80vh', overflowY: 'auto',
      }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: '#fff', marginBottom: 4 }}>
          Submit for Verification
        </div>
        <div style={{ fontSize: 12, color: '#888', marginBottom: 16 }}>
          {verifyKB.title}
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
            onClick={() => setVerifyKB(null)}
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
  ) : null

  // Detail view
  if (selectedKB) {
    const badge = STATUS_BADGE[selectedKB.status] || STATUS_BADGE.empty
    return (
      <>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#1e1e1e', position: 'relative' }}>
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
            <div
              style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}
            >
              <input
                ref={titleInputRef}
                autoFocus
                value={titleDraft}
                maxLength={MAX_NAME_LENGTH}
                onChange={e => setTitleDraft(e.target.value)}
                onBlur={commitTitle}
                onKeyDown={e => {
                  if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() }
                  else if (e.key === 'Escape') { cancelTitleEdit.current = true; e.currentTarget.blur() }
                }}
                style={{
                  flex: 1, fontSize: 16, fontWeight: 600, fontFamily: 'inherit',
                  color: '#fff', backgroundColor: '#2a2a2a',
                  border: '1px solid #555', borderRadius: 4,
                  padding: '2px 8px', outline: 'none', minWidth: 0,
                }}
              />
              <button
                type="button"
                // Keep focus on the input through mousedown, then blur on click so
                // the commit runs exactly once via onBlur (no double-save).
                onMouseDown={e => e.preventDefault()}
                onClick={() => titleInputRef.current?.blur()}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
              >
                <Check size={16} style={{ color: '#15803d' }} />
              </button>
            </div>
          ) : (
            <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span
                onClick={() => { setTitleDraft(selectedKB.title); setEditingTitle(true) }}
                title="Click to rename"
                style={{
                  fontSize: 16, fontWeight: 600, color: '#fff',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  cursor: 'text', borderRadius: 4, padding: '2px 0',
                  minWidth: 0,
                }}
              >
                {selectedKB.title}
              </span>
              <button
                onClick={() => { setTitleDraft(selectedKB.title); setEditingTitle(true) }}
                title="Edit title"
                style={{
                  background: 'transparent', border: 'none', cursor: 'pointer',
                  padding: 2, display: 'flex', color: '#888', flexShrink: 0,
                }}
              >
                <Pencil size={13} />
              </button>
            </div>
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
          {selectedKB.has_optimized_config && (
            <span
              title={
                selectedKB.optimized_config_set_at
                  ? `Optimized settings applied ${new Date(selectedKB.optimized_config_set_at).toLocaleString()}`
                  : 'Optimized settings applied'
              }
              style={{
                fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
                color: '#a78bfa', backgroundColor: 'rgba(124, 58, 237, 0.12)',
                border: '1px solid rgba(124, 58, 237, 0.3)',
                display: 'flex', alignItems: 'center', gap: 3,
              }}
            >
              <Sparkles size={10} />
              Optimized
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
            <div style={{ marginBottom: 12 }}>
              {editingDescription ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <textarea
                    autoFocus
                    value={descriptionDraft}
                    onChange={e => setDescriptionDraft(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Escape') {
                        e.preventDefault()
                        setEditingDescription(false)
                      } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault()
                        ;(e.currentTarget.form as HTMLFormElement | null)?.requestSubmit()
                      }
                    }}
                    placeholder="Describe what this knowledge base contains, who it's for, and how to use it."
                    rows={4}
                    maxLength={5000}
                    disabled={savingDescription}
                    style={{
                      width: '100%', fontSize: 13, fontFamily: 'inherit', lineHeight: 1.5,
                      color: '#e5e5e5', backgroundColor: '#1a1a1a',
                      border: '1px solid #555', borderRadius: 6,
                      padding: '8px 10px', outline: 'none',
                      resize: 'vertical', minHeight: 80,
                    }}
                  />
                  <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                    <button
                      onClick={() => setEditingDescription(false)}
                      disabled={savingDescription}
                      style={{
                        padding: '4px 10px', fontSize: 12, fontFamily: 'inherit',
                        color: '#ccc', background: 'transparent',
                        border: '1px solid #3a3a3a', borderRadius: 5, cursor: 'pointer',
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={async () => {
                        const next = descriptionDraft.trim()
                        const current = selectedKB.description || ''
                        if (next === current) { setEditingDescription(false); return }
                        setSavingDescription(true)
                        try {
                          await api.updateKnowledgeBase(selectedKB.uuid, { description: next })
                          setSelectedKB(prev => prev ? { ...prev, description: next } : prev)
                          refresh()
                          setEditingDescription(false)
                        } catch (err) {
                          console.error('Failed to update description:', err)
                          toast('Failed to update description', 'error')
                        } finally {
                          setSavingDescription(false)
                        }
                      }}
                      disabled={savingDescription}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        padding: '4px 10px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                        color: 'var(--highlight-text-color, #000)',
                        background: 'var(--highlight-color, #eab308)',
                        border: 'none', borderRadius: 5,
                        cursor: savingDescription ? 'default' : 'pointer',
                        opacity: savingDescription ? 0.7 : 1,
                      }}
                    >
                      {savingDescription ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Check size={11} />}
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                  <div style={{
                    flex: 1, fontSize: 13, lineHeight: 1.5,
                    color: selectedKB.description ? '#aaa' : '#666',
                    fontStyle: selectedKB.description ? 'normal' : 'italic',
                    whiteSpace: 'pre-wrap',
                  }}>
                    {selectedKB.description || 'No description yet — add one to help others understand what this KB is for.'}
                  </div>
                  <button
                    onClick={() => {
                      setDescriptionDraft(selectedKB.description || '')
                      setEditingDescription(true)
                    }}
                    title="Edit description"
                    style={{
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      padding: 2, display: 'flex', color: '#888', flexShrink: 0,
                      marginTop: 2,
                    }}
                  >
                    <Pencil size={13} />
                  </button>
                </div>
              )}
            </div>

            {/* AI Trust banner — headline answer to "is this KB worth using?" */}
            <KBTrustBanner
              score={selectedKB.last_validation_score}
              baseline={selectedKB.last_validation_baseline_score}
              lift={selectedKB.last_validation_lift}
              validatedAt={selectedKB.last_validated_at}
            />

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
                onClick={() => handleToggleShare(selectedKB)}
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
              <button
                onClick={handleExport}
                disabled={exporting}
                title="Download this knowledge base as a JSON file"
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: '#e5e5e5', backgroundColor: '#2a2a2a',
                  border: '1px solid #3a3a3a', borderRadius: 6,
                  cursor: exporting ? 'default' : 'pointer',
                  opacity: exporting ? 0.5 : 1,
                }}
              >
                {exporting ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Download size={13} />}
                {exporting ? 'Exporting...' : 'Export'}
              </button>
              {selectedKB.status === 'ready' && !selectedKB.verified && (
                verificationSubmitted ? (
                  <span style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 12px', fontSize: 12, fontWeight: 600,
                    color: '#059669',
                  }}>
                    <ShieldCheck size={13} />
                    Submitted for Verification
                  </span>
                ) : (
                  <button
                    onClick={() => openVerifyModal(selectedKB)}
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
                )
              )}
              {selectedKB.verified && isExaminerOrAdmin && (
                <button
                  onClick={handleOpenOrgsModal}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                    color: (selectedKB.organization_ids?.length ?? 0) > 0 ? '#2563eb' : '#e5e5e5',
                    backgroundColor: (selectedKB.organization_ids?.length ?? 0) > 0 ? 'rgba(37, 99, 235, 0.1)' : '#2a2a2a',
                    border: (selectedKB.organization_ids?.length ?? 0) > 0 ? '1px solid rgba(37, 99, 235, 0.3)' : '1px solid #3a3a3a',
                    borderRadius: 6, cursor: 'pointer',
                  }}
                >
                  <Tag size={13} />
                  Org Visibility
                </button>
              )}
            </div>

            {/* Org visibility badges */}
            {(selectedKB.organization_ids?.length ?? 0) > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
                {selectedKB.organization_ids.map(gid => {
                  const o = allOrgs.find(x => x.uuid === gid)
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
                      {o?.name || gid}
                    </span>
                  )
                })}
              </div>
            )}

            {/* Tags editor */}
            <KBTagsEditor
              tags={selectedKB.tags || []}
              canManage={!!user && (selectedKB.user_id === user.user_id || isExaminerOrAdmin)}
              onSave={async (next) => {
                await api.updateKnowledgeBase(selectedKB.uuid, { tags: next })
                setSelectedKB(prev => prev ? { ...prev, tags: next } : prev)
                refresh()
              }}
            />

            {/* Sources list */}
            <div style={{ fontSize: 13, fontWeight: 600, color: '#ccc', marginBottom: 8 }}>Sources</div>
            {selectedKB.sources.length === 0 ? (
              <div style={{ fontSize: 12, color: '#888', padding: '20px 0' }}>
                No sources added yet. Add documents or URLs above.
              </div>
            ) : (
              <div style={{
                display: 'flex', flexDirection: 'column', gap: 6,
                maxHeight: 320, overflowY: 'auto',
                paddingRight: 4,
              }}>
                {selectedKB.sources.map((source: KnowledgeBaseSource) => {
                  const st = SOURCE_STATUS[source.status] || SOURCE_STATUS.pending
                  const StatusIcon = st.icon
                  const autoLabel = source.source_type === 'url'
                    ? (source.url_title || source.url || source.uuid)
                    : (source.document_title || source.document_uuid || source.uuid)
                  const displayLabel = source.custom_name || autoLabel
                  // Verifiable provenance: an explicit source_reference, else the
                  // origin URL for url sources. Linkify http(s)/www, else show text.
                  const effectiveSource = source.source_reference || (source.source_type === 'url' ? (source.url || '') : '')
                  const sourceHref = effectiveSource
                    ? (/^https?:\/\//i.test(effectiveSource)
                        ? effectiveSource
                        : (/^www\./i.test(effectiveSource) ? `https://${effectiveSource}` : null))
                    : null
                  const isRenaming = renamingSourceUuid === source.uuid
                  const canInspect = source.status !== 'pending' && !isRenaming
                  return (
                    <div
                      key={source.uuid}
                      onClick={() => { if (canInspect) setInspectingSource(source) }}
                      title={canInspect ? 'Click to inspect this source' : undefined}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '8px 10px', backgroundColor: '#2a2a2a',
                        border: '1px solid #3a3a3a', borderRadius: 6,
                        cursor: canInspect ? 'pointer' : 'default',
                        transition: 'background-color 0.12s, border-color 0.12s',
                      }}
                      onMouseEnter={e => {
                        if (!canInspect) return
                        e.currentTarget.style.backgroundColor = '#323232'
                        e.currentTarget.style.borderColor = '#4a4a4a'
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.backgroundColor = '#2a2a2a'
                        e.currentTarget.style.borderColor = '#3a3a3a'
                      }}
                    >
                      {source.source_type === 'document' ? (
                        <FileText size={14} style={{ color: '#888', flexShrink: 0 }} />
                      ) : (
                        <Globe size={14} style={{ color: '#888', flexShrink: 0 }} />
                      )}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        {isRenaming ? (
                          <input
                            autoFocus
                            value={renameDraft}
                            onChange={e => setRenameDraft(e.target.value)}
                            onClick={e => e.stopPropagation()}
                            onKeyDown={e => {
                              if (e.key === 'Enter') { e.preventDefault(); handleRenameSource() }
                              else if (e.key === 'Escape') { e.preventDefault(); cancelRenameSource() }
                            }}
                            placeholder={autoLabel || 'Custom name'}
                            maxLength={300}
                            disabled={savingRename}
                            style={{
                              width: '100%', fontSize: 12, color: '#e5e5e5',
                              backgroundColor: '#1f1f1f', border: '1px solid #4a4a4a',
                              borderRadius: 4, padding: '4px 6px', fontFamily: 'inherit',
                              outline: 'none',
                            }}
                          />
                        ) : (
                          <div
                            style={{ fontSize: 12, color: '#e5e5e5', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                            title={source.custom_name
                              ? `${displayLabel} — original: ${autoLabel || (source.source_type === 'url' ? source.url : source.document_uuid) || ''}`
                              : (source.source_type === 'url' ? (source.url || '') : (source.document_uuid || ''))}
                          >
                            {displayLabel}
                            {source.custom_name && autoLabel && autoLabel !== source.custom_name && (
                              <span style={{ color: '#888', marginLeft: 6, fontStyle: 'italic' }}>
                                · {autoLabel}
                              </span>
                            )}
                          </div>
                        )}
                        {!isRenaming && effectiveSource && (
                          <div
                            style={{ fontSize: 11, color: '#9a9a9a', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                            title={`Source: ${effectiveSource}`}
                          >
                            Source:{' '}
                            {sourceHref ? (
                              <a
                                href={sourceHref}
                                target="_blank"
                                rel="noreferrer"
                                onClick={e => e.stopPropagation()}
                                style={{ color: '#7aa2f7', textDecoration: 'none' }}
                              >
                                {effectiveSource}
                              </a>
                            ) : (
                              <span style={{ color: '#bcbcbc' }}>{effectiveSource}</span>
                            )}
                          </div>
                        )}
                        {!isRenaming && source.error_message && (
                          <div style={{ fontSize: 11, color: '#ef4444', marginTop: 2 }}>{source.error_message}</div>
                        )}
                        {!isRenaming && source.status === 'ready' && (
                          <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>{source.chunk_count} chunks</div>
                        )}
                      </div>
                      {isRenaming ? (
                        <>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleRenameSource() }}
                            disabled={savingRename}
                            title="Save name"
                            style={{ background: 'transparent', border: 'none', cursor: savingRename ? 'default' : 'pointer', padding: 2, display: 'flex' }}
                          >
                            <Check size={14} style={{ color: '#22c55e' }} />
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); cancelRenameSource() }}
                            disabled={savingRename}
                            title="Cancel"
                            style={{ background: 'transparent', border: 'none', cursor: savingRename ? 'default' : 'pointer', padding: 2, display: 'flex' }}
                          >
                            <X size={14} style={{ color: '#888' }} />
                          </button>
                        </>
                      ) : (
                        <>
                          <StatusIcon
                            size={14}
                            style={{
                              color: st.color, flexShrink: 0,
                              ...(source.status === 'processing' || source.status === 'pending' ? { animation: 'spin 1s linear infinite' } : {}),
                            }}
                          />
                          <button
                            onClick={(e) => { e.stopPropagation(); beginRenameSource(source) }}
                            title={source.custom_name ? 'Rename (or clear to revert to original)' : 'Rename source'}
                            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, display: 'flex' }}
                          >
                            <Pencil size={12} style={{ color: '#888' }} />
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleRemoveSource(source.uuid) }}
                            title="Remove source"
                            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, display: 'flex' }}
                          >
                            <X size={12} style={{ color: '#666' }} />
                          </button>
                        </>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {/* Validation panel — gates on ready KB and management permission */}
            <KBValidationPanel
              kbUuid={selectedKB.uuid}
              kbReady={selectedKB.status === 'ready'}
              canManage={!!user && (selectedKB.user_id === user.user_id || isExaminerOrAdmin)}
            />

            {/* "What are knowledge bases?" pill */}
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24, marginBottom: 4 }}>
              <button
                onClick={() => setShowExplainer(true)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '6px 14px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
                  color: '#9ca3af',
                  backgroundColor: '#262626',
                  border: '1px solid #3a3a3a',
                  borderRadius: 999, cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.backgroundColor = '#2f2f2f'
                  e.currentTarget.style.color = '#e5e7eb'
                  e.currentTarget.style.borderColor = '#4a4a4a'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.backgroundColor = '#262626'
                  e.currentTarget.style.color = '#9ca3af'
                  e.currentTarget.style.borderColor = '#3a3a3a'
                }}
              >
                <HelpCircle size={13} />
                What are knowledge bases?
              </button>
            </div>
          </div>
        )}

        {showExplainer && <KnowledgeExplainer onClose={() => setShowExplainer(false)} />}

        {inspectingSource && selectedKB && (
          <KBSourceInspectorModal
            kbUuid={selectedKB.uuid}
            source={inspectingSource}
            onClose={() => setInspectingSource(null)}
            onUpdated={() => { if (selectedKB) loadDetail(selectedKB.uuid) }}
          />
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
            onSubmitFolder={handleAddFolder}
            onClose={() => setShowDocPicker(false)}
            existingSourceUuids={selectedKB.sources
              .filter(s => s.source_type === 'document' && s.document_uuid)
              .map(s => s.document_uuid!)}
          />
        )}
        {showOrgsModal && (
          <div style={{
            position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          }}>
            <div style={{
              backgroundColor: '#1e1e1e', borderRadius: 12, padding: 24, width: 400,
              border: '1px solid #3a3a3a', maxHeight: '80vh', overflowY: 'auto',
            }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#fff', marginBottom: 8 }}>
                Organization Visibility
              </div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 16 }}>
                No orgs selected = visible to everyone. Selected orgs restrict visibility to users in those orgs and below.
              </div>
              {allOrgs.length === 0 ? (
                <div style={{ fontSize: 13, color: '#888', padding: '20px 0', textAlign: 'center' }}>
                  No organizations available. Set up the org hierarchy in the admin page.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
                  {allOrgs.map(org => (
                    <label
                      key={org.uuid}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '8px 10px', borderRadius: 6,
                        backgroundColor: selectedOrgIds.includes(org.uuid) ? 'rgba(37, 99, 235, 0.1)' : '#2a2a2a',
                        border: selectedOrgIds.includes(org.uuid)
                          ? '1px solid rgba(37, 99, 235, 0.3)'
                          : '1px solid #3a3a3a',
                        cursor: 'pointer',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedOrgIds.includes(org.uuid)}
                        onChange={() => {
                          setSelectedOrgIds(prev =>
                            prev.includes(org.uuid)
                              ? prev.filter(id => id !== org.uuid)
                              : [...prev, org.uuid]
                          )
                        }}
                        style={{ accentColor: '#2563eb' }}
                      />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#e5e5e5' }}>{org.name}</div>
                        <div style={{ fontSize: 11, color: '#888' }}>{org.org_type}</div>
                      </div>
                    </label>
                  ))}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button
                  onClick={() => setShowOrgsModal(false)}
                  style={{
                    padding: '6px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                    color: '#aaa', backgroundColor: 'transparent', border: '1px solid #3a3a3a',
                    borderRadius: 6, cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveOrgs}
                  disabled={savingOrgs}
                  style={{
                    padding: '6px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                    color: 'var(--highlight-text-color, #000)',
                    backgroundColor: 'var(--highlight-color, #eab308)',
                    border: 'none', borderRadius: 6,
                    cursor: savingOrgs ? 'default' : 'pointer',
                    opacity: savingOrgs ? 0.6 : 1,
                  }}
                >
                  {savingOrgs ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {shareDialogJSX}
      {verifyModalJSX}
      <SharedKBDeleteDialog
        open={!!sharedDeleteTarget}
        kbTitle={sharedDeleteTarget?.title ?? ''}
        onCancel={() => setSharedDeleteTarget(null)}
        onChoose={handleSharedDeleteChoice}
      />
      </>
    )
  }

  // Mine/team only — Explore renders its own KBExploreTab.
  const listScope: KBScope = activeTab === 'team' ? 'team' : 'mine'

  // List view
  return (
    <>
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
        {activeTab === 'mine' && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              ref={importInputRef}
              type="file"
              accept=".json,application/json"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleImportFile(f)
              }}
            />
            <button
              onClick={() => importInputRef.current?.click()}
              disabled={importing}
              title="Import a knowledge base from a .kb.json file"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 12px',
                fontSize: 13,
                fontWeight: 600,
                fontFamily: 'inherit',
                color: '#e5e5e5',
                backgroundColor: '#2a2a2a',
                border: '1px solid #3a3a3a',
                borderRadius: 6,
                cursor: importing ? 'default' : 'pointer',
                opacity: importing ? 0.6 : 1,
              }}
            >
              {importing ? <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} /> : <Upload style={{ width: 14, height: 14 }} />}
              {importing ? 'Importing...' : 'Import'}
            </button>
            <button
              onClick={() => setShowCreateModal(true)}
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
              <Plus style={{ width: 14, height: 14 }} />
              New
            </button>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex', gap: 0,
        borderBottom: '1px solid #3a3a3a',
        backgroundColor: '#191919',
        flexShrink: 0,
      }}>
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => { setActiveTab(tab.key); setSearch('') }}
            style={{
              flex: 1,
              padding: '8px 0',
              fontSize: 12,
              fontWeight: 600,
              fontFamily: 'inherit',
              color: activeTab === tab.key ? '#fff' : '#888',
              backgroundColor: 'transparent',
              border: 'none',
              borderBottom: activeTab === tab.key ? '2px solid var(--highlight-color, #eab308)' : '2px solid transparent',
              cursor: 'pointer',
              transition: 'color 0.15s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Search (hidden on Explore — KBExploreTab has its own) */}
      {activeTab !== 'explore' && (
        <KBSearchBar value={search} onChange={setSearch} placeholder="Search..." />
      )}

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

      {activeTab === 'explore' ? (
        <KBExploreTab onAdopted={refresh} />
      ) : (
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px', position: 'relative' }}>
          <KBGridView
            scope={listScope}
            search={search}
            allOrgs={allOrgs}
            onSelect={loadDetail}
            onChat={(uuid, title) => activateKB(uuid, title)}
            onEdit={loadDetail}
            onDelete={activeTab === 'mine' ? handleDelete : undefined}
            onAdopt={activeTab === 'team'
              ? async (uuid) => {
                  try {
                    await scopedMine.adopt(uuid)
                    toast('Added to My KBs', 'success')
                    refresh()
                  } catch (err) {
                    console.error('Failed to adopt KB:', err)
                    toast(err instanceof Error ? err.message : 'Failed to add to My KBs', 'error')
                  }
                }
              : undefined}
            onRemoveRef={activeTab === 'mine'
              ? async (refUuid) => {
                  const kb = scopedMine.knowledgeBases.find((k: KnowledgeBase) => k.reference_uuid === refUuid)
                  const ok = await confirm({
                    title: 'Remove from My KBs?',
                    message: (
                      <>
                        Remove <strong>{kb?.title || 'this knowledge base'}</strong> from My KBs? This only removes your bookmark — the original knowledge base is unaffected, and you can add it again from Explore.
                      </>
                    ),
                    confirmLabel: 'Remove',
                  })
                  if (!ok) return
                  try {
                    await scopedMine.removeRef(refUuid)
                    toast('Removed from My KBs', 'success')
                    refresh()
                  } catch (err) {
                    console.error('Failed to remove KB reference:', err)
                    toast(err instanceof Error ? err.message : 'Failed to remove', 'error')
                  }
                }
              : undefined}
            emptyComponent={activeTab === 'mine' && !search ? <KnowledgeExplainer /> : undefined}
            emptyMessage={
              activeTab === 'team'
                ? 'No knowledge bases shared with your team yet.'
                : 'No knowledge bases found.'
            }
          />
        </div>
      )}
    </div>

    {showCreateModal && (
      <CreateKBModal
        onClose={() => setShowCreateModal(false)}
        onCreate={handleCreate}
      />
    )}
    {shareDialogJSX}
    {verifyModalJSX}
    <SharedKBDeleteDialog
      open={!!sharedDeleteTarget}
      kbTitle={sharedDeleteTarget?.title ?? ''}
      onCancel={() => setSharedDeleteTarget(null)}
      onChoose={handleSharedDeleteChoice}
    />
    </>
  )
}

// Inline tag editor — free-form labels (e.g. "v1.2", "draft", "2026-Q1").
// Owners and examiners/admins can add/remove; everyone else sees read-only chips.
function KBTagsEditor({
  tags, canManage, onSave,
}: {
  tags: string[]
  canManage: boolean
  onSave: (next: string[]) => Promise<void>
}) {
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const normalize = (t: string) => t.trim().slice(0, 50)

  const addTag = async () => {
    const t = normalize(draft)
    if (!t) return
    if (tags.some(existing => existing.toLowerCase() === t.toLowerCase())) {
      setDraft('')
      return
    }
    if (tags.length >= 20) return
    setSaving(true)
    try {
      await onSave([...tags, t])
      setDraft('')
    } finally {
      setSaving(false)
    }
  }

  const removeTag = async (t: string) => {
    setSaving(true)
    try {
      await onSave(tags.filter(x => x !== t))
    } finally {
      setSaving(false)
    }
  }

  if (!canManage && tags.length === 0) return null

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#ccc', marginBottom: 8 }}>Tags</div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {tags.map(t => (
          <span
            key={t}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              fontSize: 11, fontWeight: 600, padding: '2px 4px 2px 8px', borderRadius: 8,
              color: '#cbd5e1', backgroundColor: '#2f2f2f',
              border: '1px solid #3a3a3a',
            }}
          >
            {t}
            {canManage && (
              <button
                onClick={() => removeTag(t)}
                disabled={saving}
                title="Remove tag"
                style={{
                  background: 'transparent', border: 'none',
                  cursor: saving ? 'default' : 'pointer',
                  padding: 0, display: 'flex', color: '#888',
                }}
              >
                <X size={11} />
              </button>
            )}
          </span>
        ))}
        {canManage && tags.length < 20 && (
          <input
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                e.preventDefault()
                addTag()
              } else if (e.key === 'Backspace' && !draft && tags.length > 0) {
                e.preventDefault()
                removeTag(tags[tags.length - 1])
              }
            }}
            onBlur={() => { if (draft.trim()) addTag() }}
            disabled={saving}
            placeholder={tags.length === 0 ? 'e.g. v1.2, draft' : 'Add tag…'}
            maxLength={50}
            style={{
              minWidth: 100, fontSize: 12, fontFamily: 'inherit',
              color: '#e5e5e5', backgroundColor: '#1a1a1a',
              border: '1px solid #333', borderRadius: 6,
              padding: '3px 8px', outline: 'none',
            }}
          />
        )}
      </div>
    </div>
  )
}
