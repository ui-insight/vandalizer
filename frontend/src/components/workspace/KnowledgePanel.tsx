import { useState, useEffect, useCallback, useRef } from 'react'
import { Plus, Loader2, ArrowLeft, X, FileText, Globe, MessageSquare, AlertCircle, AlertTriangle, CheckCircle2, Users, ShieldCheck, Send, Tag, Check, Download, Upload, HelpCircle, Pencil, Pin, PinOff, FolderKanban, ChevronDown, ChevronRight, RefreshCw, Copy } from 'lucide-react'
import { useKnowledgeBases, useScopedKnowledgeBases } from '../../hooks/useKnowledgeBases'
import { describeSourceCurrency, formatCurrencyDateTime, shortHash } from '../knowledge/sourceCurrency'
import { useProjectPins } from '../../hooks/useProjectPins'
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
import { ExplainerPill } from './AutomationsPanel'
import { ShareWithTeamDialog } from '../library/ShareWithTeamDialog'
import { useToast } from '../../contexts/ToastContext'
import { useConfirm } from '../shared/useConfirm'
import { SharedKBDeleteDialog, type SharedKBDeleteChoice } from '../shared/SharedKBDeleteDialog'
import { OptimizedBadge, VerifiedBadge } from '../knowledge/KBTrustBadges'

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
  const { activateKB, activeProjectUuid, activeProjectTitle, activeProjectRole } = useWorkspace()
  const { user } = useAuth()
  const { toast } = useToast()
  const { knowledgeBases, create, remove, transferToTeam, refresh } = useKnowledgeBases()
  const projectPins = useProjectPins(activeProjectUuid)
  // Inside a project, default to showing only the KBs pinned to it; "Show all"
  // escapes the scope. Reset to scoped when the project changes.
  const [projectScoped, setProjectScoped] = useState(true)
  useEffect(() => { setProjectScoped(true) }, [activeProjectUuid])
  const canPin = !!activeProjectUuid && activeProjectRole !== 'viewer'
  const isProjectScoped = !!activeProjectUuid && projectScoped

  const handleTogglePin = async (canonicalUuid: string) => {
    try {
      if (projectPins.isPinned('knowledge_base', canonicalUuid)) {
        await projectPins.unpin('knowledge_base', canonicalUuid)
        toast('Unpinned from project', 'success')
      } else {
        await projectPins.pin('knowledge_base', canonicalUuid)
        toast('Pinned to project', 'success')
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to update pin', 'error')
    }
  }
  const [sharedDeleteTarget, setSharedDeleteTarget] = useState<KnowledgeBase | null>(null)
  const confirm = useConfirm()
  const [activeTab, setActiveTab] = useState<TabKey>('mine')
  const [search, setSearch] = useState('')
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])
  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex = index
    if (e.key === 'ArrowRight') nextIndex = (index + 1) % TABS.length
    else if (e.key === 'ArrowLeft') nextIndex = (index - 1 + TABS.length) % TABS.length
    else if (e.key === 'Home') nextIndex = 0
    else if (e.key === 'End') nextIndex = TABS.length - 1
    else return
    e.preventDefault()
    setActiveTab(TABS[nextIndex].key)
    setSearch('')
    tabRefs.current[nextIndex]?.focus()
  }
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
  // Collapsible detail sections. Collapsing Validation also lifts the inner
  // scroll cap on the Sources list so long source lists become fully visible.
  const [sourcesCollapsed, setSourcesCollapsed] = useState(false)
  const [validationCollapsed, setValidationCollapsed] = useState(false)
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
      // Created from inside a project: auto-pin so it shows in the project's
      // Knowledge tab (pins are the only project↔KB link). A fresh KB is never
      // a reference, so its own uuid is the canonical pin target.
      if (canPin) {
        try {
          await projectPins.pin('knowledge_base', kb.uuid)
        } catch (err) {
          console.error('Failed to pin new KB to project:', err)
        }
      }
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

  // A different KB starts with both detail sections expanded
  useEffect(() => {
    setSourcesCollapsed(false)
    setValidationCollapsed(false)
  }, [selectedKB?.uuid])

  // Sources still being chunked and embedded by a worker. Tracked separately
  // from kb.status because a KB can report "ready" from an earlier build while
  // newly added sources are still pending.
  const inFlightSources = (selectedKB?.sources ?? []).filter(
    s => s.status === 'pending' || s.status === 'processing'
  )
  const inFlightCount = inFlightSources.length

  // Poll while the KB is building or any source is still indexing
  useEffect(() => {
    if (!selectedKB) return
    if (selectedKB.status !== 'building' && inFlightCount === 0) return
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
  }, [selectedKB?.uuid, selectedKB?.status, inFlightCount, refresh])

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

  // Clone lands an owned, editable copy in My KBs (sources re-ingest in the
  // background, so it opens in 'building' status).
  const handleClone = async (uuid: string) => {
    if (cloning) return
    setCloning(true)
    try {
      const clone = await api.cloneKnowledgeBase(uuid)
      const newUuid = (clone as { uuid?: string }).uuid
      toast('Knowledge base cloned — sources are re-indexing', 'success')
      refresh()
      if (newUuid) {
        setActiveTab('mine')
        loadDetail(newUuid)
      }
    } catch (err) {
      console.error('Failed to clone KB:', err)
      toast(err instanceof Error ? err.message : 'Failed to clone knowledge base', 'error')
    } finally {
      setCloning(false)
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
    // Optimistically set status to building so the poller starts — indexing runs
    // on a worker, so this call returns before any source is ready.
    setSelectedKB(prev => prev ? { ...prev, status: 'building' } : prev)
    try {
      const result = await api.addDocumentsToKB(selectedKB.uuid, docUuids)
      const n = result?.added ?? docUuids.length
      if (n === 0) {
        toast('Those documents are already in this knowledge base', 'info')
      } else {
        toast(`Added ${n} document${n === 1 ? '' : 's'} — indexing in background`, 'success')
      }
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
    setSelectedKB(prev => prev ? { ...prev, status: 'building' } : prev)
    try {
      const result = await api.addFolderToKB(selectedKB.uuid, folderUuid, includeSubfolders)
      const n = result?.added ?? 0
      if (n === 0) {
        toast('No new documents found in that folder', 'info')
      } else {
        toast(`Added ${n} document${n === 1 ? '' : 's'} from folder — indexing in background`, 'success')
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
        const skipped = result?.skipped ?? 0
        const plural = (c: number) => (c === 1 ? '' : 's')
        if (n === 0 && skipped > 0) {
          // Nothing was fetched: re-adding an existing URL is a no-op. Say so —
          // a silent "Added 2" here sent one user on a fruitless refresh loop.
          toast(
            `${skipped} URL${plural(skipped)} already in this KB — nothing was fetched. Use the ↻ button on a source to re-fetch its page.`,
            'info',
          )
        } else if (skipped > 0) {
          toast(
            `Added ${n} URL${plural(n)} — crawling in background. ${skipped} already in this KB and not re-fetched.`,
            'success',
          )
        } else {
          toast(`Added ${n} URL${plural(n)} — crawling in background`, 'success')
        }
        loadDetail(selectedKB.uuid)
        refresh()
      })
      .catch(err => {
        console.error('Failed to add URLs:', err)
        toast(err instanceof Error ? err.message : 'Failed to add URLs', 'error')
      })
      .finally(() => setAddingUrls(false))
  }

  const handleRefreshSource = async (source: KnowledgeBaseSource) => {
    if (!selectedKB) return
    try {
      await api.refreshKBSource(selectedKB.uuid, source.uuid)
      // Optimistically flip to building so the status poller starts.
      setSelectedKB(prev => prev ? {
        ...prev,
        status: 'building',
        sources: prev.sources.map(s => s.uuid === source.uuid ? { ...s, status: 'pending' as const } : s),
      } : prev)
      toast('Re-fetching page in background — previous text is kept if the fetch fails', 'success')
      loadDetail(selectedKB.uuid)
      refresh()
    } catch (err) {
      console.error('Failed to refresh source:', err)
      toast(err instanceof Error ? err.message : 'Failed to refresh source', 'error')
    }
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
  const [cloning, setCloning] = useState(false)
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
        <label htmlFor="verify-summary" style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#aaa', marginBottom: 4 }}>Summary</label>
        <input
          id="verify-summary"
          value={verifySummary}
          onChange={e => setVerifySummary(e.target.value)}
          placeholder="Brief summary of this knowledge base"
          style={{
            width: '100%', padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
            backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
            color: '#e5e5e5', marginBottom: 12, boxSizing: 'border-box',
          }}
        />
        <label htmlFor="verify-description" style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#aaa', marginBottom: 4 }}>Description</label>
        <textarea
          id="verify-description"
          value={verifyDescription}
          onChange={e => setVerifyDescription(e.target.value)}
          placeholder="Detailed description, intended use, etc."
          rows={3}
          style={{
            width: '100%', padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
            backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
            color: '#e5e5e5', marginBottom: 12, resize: 'vertical',
            boxSizing: 'border-box',
          }}
        />
        <label htmlFor="verify-category" style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#aaa', marginBottom: 4 }}>Category</label>
        <input
          id="verify-category"
          value={verifyCategory}
          onChange={e => setVerifyCategory(e.target.value)}
          placeholder="e.g. Legal, Medical, Research"
          style={{
            width: '100%', padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
            backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
            color: '#e5e5e5', marginBottom: 16, boxSizing: 'border-box',
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
    // Manage rights come from the backend's own gate (owner / examiner on a
    // verified KB / team manager / admin). Without this, a viewer on e.g. an
    // adopted verified catalog KB could walk the whole add-source flow and only
    // hit "You don't have permission to manage this knowledge base." on submit.
    const canManageKB = selectedKB.can_manage !== false
    const noManageReason = "You don't have permission to manage this knowledge base."
    // A ready KB with zero indexed chunks has nothing to retrieve — chatting
    // with it only produces a misleading "still indexing" reply.
    const canChatKB = selectedKB.status === 'ready' && selectedKB.total_chunks > 0
    // Export serializes the KB's sources. With none it downloads a file nobody
    // can use — the backend refuses it now, so say why before the click.
    const hasSources = selectedKB.total_sources > 0
    return (
      <>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#1e1e1e', position: 'relative' }}>
        {/* Header */}
        <div
          style={{
            height: 50,
            backgroundColor: 'var(--color-panel-dark)',
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
            type="button"
            aria-label="Back to knowledge bases"
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
                aria-label="Knowledge base title"
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
                  padding: '2px 8px', minWidth: 0,
                }}
              />
              <button
                type="button"
                aria-label="Save title"
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
                onClick={canManageKB ? () => { setTitleDraft(selectedKB.title); setEditingTitle(true) } : undefined}
                title={canManageKB ? 'Click to rename' : noManageReason}
                style={{
                  fontSize: 16, fontWeight: 600, color: '#fff',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  cursor: canManageKB ? 'text' : 'default', borderRadius: 4, padding: '2px 0',
                  minWidth: 0,
                }}
              >
                {selectedKB.title}
              </span>
              {canManageKB && (
                <button
                  type="button"
                  aria-label="Edit title"
                  onClick={() => { setTitleDraft(selectedKB.title); setEditingTitle(true) }}
                  title="Edit title"
                  style={{
                    background: 'transparent', border: 'none', cursor: 'pointer',
                    padding: 2, display: 'flex', color: '#888', flexShrink: 0,
                  }}
                >
                  <Pencil size={13} />
                </button>
              )}
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
          {selectedKB.verified && <VerifiedBadge />}
          <OptimizedBadge kb={selectedKB} withTime />
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
          <div role="status" aria-live="polite" style={{ textAlign: 'center', padding: 40, color: '#888' }}>
            <Loader2 aria-hidden="true" style={{ width: 20, height: 20, margin: '0 auto', animation: 'spin 1s linear infinite' }} />
            <span style={{ position: 'absolute', width: 1, height: 1, padding: 0, margin: -1, overflow: 'hidden', clip: 'rect(0 0 0 0)', border: 0 }}>Loading knowledge base…</span>
          </div>
        ) : (
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px' }}>
            {/* Description */}
            <div style={{ marginBottom: 12 }}>
              {editingDescription ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <textarea
                    autoFocus
                    aria-label="Knowledge base description"
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
                      padding: '8px 10px',
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
                    {selectedKB.description || (canManageKB
                      ? 'No description yet — add one to help others understand what this KB is for.'
                      : 'No description.')}
                  </div>
                  {canManageKB && (
                    <button
                      type="button"
                      aria-label="Edit description"
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
                  )}
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
              <div role="status" aria-live="polite" style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 14px', marginBottom: 16, borderRadius: 8,
                backgroundColor: 'rgba(217, 119, 6, 0.1)',
                border: '1px solid rgba(217, 119, 6, 0.25)',
              }}>
                <Loader2 size={16} aria-hidden="true" style={{ color: '#d97706', animation: 'spin 1s linear infinite', flexShrink: 0 }} />
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

            {/* Indexing progress banner — covers the wait right after adding and
                the case where the user navigates back while work is still queued. */}
            {(addingDocs || inFlightCount > 0) && (
              <div role="status" aria-live="polite" style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 14px', marginBottom: 16, borderRadius: 8,
                backgroundColor: 'rgba(217, 119, 6, 0.1)',
                border: '1px solid rgba(217, 119, 6, 0.25)',
              }}>
                <Loader2 size={16} aria-hidden="true" style={{ color: '#d97706', animation: 'spin 1s linear infinite', flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#e5e5e5' }}>
                    {inFlightCount > 0
                      ? `Indexing ${inFlightCount} source${inFlightCount === 1 ? '' : 's'}...`
                      : 'Adding documents...'}
                  </div>
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                    Large documents can take a few minutes. Sources turn green below as they
                    finish — you can leave this page and come back.
                  </div>
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
              <button
                onClick={() => setShowDocPicker(true)}
                disabled={addingDocs || !canManageKB}
                title={canManageKB ? undefined : noManageReason}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: '#e5e5e5',
                  backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
                  cursor: addingDocs || !canManageKB ? 'default' : 'pointer',
                  opacity: addingDocs || !canManageKB ? 0.5 : 1,
                }}
              >
                <FileText size={13} />
                {addingDocs ? 'Adding...' : 'Add Documents'}
              </button>
              <button
                onClick={() => setShowUrlModal(true)}
                disabled={addingUrls || !canManageKB}
                title={canManageKB ? undefined : noManageReason}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: '#e5e5e5', backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a',
                  borderRadius: 6,
                  cursor: addingUrls || !canManageKB ? 'default' : 'pointer',
                  opacity: addingUrls || !canManageKB ? 0.5 : 1,
                }}
              >
                {addingUrls ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Globe size={13} />}
                {addingUrls ? 'Adding...' : 'Add URLs'}
              </button>
              <button
                onClick={handleChat}
                disabled={!canChatKB}
                title={!canChatKB && selectedKB.status === 'ready'
                  ? 'This knowledge base has no indexed content yet'
                  : undefined}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: canChatKB ? 'var(--highlight-text-color, #000)' : '#666',
                  backgroundColor: canChatKB ? 'var(--highlight-color, #eab308)' : '#2a2a2a',
                  border: canChatKB ? 'none' : '1px solid #3a3a3a',
                  borderRadius: 6,
                  cursor: canChatKB ? 'pointer' : 'default',
                  opacity: canChatKB ? 1 : 0.5,
                }}
              >
                <MessageSquare size={13} />
                Chat with this KB
              </button>
              {canPin && (() => {
                const pinned = projectPins.isPinned('knowledge_base', selectedKB.uuid)
                return (
                  <button
                    type="button"
                    role="switch"
                    aria-checked={pinned}
                    onClick={() => handleTogglePin(selectedKB.uuid)}
                    title={pinned ? `Unpin from ${activeProjectTitle || 'this project'}` : `Pin to ${activeProjectTitle || 'this project'}`}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6,
                      padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                      color: pinned ? 'var(--highlight-text-color, #000)' : '#e5e5e5',
                      backgroundColor: pinned ? 'var(--highlight-color, #eab308)' : '#2a2a2a',
                      border: pinned ? 'none' : '1px solid #3a3a3a',
                      borderRadius: 6, cursor: 'pointer',
                    }}
                  >
                    {pinned ? <Pin size={13} fill="currentColor" /> : <PinOff size={13} />}
                    {pinned ? 'Pinned to Project' : 'Pin to Project'}
                  </button>
                )
              })()}
              <button
                type="button"
                role="switch"
                aria-checked={!!selectedKB.shared_with_team}
                onClick={() => handleToggleShare(selectedKB)}
                disabled={!canManageKB}
                title={canManageKB ? undefined : noManageReason}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: selectedKB.shared_with_team ? 'rgb(0, 128, 128)' : '#e5e5e5',
                  backgroundColor: selectedKB.shared_with_team ? 'rgba(0, 128, 128, 0.1)' : '#2a2a2a',
                  border: selectedKB.shared_with_team ? '1px solid rgba(0, 128, 128, 0.3)' : '1px solid #3a3a3a',
                  borderRadius: 6,
                  cursor: canManageKB ? 'pointer' : 'default',
                  opacity: canManageKB ? 1 : 0.5,
                }}
              >
                <Users size={13} />
                {selectedKB.shared_with_team ? 'Shared with Team' : 'Share with Team'}
              </button>
              <button
                onClick={handleExport}
                disabled={exporting || !hasSources}
                title={hasSources
                  ? 'Download this knowledge base as a JSON file'
                  : 'Add at least one source to this knowledge base first'}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: '#e5e5e5', backgroundColor: '#2a2a2a',
                  border: '1px solid #3a3a3a', borderRadius: 6,
                  cursor: exporting || !hasSources ? 'default' : 'pointer',
                  opacity: exporting || !hasSources ? 0.5 : 1,
                }}
              >
                {exporting ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Download size={13} />}
                {exporting ? 'Exporting...' : 'Export'}
              </button>
              {/* Clone lives on the KB cards too, but this is the page you are
                  on once you have opened a KB and decided you want a copy of
                  it — the support ticket was written from here. */}
              <button
                onClick={() => handleClone(selectedKB.uuid)}
                disabled={cloning || !hasSources}
                title={hasSources
                  ? 'Make an editable copy of this knowledge base'
                  : 'Add at least one source to this knowledge base first'}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  color: '#e5e5e5', backgroundColor: '#2a2a2a',
                  border: '1px solid #3a3a3a', borderRadius: 6,
                  cursor: cloning || !hasSources ? 'default' : 'pointer',
                  opacity: cloning || !hasSources ? 0.5 : 1,
                }}
              >
                {cloning ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Copy size={13} />}
                {cloning ? 'Cloning...' : 'Clone'}
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

            {/* A disabled button's tooltip is unreachable by keyboard and touch,
                so say once, visibly, why the add-source actions are inert. */}
            {!canManageKB && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                marginTop: -8, marginBottom: 16, fontSize: 11, color: '#999',
              }}>
                <ShieldCheck size={12} aria-hidden="true" style={{ flexShrink: 0 }} />
                <span>View only — {noManageReason}</span>
              </div>
            )}

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
              canManage={canManageKB}
              onSave={async (next) => {
                await api.updateKnowledgeBase(selectedKB.uuid, { tags: next })
                setSelectedKB(prev => prev ? { ...prev, tags: next } : prev)
                refresh()
              }}
            />

            {/* Sources list */}
            <button
              type="button"
              onClick={() => setSourcesCollapsed(c => !c)}
              aria-expanded={!sourcesCollapsed}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                padding: 0, marginBottom: sourcesCollapsed ? 0 : 8,
                background: 'transparent', border: 'none',
                fontFamily: 'inherit', cursor: 'pointer', color: '#ccc',
                textAlign: 'left',
              }}
            >
              {sourcesCollapsed ? <ChevronRight size={14} style={{ color: '#888' }} /> : <ChevronDown size={14} style={{ color: '#888' }} />}
              <span style={{ fontSize: 13, fontWeight: 600 }}>Sources</span>
              <span style={{ marginLeft: 'auto', fontSize: 11, color: '#666' }}>
                {selectedKB.sources.length} {selectedKB.sources.length === 1 ? 'source' : 'sources'}
              </span>
            </button>
            {sourcesCollapsed ? null : selectedKB.sources.length === 0 ? (
              <div style={{ fontSize: 12, color: '#888', padding: '20px 0' }}>
                No sources added yet. Add documents or URLs above.
              </div>
            ) : (
              <div style={{
                display: 'flex', flexDirection: 'column', gap: 6,
                // With Validation collapsed the sources list gets the freed
                // space: no inner scroll cap, the full list is visible.
                maxHeight: validationCollapsed ? undefined : 320, overflowY: 'auto',
                paddingRight: 4,
              }}>
                {selectedKB.sources.map((source: KnowledgeBaseSource) => {
                  // A ready-but-truncated source is incomplete: the fetched page
                  // was cut off at the size cap, so it retrieves wrong answers
                  // for anything past the cut. Show an amber warning, not a
                  // clean green check.
                  const isTruncated = source.status === 'ready' && !!source.truncated
                  const st = isTruncated
                    ? { icon: AlertTriangle, color: '#d97706' }
                    : (SOURCE_STATUS[source.status] || SOURCE_STATUS.pending)
                  const StatusIcon = st.icon
                  const autoLabel = source.source_type === 'url'
                    ? (source.url_title || source.url || source.uuid)
                    : (source.document_title || source.document_uuid || source.uuid)
                  const displayLabel = source.custom_name || autoLabel
                  // The document was deleted from Files. Its chunks are still
                  // indexed and still answer questions, so the row stays — but
                  // it says so, the way an extraction test case does.
                  const docDeleted = source.source_type === 'document'
                    && !!source.document_uuid
                    && source.document_exists === false
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
                      role={canInspect ? 'button' : undefined}
                      tabIndex={canInspect ? 0 : undefined}
                      aria-label={canInspect ? `Inspect source: ${displayLabel}` : undefined}
                      onKeyDown={canInspect ? (e) => {
                        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                          e.preventDefault()
                          setInspectingSource(source)
                        }
                      } : undefined}
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
                            aria-label="Source name"
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
                            {docDeleted && (
                              <span
                                style={{ color: '#d97706', marginLeft: 6, fontStyle: 'italic' }}
                                title="The source document was deleted from Files. This knowledge base still answers from the text it indexed."
                              >
                                · source deleted
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
                        {!isRenaming && source.status === 'ready' && (() => {
                          // Currency beside the size: when the text was last
                          // actually obtained / indexed, whether the last
                          // refresh failed and what is being served instead,
                          // and a fingerprint of the indexed text — so an
                          // evaluator can check a source is current without
                          // opening the original.
                          const cur = describeSourceCurrency(source.currency)
                          const hash = source.currency?.content_hash
                          const toneColor = cur?.tone === 'warn' ? '#b45309' : cur?.tone === 'error' ? '#ef4444' : '#888'
                          return (
                            <div style={{ fontSize: 11, color: '#888', marginTop: 2 }} data-testid="source-currency">
                              {source.chunk_count} chunks
                              {cur && (
                                <>
                                  {' · '}
                                  <span style={{ color: toneColor }} title={[
                                    source.currency?.last_refresh_attempted_at ? `Last refresh attempted: ${formatCurrencyDateTime(source.currency.last_refresh_attempted_at)}` : null,
                                    source.currency?.last_retrieved_at ? `Last retrieved: ${formatCurrencyDateTime(source.currency.last_retrieved_at)}` : null,
                                    source.currency?.last_ingested_at ? `Last indexed: ${formatCurrencyDateTime(source.currency.last_ingested_at)}` : null,
                                    source.currency?.content_retrieved_at ? `Serving text retrieved: ${formatCurrencyDateTime(source.currency.content_retrieved_at)}` : null,
                                    source.currency?.last_refresh_error ? `Last refresh error: ${source.currency.last_refresh_error}` : null,
                                  ].filter(Boolean).join('\n')}>
                                    {cur.summary}
                                  </span>
                                </>
                              )}
                              {hash && (
                                <>
                                  {' · '}
                                  <span
                                    style={{ fontFamily: 'monospace' }}
                                    title={`${source.currency?.content_hash_algorithm ?? 'sha256'} of the indexed text: ${hash}${source.currency?.content_hash_recorded ? '' : ' (computed from the stored snapshot; recorded at the next refresh)'}`}
                                  >
                                    {shortHash(hash)}
                                  </span>
                                </>
                              )}
                            </div>
                          )
                        })()}
                        {!isRenaming && (source.status === 'processing' || source.status === 'pending') && (
                          <div style={{ fontSize: 11, color: '#d97706', marginTop: 2 }}>
                            {source.status === 'processing'
                              ? 'Indexing… large documents can take a few minutes'
                              : 'Waiting for document text to finish extracting…'}
                          </div>
                        )}
                        {!isRenaming && isTruncated && (
                          <div style={{ fontSize: 11, color: '#b45309', marginTop: 2 }}>
                            Page too long — text was cut off; later sections aren’t in this source.
                          </div>
                        )}
                      </div>
                      {isRenaming ? (
                        <>
                          <button
                            type="button"
                            aria-label="Save name"
                            onClick={(e) => { e.stopPropagation(); handleRenameSource() }}
                            disabled={savingRename}
                            title="Save name"
                            style={{ background: 'transparent', border: 'none', cursor: savingRename ? 'default' : 'pointer', padding: 2, display: 'flex' }}
                          >
                            <Check size={14} style={{ color: '#22c55e' }} />
                          </button>
                          <button
                            type="button"
                            aria-label="Cancel rename"
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
                            aria-label={isTruncated ? 'Source text was truncated' : undefined}
                            style={{
                              color: st.color, flexShrink: 0,
                              ...(source.status === 'processing' || source.status === 'pending' ? { animation: 'spin 1s linear infinite' } : {}),
                            }}
                          >
                            {isTruncated && <title>Page too long — text was cut off; later sections aren’t in this source.</title>}
                          </StatusIcon>
                          {canManageKB && (
                            <>
                              <button
                                type="button"
                                aria-label="Rename source"
                                onClick={(e) => { e.stopPropagation(); beginRenameSource(source) }}
                                title={source.custom_name ? 'Rename (or clear to revert to original)' : 'Rename source'}
                                style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, display: 'flex' }}
                              >
                                <Pencil size={12} style={{ color: '#888' }} />
                              </button>
                              {source.source_type === 'url' && (
                                <button
                                  type="button"
                                  aria-label="Refresh source"
                                  onClick={(e) => { e.stopPropagation(); handleRefreshSource(source) }}
                                  disabled={source.status === 'processing' || source.status === 'pending'}
                                  title={
                                    source.processed_at
                                      ? `Re-fetch this page (last fetched ${new Date(source.processed_at).toLocaleDateString()})`
                                      : 'Re-fetch this page'
                                  }
                                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, display: 'flex' }}
                                >
                                  <RefreshCw size={12} style={{ color: '#888' }} />
                                </button>
                              )}
                              <button
                                type="button"
                                aria-label="Remove source"
                                onClick={(e) => { e.stopPropagation(); handleRemoveSource(source.uuid) }}
                                title="Remove source"
                                style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, display: 'flex' }}
                              >
                                <X size={12} style={{ color: '#666' }} />
                              </button>
                            </>
                          )}
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
              canManage={canManageKB}
              kbHasSources={hasSources}
              onCloned={(newUuid) => { refresh(); loadDetail(newUuid) }}
              collapsed={validationCollapsed}
              onToggleCollapsed={() => setValidationCollapsed(c => !c)}
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
          minHeight: 50,
          backgroundColor: 'var(--color-panel-dark)',
          boxShadow: '0 0px 23px -8px rgb(211, 211, 211)',
          padding: '8px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          columnGap: 12,
          rowGap: 8,
          flexShrink: 0,
          zIndex: 300,
          position: 'relative',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', minWidth: 0 }}>
          <span style={{ fontSize: 18, fontWeight: 600, color: '#fff' }}>Knowledge Bases</span>
          <ExplainerPill label="What are knowledge bases?" onClick={() => setShowExplainer(true)} />
        </div>
        {activeTab === 'mine' && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0, marginLeft: 'auto' }}>
            <input
              ref={importInputRef}
              type="file"
              aria-label="Upload files"
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
      <div
        role="tablist"
        aria-label="Knowledge base views"
        style={{
          display: 'flex', gap: 0,
          borderBottom: '1px solid #3a3a3a',
          backgroundColor: 'var(--color-panel-dark)',
          flexShrink: 0,
        }}
      >
        {TABS.map((tab, index) => (
          <button
            key={tab.key}
            ref={el => { tabRefs.current[index] = el }}
            role="tab"
            type="button"
            id={`kb-tab-${tab.key}`}
            aria-selected={activeTab === tab.key}
            aria-controls="kb-tabpanel"
            tabIndex={activeTab === tab.key ? 0 : -1}
            onKeyDown={e => handleTabKeyDown(e, index)}
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

      {/* Project scope bar — flip between KBs pinned to this project and all of
          them. Only meaningful on the My/Team grids (Explore is the catalog). */}
      {activeProjectUuid && activeTab !== 'explore' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '7px 12px',
          backgroundColor: '#202020',
          borderBottom: '1px solid #2f2f2f',
          flexShrink: 0,
        }}>
          <FolderKanban size={13} style={{ color: 'var(--highlight-color, #eab308)', flexShrink: 0 }} />
          <span style={{ fontSize: 12, color: '#aaa', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {projectScoped
              ? <>Pinned to <strong style={{ color: '#ddd' }}>{activeProjectTitle}</strong></>
              : <>All knowledge bases</>}
          </span>
          <button
            onClick={() => setProjectScoped(s => !s)}
            style={{
              marginLeft: 'auto', flexShrink: 0,
              padding: '3px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
              color: '#ccc', backgroundColor: 'transparent',
              border: '1px solid #3a3a3a', borderRadius: 12, cursor: 'pointer',
            }}
          >
            {projectScoped ? 'Show all' : 'Show project only'}
          </button>
        </div>
      )}

      {/* Search (hidden on Explore — KBExploreTab has its own) */}
      {activeTab !== 'explore' && (
        <KBSearchBar value={search} onChange={setSearch} placeholder="Search..." />
      )}

      {/* Error */}
      {error && (
        <div role="alert" style={{
          margin: '8px 12px 0', padding: '8px 12px', fontSize: 12,
          color: '#b91c1c', backgroundColor: '#fef2f2', borderRadius: 6,
          border: '1px solid #fecaca',
        }}>
          {error}
        </div>
      )}

      <div
        role="tabpanel"
        id="kb-tabpanel"
        aria-labelledby={`kb-tab-${activeTab}`}
        style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}
      >
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
            onClone={handleClone}
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
            filterUuids={isProjectScoped ? projectPins.idsByType('knowledge_base') : undefined}
            pinnedUuids={canPin ? projectPins.idsByType('knowledge_base') : undefined}
            onTogglePin={canPin ? handleTogglePin : undefined}
            emptyComponent={!isProjectScoped && activeTab === 'mine' && !search ? <KnowledgeExplainer /> : undefined}
            emptyMessage={
              isProjectScoped
                ? `No knowledge bases pinned to ${activeProjectTitle || 'this project'}. Pin one here or in Explore, or switch to "Show all".`
                : activeTab === 'team'
                  ? 'No knowledge bases shared with your team yet.'
                  : 'No knowledge bases found.'
            }
          />
        </div>
      )}
      </div>
    </div>

    {showCreateModal && (
      <CreateKBModal
        onClose={() => setShowCreateModal(false)}
        onCreate={handleCreate}
        existingTitles={knowledgeBases.filter((kb) => !kb.verified).map((kb) => kb.title)}
      />
    )}
    {showExplainer && <KnowledgeExplainer onClose={() => setShowExplainer(false)} />}
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
                type="button"
                aria-label={`Remove tag ${t}`}
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
            aria-label="Add a tag"
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
              padding: '3px 8px',
            }}
          />
        )}
      </div>
    </div>
  )
}
