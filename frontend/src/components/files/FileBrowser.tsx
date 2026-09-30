import { WorkspaceSectionHeader } from '../shared/WorkspaceSectionHeader'
import { useCallback, useMemo, useState, useRef, useEffect, type ReactNode, type DragEvent } from 'react'
import { Plus, Folder as FolderIcon, Upload, Trash2, Download, FolderInput } from 'lucide-react'
import { useTeams } from '../../hooks/useTeams'
import { useDocuments } from '../../hooks/useDocuments'
import { useBreadcrumbs } from '../../hooks/useFolders'
import { useUpload } from '../../hooks/useUpload'
import { Breadcrumbs } from './Breadcrumbs'
import { FileList } from './FileList'
import { UploadZone } from './UploadZone'
import { UploadProgress } from './UploadProgress'
import { ContextMenu } from './ContextMenu'
import { RenameDialog } from './RenameDialog'
import { CreateFolderDialog } from './CreateFolderDialog'
import { MoveFolderDialog } from './MoveFolderDialog'
import { MoveFileDialog } from './MoveFileDialog'
import { useConfirm } from '../shared/useConfirm'
import { useToast } from '../../contexts/ToastContext'
import { deleteFile, renameFile, downloadFile, downloadFilesAsZip, moveFile, fetchDocumentUsage, type DeleteFileResult, type DocumentUsage } from '../../api/files'
import { DocumentUsageDialog, UsageSummaryList, UsageCheckFailedNote, RemoveFromKnowledgeBasesOption, describeDeleteEffects, mergeUsage, summarizeUsage, type UsageGroups } from './DocumentUsageDialog'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { createFolder, renameFolder, deleteFolder, convertFolderToTeam, moveFolder, exportFolder } from '../../api/folders'
import { listAutomations } from '../../api/automations'
import type { Document, Folder } from '../../types/document'
import { isDocReady } from '../../utils/processingStatus'
import { SUPPORTED_ACCEPT_ATTR } from '../../utils/fileTypes'

export type SortColumn = 'name' | 'modified'
export type SortDirection = 'asc' | 'desc'
export interface SortState {
  column: SortColumn
  direction: SortDirection
}

export interface ContentMatch {
  uuid: string
  title: string
  snippet: string
  extension: string
  num_pages: number
  created_at: string
  updated_at: string
  processing: boolean
  valid: boolean
  task_status: string | null
  folder: string | null
  token_count: number
  /** Carried through from the search endpoint so a cross-folder hit shows
   * the same caveat the in-folder row does (#803). */
  ingestion_warnings?: string[]
  ingestion_warning_text?: string
}

interface FileBrowserProps {
  searchAction?: ReactNode
  searchField?: ReactNode
  selectedDocumentUuids?: string[]
  selectedFolderUuids?: string[]
  onDocClick?: (doc: Document) => void
  contentSearchState?: 'loading' | 'error' | null
  onRetryContentSearch?: () => void
  searchQuery?: string
  contentMatches?: ContentMatch[]
  onSelectionChange?: (docUuids: string[]) => void
  onDocNamesChange?: (names: Record<string, string>) => void
  onFolderSelectionChange?: (folderUuids: string[]) => void
  onFolderNamesChange?: (names: Record<string, string>) => void
  // Emits the subset of selected docs that are still being processed
  // (text extraction, OCR, indexing, etc.). Used by the chat banner to
  // avoid the false "ready for analysis" claim.
  onSelectionProcessingChange?: (
    docs: Array<{ uuid: string; title: string; status: string | null }>,
  ) => void
  currentFolder?: string | null
  onFolderNavigate?: (folderId: string | null) => void
  // Scope the chat to a folder and focus the composer ("Ask about folder").
  onAskAboutFolder?: (folder: Folder) => void
  // Run a workflow against / add to a KB every document in a folder.
  onRunWorkflowOnFolder?: (folder: Folder) => void
  onAddFolderToKB?: (folder: Folder) => void
  // When set (project scope), this folder is the browser's home/floor:
  // breadcrumbs start here and navigation can't go above it.
  rootFolder?: string | null
  rootLabel?: string | null
  // Override the team scope used to list/scope documents (project's team).
  teamScopeUuid?: string
}

// Usage for one or more documents, merged. `undefined` when any lookup fails,
// so the confirmation can say the check did not happen rather than imply
// "used nowhere".
async function collectUsage(docUuids: string[]): Promise<UsageGroups | undefined> {
  const settled = await Promise.allSettled(docUuids.map(u => fetchDocumentUsage(u)))
  const ok: DocumentUsage[] = []
  for (const r of settled) {
    if (r.status !== 'fulfilled') return undefined
    ok.push(r.value)
  }
  return mergeUsage(ok)
}

// Knowledge bases that still hold a copy after "also remove" — ones the user
// cannot manage. Named, so the dialog's promise is never silently broken.
function keptKnowledgeBasesMessage(results: DeleteFileResult[]): string | null {
  const kept = new Map<string, string>()
  for (const r of results) for (const kb of r.knowledge_bases_kept ?? []) kept.set(kb.uuid, kb.title)
  if (kept.size === 0) return null
  const titles = [...kept.values()].map(t => `"${t}"`).join(', ')
  return `Still in ${kept.size === 1 ? 'knowledge base' : 'knowledge bases'} ${titles} — it couldn't be removed there (you may not manage ${kept.size === 1 ? 'it' : 'them'}). Remove it from the knowledge base itself, or ask its owner.`
}

// The delete confirmation names what it deletes; past this many, "and N more".
const DELETE_NAME_CAP = 8

export function FileBrowser({ searchAction, searchField, selectedDocumentUuids, selectedFolderUuids, onDocClick, searchQuery = '', contentMatches, contentSearchState, onRetryContentSearch, onSelectionChange, onDocNamesChange, onFolderSelectionChange, onFolderNamesChange, onSelectionProcessingChange, currentFolder: controlledFolder, onFolderNavigate, onAskAboutFolder, onRunWorkflowOnFolder, onAddFolderToKB, rootFolder = null, rootLabel, teamScopeUuid }: FileBrowserProps) {
  const { currentTeam } = useTeams()
  const confirm = useConfirm()
  const { toast } = useToast()

  const [internalFolder, setInternalFolder] = useState<string | null>(null)
  const currentFolder = controlledFolder !== undefined ? controlledFolder : internalFolder
  const setCurrentFolder = onFolderNavigate ?? setInternalFolder
  const { documents, folders, loading, error: contentsError, refresh } = useDocuments(currentFolder, teamScopeUuid ?? currentTeam?.uuid)
  const { breadcrumbs } = useBreadcrumbs(currentFolder)

  // When rooted at a project folder, trim the breadcrumb trail to start at that
  // folder so the project root acts as "Home" and ancestors above it are hidden.
  const displayBreadcrumbs = useMemo(() => {
    if (!rootFolder) return breadcrumbs
    const idx = breadcrumbs.findIndex(b => b.uuid === rootFolder)
    return idx >= 0 ? breadcrumbs.slice(idx + 1) : breadcrumbs
  }, [breadcrumbs, rootFolder])
  const { uploads, upload, dismissUpload, lastUploadedUuid, clearLastUploaded } = useUpload(currentFolder, refresh)

  // Load watched folder UUIDs from automations
  const [watchedFolderUuids, setWatchedFolderUuids] = useState<Set<string>>(new Set())
  useEffect(() => {
    listAutomations()
      .then(automations => {
        const uuids = new Set<string>()
        for (const a of automations) {
          if (a.trigger_type === 'folder_watch' && a.enabled) {
            const folderId = (a.trigger_config as Record<string, unknown>)?.folder_id
            if (typeof folderId === 'string') uuids.add(folderId)
          }
        }
        setWatchedFolderUuids(uuids)
      })
      .catch(() => {})
  }, [])

  // Auto-open the first document after upload
  useEffect(() => {
    if (!lastUploadedUuid || documents.length === 0) return
    const doc = documents.find(d => d.uuid === lastUploadedUuid)
    if (doc) {
      onDocClick?.(doc)
      clearLastUploaded()
    }
  }, [lastUploadedUuid, documents, onDocClick, clearLastUploaded])

  // Sort state
  const [sort, setSort] = useState<SortState>({ column: 'modified', direction: 'desc' })
  const handleSort = useCallback((column: SortColumn) => {
    setSort(prev =>
      prev.column === column
        ? { column, direction: prev.direction === 'asc' ? 'desc' : 'asc' }
        : { column, direction: 'asc' }
    )
  }, [])

  // Bulk selection
  const [internalSelection, setInternalSelection] = useState<Set<string>>(new Set())
  const selectedUuids = useMemo(() => {
    if (selectedDocumentUuids === undefined) return internalSelection
    const visible = new Set([...documents, ...folders, ...(contentMatches ?? [])].map(item => item.uuid))
    return new Set([...selectedDocumentUuids, ...(selectedFolderUuids ?? [])].filter(uuid => visible.has(uuid)))
  }, [internalSelection, selectedDocumentUuids, selectedFolderUuids, documents, folders, contentMatches])
  // Only explicit selection actions change chat scope. A list refresh must
  // never emit an empty selection over a document just attached in chat.
  const setSelectedUuids = useCallback((update: Set<string> | ((previous: Set<string>) => Set<string>)) => {
    const next = typeof update === 'function' ? update(selectedUuids) : update
    setInternalSelection(next)
    const folderIds = new Set(folders.map(folder => folder.uuid))
    onSelectionChange?.([...next].filter(uuid => !folderIds.has(uuid)))
    onFolderSelectionChange?.([...next].filter(uuid => folderIds.has(uuid)))
  }, [selectedUuids, folders, onSelectionChange, onFolderSelectionChange])
  const [bulkDeleting, setBulkDeleting] = useState(false)

  // Sync selected document UUIDs (excluding folders) to parent
  useEffect(() => {
    if (!onSelectionChange) return
    const selectedDocs = documents.filter(d => selectedUuids.has(d.uuid))
    // Also emit a names map so the chat can show pills with document titles
    const names: Record<string, string> = {}
    for (const d of selectedDocs) names[d.uuid] = d.title
    onDocNamesChange?.(names)
    // And which selected docs aren't fully ready yet. `processing` flips off
    // after text extraction, but the doc still goes through RAG indexing
    // (task_status="readying") before it's truly ready for analysis. Use
    // isDocReady so the chat banner stays accurate across that whole window.
    onSelectionProcessingChange?.(
      selectedDocs
        .filter(d => !isDocReady(d))
        .map(d => ({ uuid: d.uuid, title: d.title, status: d.task_status })),
    )
  }, [selectedUuids, documents, onSelectionChange, onDocNamesChange, onSelectionProcessingChange])

  // Sync selected folder UUIDs to parent
  useEffect(() => {
    if (!onFolderSelectionChange) return
    const selectedFolders = folders.filter(f => selectedUuids.has(f.uuid))
    // Names too, so the chat can title the folder chips (mirrors onDocNamesChange)
    const names: Record<string, string> = {}
    for (const f of selectedFolders) names[f.uuid] = f.title
    onFolderNamesChange?.(names)
  }, [selectedUuids, folders, onFolderSelectionChange, onFolderNamesChange])

  // Clear selection when navigating folders
  const previousFolder = useRef(currentFolder)
  useEffect(() => {
    if (previousFolder.current === currentFolder) return
    previousFolder.current = currentFolder
    setSelectedUuids(new Set())
  }, [currentFolder, setSelectedUuids])

  // Search (query provided via prop, content matches from API)
  const filteredFolders = useMemo(() => {
    if (!searchQuery.trim()) return folders
    const q = searchQuery.toLowerCase()
    return folders.filter(f => f.title.toLowerCase().includes(q))
  }, [folders, searchQuery])

  // Build a set of content-matched UUIDs and a snippet map
  const contentMatchUuids = useMemo(() => {
    if (!contentMatches) return new Set<string>()
    return new Set(contentMatches.map(m => m.uuid))
  }, [contentMatches])

  const snippetMap = useMemo(() => {
    const map = new Map<string, string>()
    if (contentMatches) {
      for (const m of contentMatches) {
        if (m.snippet) map.set(m.uuid, m.snippet)
      }
    }
    return map
  }, [contentMatches])

  const filteredDocuments = useMemo(() => {
    if (!searchQuery.trim()) return documents
    const q = searchQuery.toLowerCase()
    // Include docs matching by title OR by content from current folder
    const matched = documents.filter(d =>
      d.title.toLowerCase().includes(q) || contentMatchUuids.has(d.uuid)
    )
    // Merge in content matches from other folders (not already loaded)
    if (contentMatches) {
      const loadedUuids = new Set(documents.map(d => d.uuid))
      for (const m of contentMatches) {
        if (!loadedUuids.has(m.uuid)) {
          matched.push({
            id: m.uuid,
            uuid: m.uuid,
            title: m.title,
            extension: m.extension,
            processing: m.processing,
            valid: m.valid,
            task_status: m.task_status,
            folder: m.folder,
            created_at: m.created_at,
            updated_at: m.updated_at,
            token_count: m.token_count,
            num_pages: m.num_pages,
            // Without these a cross-folder search hit renders as a clean row
            // even when the document was only partly read (#803).
            ingestion_warnings: m.ingestion_warnings,
            ingestion_warning_text: m.ingestion_warning_text,
          })
        }
      }
    }
    return matched
  }, [documents, searchQuery, contentMatchUuids, contentMatches])

  // Sort folders (by name only) and documents independently — folders always above documents
  const sortedFolders = useMemo(() => {
    const sorted = [...filteredFolders].sort((a, b) =>
      a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
    )
    return sort.direction === 'desc' && sort.column === 'name' ? sorted.reverse() : sorted
  }, [filteredFolders, sort])

  const sortedDocuments = useMemo(() => {
    const sorted = [...filteredDocuments].sort((a, b) => {
      switch (sort.column) {
        case 'name':
          return a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
        case 'modified': {
          const aTime = a.updated_at ? new Date(a.updated_at).getTime() : 0
          const bTime = b.updated_at ? new Date(b.updated_at).getTime() : 0
          return aTime - bTime
        }
        default:
          return 0
      }
    })
    return sort.direction === 'desc' ? sorted.reverse() : sorted
  }, [filteredDocuments, sort])

  const handleToggleSelect = useCallback((uuid: string) => {
    setSelectedUuids(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }, [setSelectedUuids])

  const handleToggleAll = useCallback(() => {
    const allUuids = [...filteredFolders.map(f => f.uuid), ...filteredDocuments.map(d => d.uuid)]
    setSelectedUuids(prev => {
      const allSelected = allUuids.every(u => prev.has(u))
      return allSelected ? new Set() : new Set(allUuids)
    })
  }, [filteredFolders, filteredDocuments, setSelectedUuids])

  const handleBulkDelete = useCallback(async () => {
    if (selectedUuids.size === 0) return
    const folderCount = [...selectedUuids].filter(u => folders.some(f => f.uuid === u)).length
    const fileCount = selectedUuids.size - folderCount
    const parts: string[] = []
    if (fileCount > 0) parts.push(`${fileCount} file${fileCount === 1 ? '' : 's'}`)
    if (folderCount > 0) parts.push(`${folderCount} folder${folderCount === 1 ? '' : 's'}`)
    const summary = parts.join(' and ')
    // Name what is about to go, and say what depends on it. "Delete 1 file?"
    // let a wrong selection through, and a file can be a knowledge-base
    // source, an extraction test case, or a workflow's fixed document
    // without anything here saying so.
    const selectedFolderNames = folders.filter(f => selectedUuids.has(f.uuid)).map(f => f.title)
    const selectedDocs = documents.filter(d => selectedUuids.has(d.uuid))
    const docUuids = selectedDocs.map(d => d.uuid)
    const names = [...selectedDocs.map(d => d.title), ...selectedFolderNames]
    const shownNames = names.slice(0, DELETE_NAME_CAP)
    const moreNames = names.length - shownNames.length
    const usage = docUuids.length > 0 ? await collectUsage(docUuids) : null
    const oneDoc = docUuids.length === 1
    const kbCount = usage ? usage.knowledge_bases.length : 0
    let removeFromKbs = kbCount > 0
    const ok = await confirm({
      title: `Delete ${summary}?`,
      message: (
        <>
          Are you sure you want to delete <strong>{shownNames.length > 0 ? shownNames.join(', ') : summary}</strong>{moreNames > 0 ? ` and ${moreNames} more` : ''}?
          {folderCount > 0 ? ' Folders will be removed along with everything inside them.' : ''} This cannot be undone.
          {usage === undefined && <UsageCheckFailedNote many={!oneDoc} />}
          {usage && usage.total > 0 && (
            <div style={{ marginTop: 8 }}>
              {oneDoc ? <><strong>{selectedDocs[0].title}</strong> is</> : 'These files are'} {summarizeUsage(usage)}.
              {' '}{describeDeleteEffects(usage, { many: !oneDoc, removeOffered: kbCount > 0 })}
              <UsageSummaryList usage={usage} />
              {kbCount > 0 && <RemoveFromKnowledgeBasesOption count={kbCount} onChange={v => { removeFromKbs = v }} />}
            </div>
          )}
        </>
      ),
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    setBulkDeleting(true)
    try {
      const targets = [...selectedUuids].map(uuid => ({ uuid, folder: folders.some(f => f.uuid === uuid) }))
      const outcomes = await Promise.allSettled(targets.map(async target => {
        const result = target.folder
          ? await deleteFolder(target.uuid)
          : await deleteFile(target.uuid, { removeFromKnowledgeBases: removeFromKbs })
        if (!result.ok) throw new Error('The server did not confirm deletion.')
        return result
      }))
      const failed = targets.filter((_, index) => outcomes[index].status === 'rejected')
      const fileResults = outcomes.flatMap((outcome, index) => outcome.status === 'fulfilled' && !targets[index].folder ? [outcome.value as DeleteFileResult] : [])
      const kept = keptKnowledgeBasesMessage(fileResults)
      if (kept) toast(kept, 'info')
      // Keep failed items selected so retry targets only those items. Wait for
      // every request before reconciling; a fast failure must not hide siblings.
      setSelectedUuids(new Set(failed.map(target => target.uuid)))
      if (failed.length) {
        const failedNames = failed.map(target => [...documents, ...folders].find(item => item.uuid === target.uuid)?.title || target.uuid)
        const firstFailure = outcomes.find(outcome => outcome.status === 'rejected') as PromiseRejectedResult
        const reason = firstFailure.reason instanceof Error ? firstFailure.reason.message : 'Please try again.'
        toast(`${targets.length - failed.length} deleted; ${failed.length} could not be deleted: ${failedNames.slice(0, 3).join(', ')}${failed.length > 3 ? '…' : ''}. ${reason} Failed items remain selected for retry.`, 'error')
      } else {
        toast(`Deleted ${summary}.`, 'success')
      }
    } finally {
      refresh()
      setBulkDeleting(false)
    }
  }, [selectedUuids, folders, documents, refresh, confirm, setSelectedUuids, toast])

  const handleDropFile = useCallback(async (fileUuid: string, folderUuid: string) => {
    try {
      await moveFile(fileUuid, folderUuid)
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : 'Failed to move file', 'error')
    }
    refresh()
  }, [refresh, toast])

  const handleBulkDownload = useCallback(() => {
    const docUuids = [...selectedUuids].filter(u => documents.some(d => d.uuid === u))
    if (docUuids.length === 0) return
    if (docUuids.length === 1) {
      downloadFile(docUuids[0])
    } else {
      downloadFilesAsZip(docUuids)
    }
  }, [selectedUuids, documents])

  // Context menu state
  const [usageTarget, setUsageTarget] = useState<{ uuid: string; title: string } | null>(null)
  const { openWorkflow, openExtraction, activateKB } = useWorkspace()
  const [contextMenu, setContextMenu] = useState<{
    x: number
    y: number
    type: 'folder' | 'doc'
    item: Folder | Document
  } | null>(null)

  // + Add dropdown
  const [addMenuOpen, setAddMenuOpen] = useState(false)
  const addMenuRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (addMenuRef.current && !addMenuRef.current.contains(e.target as Node)) {
        setAddMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Dialog state
  const [renameTarget, setRenameTarget] = useState<{
    type: 'folder' | 'doc'
    uuid: string
    name: string
  } | null>(null)
  const [showCreateFolder, setShowCreateFolder] = useState(false)
  const [createTeamFolder, setCreateTeamFolder] = useState(false)
  const [moveTarget, setMoveTarget] = useState<Folder | null>(null)
  const [moveFileTarget, setMoveFileTarget] = useState<{
    uuids: string[]
    names: string[]
    fromFolderId: string | null
  } | null>(null)

  // Panel-wide drag & drop
  const dragCounter = useRef(0)
  const [panelDragOver, setPanelDragOver] = useState(false)

  const handlePanelDragEnter = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current++
    if (e.dataTransfer.types.includes('Files')) setPanelDragOver(true)
  }, [])

  const handlePanelDragOver = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  }, [])

  const handlePanelDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current--
    if (dragCounter.current <= 0) {
      dragCounter.current = 0
      setPanelDragOver(false)
    }
  }, [])

  const handlePanelDrop = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current = 0
    setPanelDragOver(false)
    if (e.dataTransfer.files.length > 0) upload(e.dataTransfer.files)
  }, [upload])

  const handleFolderContextMenu = useCallback((folder: Folder, e: React.MouseEvent) => {
    setContextMenu({ x: e.clientX, y: e.clientY, type: 'folder', item: folder })
  }, [])

  const handleDocContextMenu = useCallback((doc: Document, e: React.MouseEvent) => {
    setContextMenu({ x: e.clientX, y: e.clientY, type: 'doc', item: doc })
  }, [])

  const handleRename = useCallback(
    async (newName: string) => {
      if (!renameTarget) return
      if (renameTarget.type === 'doc') {
        await renameFile(renameTarget.uuid, newName)
      } else {
        await renameFolder(renameTarget.uuid, newName)
      }
      setRenameTarget(null)
      refresh()
    },
    [renameTarget, refresh],
  )

  const handleCreateFolder = useCallback(
    async (name: string) => {
      await createFolder({
        name,
        parent_id: currentFolder || '0',
        ...(createTeamFolder ? { folder_type: 'team' } : {}),
      })
      setShowCreateFolder(false)
      setCreateTeamFolder(false)
      refresh()
    },
    [currentFolder, createTeamFolder, refresh],
  )

  const handleMoveFolder = useCallback(
    async (parentId: string) => {
      if (!moveTarget) return
      await moveFolder(moveTarget.uuid, parentId)
      setMoveTarget(null)
      toast('Folder moved', 'success')
      refresh()
    },
    [moveTarget, refresh, toast],
  )

  const handleMoveFiles = useCallback(
    async (folderId: string) => {
      if (!moveFileTarget) return
      const results = await Promise.allSettled(
        moveFileTarget.uuids.map(uuid => moveFile(uuid, folderId)),
      )
      const failedUuids = moveFileTarget.uuids.filter((_, index) => results[index].status === 'rejected')
      const succeeded = new Set(moveFileTarget.uuids.filter(uuid => !failedUuids.includes(uuid)))
      setSelectedUuids(previous => new Set([...previous].filter(uuid => !succeeded.has(uuid))))
      refresh()
      if (failedUuids.length) {
        const names = moveFileTarget.uuids.flatMap((uuid, index) => failedUuids.includes(uuid) ? [moveFileTarget.names[index]] : [])
        setMoveFileTarget({ ...moveFileTarget, uuids: failedUuids, names })
        throw new Error(`${succeeded.size} moved; ${failedUuids.length} could not be moved. Only the remaining files will be retried: ${names.slice(0, 3).join(', ')}${names.length > 3 ? '…' : ''}. Choose a destination to retry.`)
      }
      toast(`${succeeded.size} file${succeeded.size === 1 ? '' : 's'} moved`, 'success')
      setMoveFileTarget(null)
    },
    [moveFileTarget, refresh, toast, setSelectedUuids],
  )

  const handleDelete = useCallback(
    async (type: 'folder' | 'doc', uuid: string) => {
      const item = type === 'folder'
        ? folders.find(f => f.uuid === uuid)
        : documents.find(d => d.uuid === uuid)
      const name = (item as { name?: string; title?: string } | undefined)?.name
        || (item as { title?: string } | undefined)?.title
        || (type === 'folder' ? 'this folder' : 'this file')
      // Say what depends on a document before it goes, and what deleting does
      // to each: a knowledge base keeps answering from its copy unless the
      // user also removes it there. `undefined` means the check failed; the
      // dialog says so rather than passing it off as "used nowhere".
      const usage: UsageGroups | null | undefined = type === 'doc' ? await collectUsage([uuid]) : null
      const kbCount = usage ? usage.knowledge_bases.length : 0
      let removeFromKbs = kbCount > 0
      const ok = await confirm({
        title: type === 'folder' ? 'Delete folder?' : 'Delete file?',
        message: type === 'folder' ? (
          <>
            Are you sure you want to delete <strong>{name}</strong> and everything inside it? This cannot be undone.
          </>
        ) : usage && usage.total > 0 ? (
          <>
            <strong>{name}</strong> is {summarizeUsage(usage)}. {describeDeleteEffects(usage, { removeOffered: kbCount > 0 })} This cannot be undone.
            <UsageSummaryList usage={usage} />
            {kbCount > 0 && <RemoveFromKnowledgeBasesOption count={kbCount} onChange={v => { removeFromKbs = v }} />}
          </>
        ) : (
          <>
            Are you sure you want to delete <strong>{name}</strong>? This cannot be undone.
            {usage === undefined && <UsageCheckFailedNote />}
          </>
        ),
        confirmLabel: 'Delete',
        destructive: true,
      })
      if (!ok) return
      try {
        if (type === 'doc') {
          const kept = keptKnowledgeBasesMessage([await deleteFile(uuid, { removeFromKnowledgeBases: removeFromKbs })])
          if (kept) toast(kept, 'info')
        } else {
          await deleteFolder(uuid)
        }
      } catch (err: unknown) {
        toast(err instanceof Error ? err.message : `Failed to delete ${type}`, 'error')
      }
      refresh()
    },
    [refresh, folders, documents, confirm, toast],
  )

  if (loading && documents.length === 0 && folders.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <div role="status" aria-label="Loading documents">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-highlight border-t-transparent" />
        </div>
      </div>
    )
  }

  return (
    <div
      className="file-browser"
      style={{ padding: '0 24px 32px' }}
      onDragEnter={handlePanelDragEnter}
      onDragOver={handlePanelDragOver}
      onDragLeave={handlePanelDragLeave}
      onDrop={handlePanelDrop}
    >
      <WorkspaceSectionHeader title="Files" actions={<>{searchAction}
      <div ref={addMenuRef} className="relative inline-block">
        <button
          type="button"
          onClick={() => setAddMenuOpen(!addMenuOpen)}
          aria-expanded={addMenuOpen}
          aria-haspopup="menu"
          className="flex items-center gap-1 rounded-[var(--ui-radius)] bg-highlight text-highlight-text px-3 py-1.5 text-sm font-bold hover:brightness-90 transition-all"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <Plus className="h-4 w-4" />
          Add
        </button>

        {addMenuOpen && (
          <div
            role="menu"
            aria-label="Add"
            onKeyDown={(e) => { if (e.key === 'Escape') setAddMenuOpen(false) }}
            className="absolute right-0 z-[1000] mt-2 min-w-[180px] rounded-lg border bg-white p-1.5"
            style={{
              borderColor: 'rgba(0,0,0,.15)',
              boxShadow: '0 8px 24px rgba(0,0,0,.12)',
            }}
          >
            <button
              role="menuitem"
              type="button"
              onClick={() => {
                setShowCreateFolder(true)
                setAddMenuOpen(false)
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
            >
              <FolderIcon className="h-4 w-4 shrink-0 text-[#a2a2a2]" style={{ width: 18 }} />
              <span>New Folder</span>
            </button>
            <button
              role="menuitem"
              type="button"
              onClick={() => {
                setCreateTeamFolder(true)
                setShowCreateFolder(true)
                setAddMenuOpen(false)
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
            >
              <FolderIcon className="h-4 w-4 shrink-0 text-[rgb(0,128,128)]" style={{ width: 18 }} />
              <span>New Team Folder</span>
            </button>
            <button
              role="menuitem"
              type="button"
              onClick={() => {
                fileInputRef.current?.click()
                setAddMenuOpen(false)
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-3.5 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] transition-colors"
            >
              <Upload className="h-4 w-4 shrink-0" style={{ width: 18 }} />
              <span>Upload Files</span>
            </button>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          multiple
          aria-label="Upload files"
          accept={SUPPORTED_ACCEPT_ATTR}
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) upload(e.target.files)
            e.target.value = ''
          }}
        />
      </div>
      </>}>{searchField}</WorkspaceSectionHeader>
      <UploadZone onFilesSelected={(files) => upload(files)} highlighted={panelDragOver} />
      <UploadProgress uploads={uploads} onDismiss={dismissUpload} />

      {/* Breadcrumbs - matches Flask _breadcrumbs.html */}
      <Breadcrumbs
        items={displayBreadcrumbs}
        onNavigate={setCurrentFolder}
        floor={rootFolder}
        homeLabel={rootFolder ? (rootLabel ?? 'Project') : 'Home'}
        onDropFile={handleDropFile}
      />

      {/* Bulk action toolbar */}
      {selectedUuids.size > 0 && (
        <div
          role="group" aria-label="Selected files and bulk actions"
          className="mt-2.5 flex flex-wrap items-center gap-2 rounded-lg px-3 py-2"
          style={{ backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)', border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, white)' }}
        >
          <span className="text-sm font-medium" style={{ color: '#374151' }}>
            {selectedUuids.size} selected
          </span>
          <div className="ml-auto flex max-w-full flex-wrap items-center gap-2">
            <button
              onClick={handleBulkDownload}
              disabled={![...selectedUuids].some(u => documents.some(d => d.uuid === u))}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Download className="h-3.5 w-3.5" />
              Download
            </button>
            <button
              onClick={() => {
                const docs = documents.filter(d => selectedUuids.has(d.uuid))
                if (docs.length === 0) return
                setMoveFileTarget({
                  uuids: docs.map(d => d.uuid),
                  names: docs.map(d => d.title),
                  fromFolderId: currentFolder,
                })
              }}
              disabled={![...selectedUuids].some(u => documents.some(d => d.uuid === u))}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <FolderInput className="h-3.5 w-3.5" />
              Move
            </button>
            <button
              onClick={handleBulkDelete}
              disabled={bulkDeleting}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium border border-red-200 bg-red-50 text-red-700 hover:bg-red-100 disabled:opacity-50 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {bulkDeleting ? 'Deleting...' : 'Delete'}
            </button>
            <button
              onClick={() => setSelectedUuids(new Set())}
              className="text-xs text-gray-500 hover:text-gray-700 px-1.5"
            >
              Clear selection
            </button>
          </div>
        </div>
      )}

      {contentSearchState === 'error' && <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Content search is unavailable. Name matches from this folder remain available. <button onClick={onRetryContentSearch} className="ml-2 rounded border border-red-300 px-2 py-1 underline">Retry search</button></div>}
      {contentsError && <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Could not load this folder. {documents.length || folders.length ? 'Previously loaded items are shown.' : 'Its contents are unavailable.'} <button onClick={() => refresh()} className="ml-2 rounded border border-red-300 px-2 py-1 underline">Retry folder</button></div>}
      {/* File table - matches Flask .styled-table */}
      <div
        className="mt-2.5 rounded-[12px] overflow-hidden"
        style={{ boxShadow: '0 0 20px rgba(0, 0, 0, 0.15)' }}
      >
        {contentsError && !documents.length && !folders.length ? null : searchQuery.trim() && !sortedFolders.length && !sortedDocuments.length ? <p role="status" className="p-6 text-sm text-gray-600">{contentSearchState === 'loading' ? 'Searching document contents…' : contentSearchState === 'error' ? 'No matching names in this folder. Retry content search above, or change the search.' : <>No files or folders match “{searchQuery}”. Change the search or use Close search to see this folder again.</>}</p> : currentFolder && !sortedFolders.length && !sortedDocuments.length ? <p role="status" className="p-6 text-sm text-gray-600">This folder is empty. Upload files here or use Add to create a folder.</p> : <FileList
          folders={sortedFolders}
          documents={sortedDocuments}
          onFolderClick={setCurrentFolder}
          onFolderContextMenu={handleFolderContextMenu}
          onDocContextMenu={handleDocContextMenu}
          onDocClick={onDocClick}
          selectedUuids={selectedUuids}
          onToggleSelect={handleToggleSelect}
          onToggleAll={handleToggleAll}
          snippets={searchQuery.trim() ? snippetMap : undefined}
          onDropFile={handleDropFile}
          highlighted={panelDragOver}
          sort={sort}
          onSort={handleSort}
          watchedFolderUuids={watchedFolderUuids}
        />}
      </div>

      {usageTarget && (
        <DocumentUsageDialog
          docUuid={usageTarget.uuid}
          docTitle={usageTarget.title}
          onClose={() => setUsageTarget(null)}
          onOpenWorkflow={(id) => openWorkflow(id)}
          onOpenExtraction={(uuid) => openExtraction(uuid)}
          onOpenKnowledgeBase={(uuid, title) => activateKB(uuid, title)}
        />
      )}

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          onAskFolder={
            contextMenu.type === 'folder' && onAskAboutFolder
              ? () => onAskAboutFolder(contextMenu.item as Folder)
              : undefined
          }
          onRunWorkflow={
            contextMenu.type === 'folder' && onRunWorkflowOnFolder
              ? () => onRunWorkflowOnFolder(contextMenu.item as Folder)
              : undefined
          }
          onAddToKB={
            contextMenu.type === 'folder' && onAddFolderToKB
              ? () => onAddFolderToKB(contextMenu.item as Folder)
              : undefined
          }
          onRename={() => {
            const item = contextMenu.item
            setRenameTarget({
              type: contextMenu.type,
              uuid: item.uuid,
              name: item.title,
            })
          }}
          onMove={
            contextMenu.type === 'folder'
              ? !(contextMenu.item as Folder).is_shared_team_root
                ? () => setMoveTarget(contextMenu.item as Folder)
                : undefined
              : () => {
                  const doc = contextMenu.item as Document
                  setMoveFileTarget({
                    uuids: [doc.uuid],
                    names: [doc.title],
                    fromFolderId: doc.folder,
                  })
                }
          }
          onExport={
            contextMenu.type === 'folder'
              ? async () => {
                  const folder = contextMenu.item as Folder
                  try {
                    await exportFolder(folder.uuid, folder.title)
                  } catch (err: unknown) {
                    toast(err instanceof Error ? err.message : 'Failed to export folder', 'error')
                  }
                }
              : undefined
          }
          onDelete={() => handleDelete(contextMenu.type, contextMenu.item.uuid)}
          onDownload={
            contextMenu.type === 'doc'
              ? () => {
                  downloadFile(contextMenu.item.uuid)
                }
              : undefined
          }
          onCopyUuid={() => {
            navigator.clipboard.writeText(contextMenu.item.uuid)
          }}
          onShowUsage={
            contextMenu.type === 'doc'
              ? () => setUsageTarget({ uuid: contextMenu.item.uuid, title: contextMenu.item.title })
              : undefined
          }
          onConvertToTeam={
            contextMenu.type === 'folder' && currentTeam && !(contextMenu.item as Folder).team_id
              ? async () => {
                  try {
                    await convertFolderToTeam(contextMenu.item.uuid)
                    refresh()
                  } catch (err: unknown) {
                    toast(err instanceof Error ? err.message : 'Failed to convert folder', 'error')
                  }
                }
              : undefined
          }
        />
      )}

      {renameTarget && (
        <RenameDialog
          currentName={renameTarget.name}
          onSubmit={handleRename}
          onClose={() => setRenameTarget(null)}
        />
      )}

      {showCreateFolder && (
        <CreateFolderDialog
          onSubmit={handleCreateFolder}
          onClose={() => { setShowCreateFolder(false); setCreateTeamFolder(false) }}
          title={createTeamFolder ? 'New Team Folder' : 'New Folder'}
        />
      )}

      {moveTarget && (
        <MoveFolderDialog
          folder={moveTarget}
          onSubmit={handleMoveFolder}
          onClose={() => setMoveTarget(null)}
        />
      )}

      {moveFileTarget && (
        <MoveFileDialog
          fileNames={moveFileTarget.names}
          currentFolderId={moveFileTarget.fromFolderId}
          onSubmit={handleMoveFiles}
          onClose={() => setMoveFileTarget(null)}
        />
      )}
    </div>
  )
}
