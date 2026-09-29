import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { FocusTrap } from 'focus-trap-react'
import { useAuth } from '../../hooks/useAuth'
import { useTeams } from '../../hooks/useTeams'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useToast } from '../../contexts/ToastContext'
import { useLibraries, useLibraryItems } from '../../hooks/useLibrary'
import { LibraryItemRow } from '../library/LibraryItemRow'
import { ExploreTab } from '../library/ExploreTab'
import { OrganizationHelp } from '../library/OrganizationHelp'
import { ShareWithTeamDialog } from '../library/ShareWithTeamDialog'
import { useConfirm } from '../shared/useConfirm'

const KIND_LABEL: Record<string, string> = {
  workflow: 'workflow',
  search_set: 'extraction',
  automation: 'automation',
}
import { cloneToPersonal, shareToTeam, addItem as addItemToLibrary, touchItem, listCollections } from '../../api/library'
import { ApiError } from '../../api/client'
import { MAX_NAME_LENGTH, getNameError, isDuplicateName, normalizeName } from '../../utils/nameValidation'
import { createWorkflow, importWorkflow } from '../../api/workflows'
import { createSearchSet, importSearchSet, listItems as listSearchSetItems, updateSearchSet, updateItem as updateSearchSetItem, addItem as addSearchSetItem } from '../../api/extractions'
import {
  Search,
  Layers,
  Star,
  Pin,
  Plus,
  Workflow,
  Filter,
  Terminal,
  Code,
  Folder,
  FolderOpen,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import type { LibraryItem, VerifiedCollection } from '../../types/library'
import { useLibraryFolders } from '../../hooks/useLibrary'

type ScopeTab = 'mine' | 'team' | 'explore'
type ViewFilter = 'all' | 'favorites' | 'pinned' | string  // string allows folder UUIDs
// Tasks/Prompts/Formatters are all stored as `search_set` items, distinguished
// by the underlying set_type. The filter chips split them out so each is
// browsable on its own (set_type defaults to 'extraction' when absent).
type KindFilter = 'all' | 'workflow' | 'extraction' | 'prompt' | 'formatter'

function matchesKindFilter(item: { kind: string; set_type: string | null }, filter: KindFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'workflow') return item.kind === 'workflow'
  if (item.kind !== 'search_set') return false
  return (item.set_type || 'extraction') === filter
}
const KIND_FILTERS = [
  { value: 'all', label: 'All types' },
  { value: 'workflow', label: 'Workflows' },
  { value: 'extraction', label: 'Extractions' },
  { value: 'prompt', label: 'Prompts' },
  { value: 'formatter', label: 'Formatters' },
] as const

type SortOption = 'recent' | 'az'

export function LibraryTab() {
  const { openWorkflow, openExtraction, sendChatMessage, selectedDocUuids, selectedFolderUuids, openWorkflowId, openExtractionId, openAutomationId } = useWorkspace()
  const { toast } = useToast()
  const confirm = useConfirm()
  const { user } = useAuth()
  const teamId = user?.current_team ?? undefined
  const { teams } = useTeams()
  const { libraries, loading: libLoading, error, refresh } = useLibraries(teamId)

  const [scope, setScope] = useState('mine' as ScopeTab)
  const [search, setSearch] = useState('')
  const [mobileViewsOpen, setMobileViewsOpen] = useState(false)
  const [viewFilter, setViewFilter] = useState<ViewFilter>('all')
  const [kindFilter, setKindFilter] = useState<KindFilter>('all')
  const [sortOption, setSortOption] = useState<SortOption>('recent')
  const [newMenuOpen, setNewMenuOpen] = useState(false)
  const newMenuRef = useRef<HTMLDivElement>(null)

  // Resizable sidebar — width persists across sessions via localStorage.
  const SIDEBAR_MIN = 148
  const SIDEBAR_MAX = 420
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const stored = Number(localStorage.getItem('library:sidebarWidth'))
    return stored >= SIDEBAR_MIN && stored <= SIDEBAR_MAX ? stored : SIDEBAR_MIN
  })
  const [resizing, setResizing] = useState(false)
  useEffect(() => {
    if (!resizing) return
    const onMove = (e: MouseEvent) => {
      const next = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, e.clientX - sidebarLeftRef.current))
      setSidebarWidth(next)
    }
    const onUp = () => setResizing(false)
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    // Stop text selection / cursor flicker while dragging.
    const prevUserSelect = document.body.style.userSelect
    const prevCursor = document.body.style.cursor
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = prevUserSelect
      document.body.style.cursor = prevCursor
    }
  }, [resizing])
  useEffect(() => {
    localStorage.setItem('library:sidebarWidth', String(sidebarWidth))
  }, [sidebarWidth])
  const sidebarRef = useRef<HTMLDivElement>(null)
  const sidebarLeftRef = useRef(0)

  // Folder system
  const folderScope = scope === 'team' ? 'team' : 'personal'
  const { folders, loading: foldersLoading, error: foldersError, refresh: refreshFolders, create: createFolder, rename: renameFolder, remove: removeFolder, moveItems: moveFolderItems } = useLibraryFolders(folderScope, teamId)
  const [folderMenuOpen, setFolderMenuOpen] = useState<string | null>(null)
  const [folderMenuPos, setFolderMenuPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 }) // folder uuid with open menu
  const [renamingFolder, setRenamingFolder] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [newFolderMode, setNewFolderMode] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const folderMenuRef = useRef<HTMLDivElement>(null)
  const folderMenuTrigger = useRef<HTMLButtonElement>(null)
  const [folderSaving, setFolderSaving] = useState(false)
  const folderSavingRef = useRef(false)
  const [folderSaveError, setFolderSaveError] = useState<string | null>(null)
  const currentScope = useRef(`${scope}:${teamId}`)
  currentScope.current = `${scope}:${teamId}`
  const submitFolder = async (uuid?: string) => {
    const name = normalizeName(uuid ? renameValue : newFolderName)
    if (!name || folderSavingRef.current) return
    const scopeAtStart = currentScope.current
    folderSavingRef.current = true; setFolderSaving(true); setFolderSaveError(null)
    try {
      if (uuid) await renameFolder(uuid, name)
      else await createFolder(name)
      if (currentScope.current !== scopeAtStart) return
      setRenamingFolder(null); setNewFolderMode(false); setNewFolderName('')
    } catch (reason) {
      if (currentScope.current === scopeAtStart) setFolderSaveError(reason instanceof Error ? reason.message : 'Could not save this folder.')
    } finally { folderSavingRef.current = false; setFolderSaving(false) }
  }

  // Collections (Explore tab)
  const [collections, setCollections] = useState<VerifiedCollection[]>([])

  // Fetch collections when Explore tab is active
  useEffect(() => {
    if (scope !== 'explore') { setCollections([]); return }
    listCollections()
      .then(data => setCollections(data.collections))
      .catch(() => {})
  }, [scope])

  // Close + New menu on outside click
  useEffect(() => {
    if (!newMenuOpen) return
    const handler = (e: MouseEvent) => {
      if (newMenuRef.current && !newMenuRef.current.contains(e.target as Node)) {
        setNewMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [newMenuOpen])

  // Close folder context menu on outside click
  useEffect(() => {
    if (!folderMenuOpen) return
    folderMenuRef.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const handler = (e: MouseEvent) => {
      if (folderMenuRef.current && !folderMenuRef.current.contains(e.target as Node)) {
        setFolderMenuOpen(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [folderMenuOpen])

  // Reset folder view when scope changes
  useEffect(() => {
    setViewFilter(current => ['all', 'favorites', 'pinned'].includes(current) ? current : 'all')
    setFolderMenuOpen(null)
    setRenamingFolder(null)
    setNewFolderMode(false)
    setFolderSaveError(null)
  }, [scope, teamId])

  // Find the library matching current scope
  const activeLibrary =
    scope === 'mine'
      ? libraries.find((l) => l.scope === 'personal') ?? null
      : scope === 'team'
        ? libraries.find((l) => l.scope === 'team') ?? null
        : libraries.find((l) => l.scope === 'verified') ?? null

  // Items — pass folder filter when a folder is selected
  const isCollectionFilter = viewFilter.startsWith('collection:')
  const selectedFolder = viewFilter !== 'all' && viewFilter !== 'favorites' && viewFilter !== 'pinned' && !isCollectionFilter ? viewFilter : undefined
  const { items, loading: itemsLoading, error: itemsError, refresh: refreshItems, update, remove } = useLibraryItems(
    activeLibrary?.id ?? null,
    {
      // Kind is filtered client-side so we can show per-kind counts on the filter chips.
      search: search.trim() || undefined,
      folder: selectedFolder,
    },
  )
  const hasActiveFilters = Boolean(search || viewFilter !== 'all' || kindFilter !== 'all')

  // The tab stays mounted (hidden) while a workflow/extraction/automation
  // editor is open in the right panel, so filters and search survive the
  // round-trip — but edits made in the editor (renames, deletes) won't be
  // reflected here. Refetch when the editor closes.
  const editorOpen = Boolean(openWorkflowId || openExtractionId || openAutomationId)
  const prevEditorOpen = useRef(editorOpen)
  useEffect(() => {
    if (prevEditorOpen.current && !editorOpen) {
      refreshItems()
      refreshFolders()
    }
    prevEditorOpen.current = editorOpen
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorOpen])

  // Delete-choice dialog: set when the user can permanently delete the
  // underlying workflow/extraction (not just remove the bookmark).
  const [deleteTarget, setDeleteTarget] = useState<LibraryItem | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [itemAction, setItemAction] = useState<{ scope: string; label: string; pending: boolean; error: string | null; retry: () => void } | null>(null)
  const itemActionBusy = useRef(false)
  const performItemAction = async (itemId: string, verb: string, action: () => Promise<unknown>) => {
    if (itemActionBusy.current) return
    const actionScope = currentScope.current
    const label = `${verb}: ${items.find(item => item.id === itemId)?.name || 'Library item'}`
    const retry = () => { void performItemAction(itemId, verb, action) }
    itemActionBusy.current = true
    setItemAction({ scope: actionScope, label, pending: true, error: null, retry })
    try {
      await action()
      if (currentScope.current === actionScope) setItemAction({ scope: actionScope, label, pending: false, error: null, retry })
    } catch (reason) {
      if (currentScope.current === actionScope) setItemAction({ scope: actionScope, label, pending: false, error: reason instanceof Error ? reason.message : 'Could not update this item.', retry })
    } finally { itemActionBusy.current = false }
  }

  // Actions
  const handlePin = async (itemId: string, pinned: boolean) => {
    await performItemAction(itemId, pinned ? 'Pin item' : 'Unpin item', () => update(itemId, { pinned }))
  }
  const handleFavorite = async (itemId: string, favorited: boolean) => {
    await performItemAction(itemId, favorited ? 'Favorite item' : 'Unfavorite item', () => update(itemId, { favorited }))
  }
  const handleClone = async (itemId: string) => {
    await performItemAction(itemId, 'Copy to My Library', async () => { await cloneToPersonal(itemId); await refreshItems() })
  }
  const [shareDialogItem, setShareDialogItem] = useState<{ id: string; name: string } | null>(null)
  const handleShare = (itemId: string) => {
    if (teams.length === 0) {
      toast('Join or create a team before sharing items.', 'info')
      return
    }
    const item = items.find((i) => i.id === itemId)
    setShareDialogItem({ id: itemId, name: item?.name ?? 'this item' })
  }
  // The dialog lets the user pick any team they belong to (default: current
  // team), so the destination is always shown and never assumed.
  const confirmShare = async (comment: string, destTeamId?: string) => {
    const targetTeamId = destTeamId ?? teamId
    if (!shareDialogItem || !targetTeamId) return
    const { id, name } = shareDialogItem
    const teamName = teams.find((t) => t.id === targetTeamId)?.name ?? 'the team'
    setShareDialogItem(null)
    try {
      await shareToTeam(id, targetTeamId, comment || undefined)
      toast(`Shared to ${teamName}'s library`, 'success')
      refreshItems()
    } catch (err) {
      // 409: this item was already shared to the team — re-sharing would
      // create an independent duplicate, so ask before forcing it.
      if (err instanceof ApiError && err.status === 409) {
        const ok = await confirm({
          title: 'Already shared to team',
          message: (
            <>
              <strong>{name}</strong> is already in {teamName}'s library. Sharing again
              creates a separate copy that can be edited independently of the first.
            </>
          ),
          confirmLabel: 'Share a copy',
        })
        if (!ok) return
        try {
          await shareToTeam(id, targetTeamId, comment || undefined, true)
          toast(`Shared a new copy to ${teamName}'s library`, 'success')
          refreshItems()
        } catch (err2) {
          const msg = err2 instanceof ApiError ? err2.message : 'Failed to share to team'
          toast(msg, 'error')
        }
        return
      }
      const msg = err instanceof ApiError ? err.message : 'Failed to share to team'
      toast(msg, 'error')
    }
  }
  // Prompts/formatters are search_set items — label them by set_type.
  const itemKindLabel = (item: { kind: string; set_type: string | null }) =>
    item.kind === 'search_set' ? (item.set_type || 'extraction') : (KIND_LABEL[item.kind] ?? 'item')

  const handleRemove = async (itemId: string) => {
    const item = items.find((i) => i.id === itemId)
    // Removing a bookmark leaves the underlying workflow/extraction alive (and
    // its name reserved). When the user may delete the real object, open the
    // choice dialog; otherwise be honest that only the bookmark goes away.
    if (item?.can_delete_underlying) {
      setDeleteTarget(item)
      return
    }
    const kindLabel = item ? itemKindLabel(item) : 'item'
    const ok = await confirm({
      title: `Remove ${kindLabel} from library?`,
      message: (
        <>
          Remove <strong>{item?.name ?? 'this item'}</strong> from this library? Only the
          bookmark is removed — the {kindLabel} itself is kept by its owner.
        </>
      ),
      confirmLabel: 'Remove',
      destructive: true,
    })
    if (!ok) return
    try {
      await remove(itemId)
      refreshFolders()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Failed to remove from library', 'error')
    }
  }

  const handleDeleteChoice = async (deleteUnderlying: boolean) => {
    if (!deleteTarget || deleting) return
    const { id, name } = deleteTarget
    const kindLabel = itemKindLabel(deleteTarget)
    setDeleting(true)
    try {
      await remove(id, deleteUnderlying ? { deleteUnderlying: true } : undefined)
      setDeleteTarget(null)
      refreshFolders()
      toast(
        deleteUnderlying
          ? `Deleted "${name}" permanently`
          : `Removed "${name}" from library — the ${kindLabel} itself was kept`,
        'success',
      )
    } catch (err) {
      toast(err instanceof ApiError ? err.message : `Failed to delete ${kindLabel}`, 'error')
    } finally {
      setDeleting(false)
    }
  }
  const handleMoveToFolder = async (itemId: string, folderUuid: string | null) => {
    await performItemAction(itemId, folderUuid ? `Move to ${folders.find(folder => folder.uuid === folderUuid)?.name || 'folder'}` : 'Remove from folder', async () => {
      await moveFolderItems([itemId], folderUuid)
      await Promise.all([refreshItems(), refreshFolders()])
    })
  }

  // Apply view filter + sort (folder filtering is handled server-side via useLibraryItems)
  const selectedCollection = isCollectionFilter
    ? collections.find(c => viewFilter === `collection:${c.id}`)
    : null
  const collectionItemIds = selectedCollection ? new Set(selectedCollection.item_ids) : null

  // In the default "All Items" view, an item that has been moved into a folder
  // belongs to that folder only — it should not also appear in the root list.
  // Favorites/Pinned and folder views are intentionally left untouched: the
  // first two span folders, and folder views are already server-side scoped.
  const scopedItems = viewFilter === 'all' && !search.trim() ? items.filter((i) => !i.folder) : items

  const filtered = scopedItems.filter((item) => {
    if (!matchesKindFilter(item, kindFilter)) return false
    if (viewFilter === 'favorites') return item.favorited
    if (viewFilter === 'pinned') return item.pinned
    if (collectionItemIds) return collectionItemIds.has(item.item_id)
    return true
  })

  const kindCounts = {
    all: scopedItems.length,
    workflow: scopedItems.filter((i) => matchesKindFilter(i, 'workflow')).length,
    extraction: scopedItems.filter((i) => matchesKindFilter(i, 'extraction')).length,
    prompt: scopedItems.filter((i) => matchesKindFilter(i, 'prompt')).length,
    formatter: scopedItems.filter((i) => matchesKindFilter(i, 'formatter')).length,
  }

  const sorted = [...filtered].sort((a, b) => {
    if (sortOption === 'az') return a.name.localeCompare(b.name)
    // Pinned first, then favorited
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    if (a.favorited !== b.favorited) return a.favorited ? -1 : 1
    // Then by most recently used/created (descending)
    const aTime = a.last_used_at || a.created_at || ''
    const bTime = b.last_used_at || b.created_at || ''
    if (aTime !== bTime) return bTime.localeCompare(aTime)
    return 0
  })

  // Creation modal state
  type ModalType = 'workflow' | 'extraction' | 'prompt' | 'formatter' | null
  const [createModalType, setCreateModalType] = useState<ModalType>(null)
  const [createName, setCreateName] = useState('')
  const [createDesc, setCreateDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const openCreateModal = (type: NonNullable<ModalType>) => {
    setCreateModalType(type)
    setCreateName('')
    setCreateDesc('')
    setCreateError(null)
  }

  const closeCreateModal = () => {
    setCreateModalType(null)
    setCreateName('')
    setCreateDesc('')
    setCreateError(null)
  }

  // Upload-from-JSON support inside the creation modal
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const handleUploadDefinition = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !createModalType) return
    setUploading(true)
    setCreateError(null)
    const personalLib = libraries.find((l) => l.scope === 'personal')
    try {
      if (createModalType === 'workflow') {
        const wf = await importWorkflow(file)
        if (personalLib) {
          await addItemToLibrary(personalLib.id, { item_id: wf.id, kind: 'workflow' })
        }
        closeCreateModal()
        refreshItems()
        openWorkflow(wf.id)
      } else {
        const ss = await importSearchSet(file)
        if (personalLib) {
          await addItemToLibrary(personalLib.id, { item_id: ss.id, kind: 'search_set' })
        }
        closeCreateModal()
        refreshItems()
        if (createModalType === 'extraction') {
          openExtraction(ss.uuid)
        }
      }
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : String(err))
    } finally {
      setUploading(false)
    }
  }

  // Preview/Edit modal state (prompts / formatters). A row click opens the
  // modal in 'preview' (read-only body + Use in Assistant); the row menu's
  // Edit opens straight to 'edit'.
  const [editingItem, setEditingItem] = useState<import('../../types/library').LibraryItem | null>(null)
  const [editMode, setEditMode] = useState<'preview' | 'edit'>('preview')
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [editItemId, setEditItemId] = useState<string | null>(null) // SearchSetItem ID
  const [editLoading, setEditLoading] = useState(false)
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [editLoadError, setEditLoadError] = useState<string | null>(null)
  const editLoadVersion = useRef(0)

  const openPromptModal = async (item: import('../../types/library').LibraryItem, mode: 'preview' | 'edit') => {
    const version = ++editLoadVersion.current
    setEditingItem(item)
    setEditMode(mode)
    setEditTitle(item.name)
    // Freshly created prompts keep their body in extraction_config.content
    // (surfaced as `description`); edited ones store it on
    // SearchSetItem.searchphrase. Show the description while the
    // authoritative searchphrase loads.
    setEditContent(item.description || '')
    setEditError(null)
    setEditLoadError(null)
    setEditItemId(null)
    if (item.item_uuid) {
      setEditLoading(true)
      try {
        const items = await listSearchSetItems(item.item_uuid)
        if (version !== editLoadVersion.current) return
        if (items.length > 0) {
          setEditItemId(items[0].id)
          if (items[0].searchphrase?.trim() || !(item.description || '').trim()) {
            setEditContent(items[0].searchphrase)
          }
        }
      } catch (reason) {
        if (version === editLoadVersion.current) setEditLoadError(reason instanceof Error ? reason.message : 'Could not load this item.')
      }
      if (version === editLoadVersion.current) setEditLoading(false)
    } else setEditLoading(false)
  }

  const closeEditModal = () => {
    if (editSaving) return
    editLoadVersion.current++
    setEditingItem(null)
    setEditTitle('')
    setEditContent('')
    setEditItemId(null)
    setEditError(null)
  }

  const markUsed = (libraryItemId: string) => {
    touchItem(libraryItemId).then(() => refreshItems()).catch(() => {})
  }

  const usePromptInAssistant = () => {
    if (!editingItem || editLoading || editLoadError) return
    const content = editContent.trim()
    if (!content) return
    markUsed(editingItem.id)
    const docs = selectedDocUuids
    const folderUuids = selectedFolderUuids
    closeEditModal()
    sendChatMessage(content, { documentUuids: docs, folderUuids })
  }

  const handleEditSave = async () => {
    if (!editingItem?.item_uuid || editLoading || editLoadError || editSaving) return
    const titleError = getNameError(editTitle, 'Title')
    if (titleError) {
      setEditError(titleError)
      return
    }
    const cleanTitle = normalizeName(editTitle)
    const editKind = (editingItem.set_type || 'extraction') as 'extraction' | 'prompt' | 'formatter'
    const siblingNames = items
      .filter((i) => i.id !== editingItem.id && matchesKindFilter(i, editKind))
      .map((i) => i.name)
    if (isDuplicateName(cleanTitle, siblingNames)) {
      setEditError(`You already have a ${editKind} named "${cleanTitle}". Choose a different name.`)
      return
    }
    setEditSaving(true)
    setEditError(null)
    try {
      await updateSearchSet(editingItem.item_uuid, { title: cleanTitle })
      if (editItemId) {
        await updateSearchSetItem(editItemId, { searchphrase: editContent, title: cleanTitle })
      } else {
        // Prompts created via the create modal don't have a SearchSetItem yet —
        // their body lives only in extraction_config.content. Materialize one so
        // the body persists through edits and is readable everywhere.
        await addSearchSetItem(editingItem.item_uuid, {
          searchphrase: editContent,
          title: cleanTitle,
        })
      }
      closeEditModal()
      refreshItems()
    } catch (e) {
      setEditError(e instanceof Error ? e.message : String(e))
    } finally {
      setEditSaving(false)
    }
  }

  const handleCreate = async () => {
    const nameError = getNameError(createName)
    if (nameError) {
      setCreateError(nameError)
      return
    }
    const cleanName = normalizeName(createName)
    if (createModalType && isDuplicateName(cleanName, items.filter((i) => matchesKindFilter(i, createModalType)).map((i) => i.name))) {
      setCreateError(`You already have a ${createModalType} named "${cleanName}". Choose a different name.`)
      return
    }
    setCreating(true)
    setCreateError(null)
    const personalLib = libraries.find((l) => l.scope === 'personal')
    try {
      if (createModalType === 'workflow') {
        const wf = await createWorkflow({ name: cleanName, description: createDesc.trim() || undefined })
        if (personalLib) {
          await addItemToLibrary(personalLib.id, { item_id: wf.id, kind: 'workflow' })
        }
        closeCreateModal()
        refreshItems()
        openWorkflow(wf.id)
      } else {
        // extraction, prompt, or formatter — all stored as SearchSets
        const config = createDesc.trim() ? { content: createDesc.trim() } : undefined
        const ss = await createSearchSet({ title: cleanName, set_type: createModalType ?? 'extraction', extraction_config: config })
        if (personalLib) {
          await addItemToLibrary(personalLib.id, { item_id: ss.id, kind: 'search_set' })
        }
        closeCreateModal()
        refreshItems()
        if (createModalType === 'extraction') {
          openExtraction(ss.uuid)
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      console.error('Failed to create item:', e)
      setCreateError(msg)
    } finally {
      setCreating(false)
    }
  }

  // Modal config per type
  const modalConfig: Record<NonNullable<ModalType>, { title: string; namePlaceholder: string; showDesc: boolean; descPlaceholder: string }> = {
    workflow: {
      title: 'Start a workflow',
      namePlaceholder: 'Name your workflow',
      showDesc: true,
      descPlaceholder: "A one sentence description of the workflow's purpose.",
    },
    extraction: {
      title: 'Name the extraction',
      namePlaceholder: 'Name your extraction',
      showDesc: false,
      descPlaceholder: '',
    },
    prompt: {
      title: 'Prompt creation',
      namePlaceholder: 'Title your prompt',
      showDesc: true,
      descPlaceholder: 'Write your prompt here',
    },
    formatter: {
      title: 'Formatter creation',
      namePlaceholder: 'Title your formatter',
      showDesc: true,
      descPlaceholder: 'Write your formatting instructions here',
    },
  }

  if (libLoading && !libraries.length) {
    return (
      <div className="flex items-center justify-center h-full" style={{ fontSize: 13, color: '#666' }}>
        Loading...
      </div>
    )
  }

  if (error && !libraries.length) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 gap-3" style={{ fontSize: 13, color: '#666' }}>
        <p>{error}</p>
        <button
          onClick={refresh}
          style={{
            borderRadius: 'var(--ui-radius, 12px)',
            background: 'var(--highlight-color, #eab308)',
            color: 'var(--highlight-text-color, #000)',
            padding: '6px 12px',
            fontSize: 13,
            fontWeight: 700,
            border: 'none',
            cursor: 'pointer',
          }}
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div
      className="library-workspace flex flex-col h-full"
      style={{
        position: 'relative',
        backgroundColor: '#fff',
        ['--library-highlight' as string]: 'var(--highlight-color, #eab308)',
        ['--library-highlight-ink' as string]: 'color-mix(in srgb, var(--library-highlight) 30%, #1f2937)',
        ['--library-highlight-soft' as string]: 'color-mix(in srgb, var(--library-highlight) 18%, #ffffff)',
        ['--library-highlight-muted' as string]: 'color-mix(in srgb, var(--library-highlight) 10%, #f8f9fa)',
      }}
    >
      {/* ── Header ── */}
      <div className="library-header"
        style={{
          flexShrink: 0,
          borderBottom: '1px solid #e0e0e0',
          backgroundColor: '#fff',
          padding: '14px 24px 6px 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}
      >
        {/* Row 1: Title + Search + New */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: '-0.02em', color: '#202124', whiteSpace: 'nowrap' }}>
            Library
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, justifyContent: 'flex-end', minWidth: 0 }}>
            {/* Search */}
            {scope !== 'explore' && <div style={{ position: 'relative', flex: 1, maxWidth: 400, minWidth: 0 }}>
              <Search
                style={{
                  position: 'absolute',
                  left: 12,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: 16,
                  height: 16,
                  color: '#5f6368',
                  pointerEvents: 'none',
                }}
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Search library"
                placeholder="Search library…"
                style={{
                  width: '100%',
                  background: '#f1f3f4',
                  border: '1px solid transparent',
                  borderRadius: 8,
                  padding: '8px 16px 8px 38px',
                  fontSize: 14,
                  outline: 'none',
                  transition: 'all 0.2s',
                  fontFamily: 'inherit',
                }}
                onFocus={(e) => {
                  e.currentTarget.style.background = '#fff'
                  e.currentTarget.style.borderColor = '#dadce0'
                  e.currentTarget.style.boxShadow = '0 1px 2px rgba(60,64,67,0.3), 0 1px 3px 1px rgba(60,64,67,0.15)'
                }}
                onBlur={(e) => {
                  e.currentTarget.style.background = '#f1f3f4'
                  e.currentTarget.style.borderColor = 'transparent'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              />
            </div>}

            {/* + New button with dropdown */}
            <div ref={newMenuRef} style={{ position: 'relative', flexShrink: 0 }}>
              <button
                onClick={() => setNewMenuOpen(!newMenuOpen)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  borderRadius: 30,
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  border: 'none',
                  padding: '6px 14px',
                  fontSize: 13,
                  fontWeight: 700,
                  color: 'var(--highlight-text-color, #000)',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  transition: 'filter 0.15s',
                }}
              >
                <Plus style={{ width: 14, height: 14 }} />
                New
              </button>

              {newMenuOpen && (
                <div
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 'calc(100% + 6px)',
                    zIndex: 1000,
                    minWidth: 220,
                    borderRadius: 'var(--ui-radius, 12px)',
                    border: '1px solid rgba(0,0,0,0.14)',
                    background: '#fff',
                    boxShadow: '0 10px 28px rgba(0,0,0,0.16)',
                    padding: 6,
                  }}
                >
                  <NewMenuItem icon={<Workflow style={{ width: 18, height: 18 }} />} label="New Workflow" onClick={() => { setNewMenuOpen(false); openCreateModal('workflow') }} />
                  <NewMenuItem icon={<Filter style={{ width: 18, height: 18 }} />} label="New Extraction" onClick={() => { setNewMenuOpen(false); openCreateModal('extraction') }} />
                  <NewMenuItem icon={<Terminal style={{ width: 18, height: 18 }} />} label="New Prompt" onClick={() => { setNewMenuOpen(false); openCreateModal('prompt') }} />
                  <NewMenuItem icon={<Code style={{ width: 18, height: 18 }} />} label="New Formatter" onClick={() => { setNewMenuOpen(false); openCreateModal('formatter') }} />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Row 2: Scope tabs */}
        <div className="library-scope-tabs" style={{ display: 'flex', gap: 0, marginTop: 2, marginBottom: 10 }}>
          {([
            { key: 'mine' as const, label: 'Mine' },
            { key: 'team' as const, label: 'Team' },
            { key: 'explore' as const, label: 'Explore' },
          ]).map(({ key, label }) => {
            const active = scope === key
            return (
              <button
                key={key}
                onClick={() => {
                  setScope(key)
                  setViewFilter('all')
                  setFolderMenuOpen(null)
                  setRenamingFolder(null)
                  setNewFolderMode(false)
                }}
                style={{
                  padding: '0 14px',
                  fontWeight: 500,
                  fontSize: 14,
                  fontFamily: 'inherit',
                  borderRadius: 0,
                  lineHeight: '1.2',
                  minHeight: 34,
                  background: 'none',
                  border: 'none',
                  borderBottom: active ? '2px solid var(--library-highlight, #eab308)' : '2px solid transparent',
                  color: active ? 'var(--library-highlight-ink, #665000)' : '#5f6368',
                  cursor: 'pointer',
                  transition: 'color 0.15s',
                  whiteSpace: 'nowrap',
                }}
              >
                {label}
              </button>
            )
          })}
        </div>

        {/* Row 3: Filter chips + sort (Explore has its own) */}
        <div className="library-filters" style={{ display: scope === 'explore' ? 'none' : 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, paddingBottom: 2 }}>
          <select className="library-kind-select" aria-label="Filter library by type" value={kindFilter} onChange={event => setKindFilter(event.target.value as KindFilter)}>
            {KIND_FILTERS.map(({ value, label }) => <option key={value} value={value}>{label} ({kindCounts[value]})</option>)}
          </select>
          <div className="library-kind-chips" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {KIND_FILTERS.map(({ value, label }) => {
              const active = kindFilter === value
              const count = kindCounts[value]
              return (
                <button
                  key={value}
                  onClick={() => setKindFilter(value)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    height: 32,
                    padding: '0 12px',
                    borderRadius: 16,
                    border: active ? '1px solid var(--library-highlight-soft)' : '1px solid #dadce0',
                    backgroundColor: active ? 'var(--library-highlight-soft)' : '#fff',
                    fontSize: 13,
                    fontFamily: 'inherit',
                    color: active ? 'var(--library-highlight-ink)' : '#3c4043',
                    cursor: 'pointer',
                    userSelect: 'none',
                    transition: 'all 0.15s',
                  }}
                >
                  <span>{label}</span>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 500,
                      color: active ? 'var(--library-highlight-ink)' : '#666',
                      opacity: active ? 0.85 : 1,
                    }}
                  >
                    {count}
                  </span>
                </button>
              )
            })}
          </div>
          <div style={{ flexShrink: 0, display: 'flex', justifyContent: 'flex-end', minWidth: 150 }}>
            <select
              aria-label="Sort library items"
              value={sortOption}
              onChange={(e) => setSortOption(e.target.value as SortOption)}
              style={{
                borderRadius: 999,
                fontSize: 13,
                fontFamily: 'inherit',
                padding: '0 32px 0 12px',
                height: 32,
                border: '1px solid #dadce0',
                background: '#fff',
                color: '#3c4043',
                cursor: 'pointer',
              }}
            >
              <option value="recent">Recently Used</option>
              <option value="az">A-Z</option>
            </select>
          </div>
        </div>
      </div>

      {/* ── Body: Explore has its own view; mine/team keep sidebar + results ── */}
      {scope === 'explore' ? (
        <div style={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0, overflow: 'hidden' }}>
          <ExploreTab />
        </div>
      ) : (
      <div className="library-body" style={{ display: 'flex', flexGrow: 1, minHeight: 0, overflow: 'hidden' }}>
        <button type="button" className="library-views-toggle" aria-expanded={mobileViewsOpen} aria-controls="library-saved-views" onClick={() => setMobileViewsOpen(open => !open)}>{mobileViewsOpen ? 'Close views & folders' : `View: ${viewFilter === 'all' ? 'All items' : viewFilter === 'favorites' ? 'Favorites' : viewFilter === 'pinned' ? 'Pinned' : 'Folder'} · Change`}</button>
        {/* Sidebar */}
        <div
          ref={sidebarRef}
          id="library-saved-views"
          className="library-sidebar"
          data-open={mobileViewsOpen}
          style={{
            width: sidebarWidth,
            flexShrink: 0,
            minHeight: 0,
            borderRight: '1px solid #f0f0f0',
            backgroundColor: '#fafafa',
            padding: '14px 0',
            overflowY: 'auto',
          }}
        >
          {/* Saved Views */}
          <div
            style={{
              padding: '0 12px',
              marginBottom: 6,
              fontSize: 10,
              fontWeight: 700,
              textTransform: 'uppercase',
              color: '#666',
              letterSpacing: '0.5px',
            }}
          >
            Saved Views
          </div>

          {([
            { view: 'all' as const, icon: Layers, label: 'All Items' },
            { view: 'favorites' as const, icon: Star, label: 'Favorites' },
            { view: 'pinned' as const, icon: Pin, label: 'Pinned' },
          ]).map(({ view, icon: Icon, label }) => {
            const isActive = viewFilter === view
            const count =
              view === 'favorites'
                ? items.filter((i) => i.favorited).length
                : view === 'pinned'
                  ? items.filter((i) => i.pinned).length
                  : 0
            return (
              <button
                type="button"
                key={view}
                aria-pressed={isActive}
                onClick={() => { setViewFilter(view); setMobileViewsOpen(false) }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  width: '100%', border: 0, textAlign: 'left', fontFamily: 'inherit',
                  padding: '10px 10px 10px 12px',
                  cursor: 'pointer',
                  fontSize: 12,
                  fontWeight: isActive ? 600 : 500,
                  color: isActive ? 'var(--library-highlight-ink)' : '#4a4a4a',
                  backgroundColor: isActive ? 'var(--library-highlight-soft)' : 'transparent',
                  borderLeft: isActive ? '3px solid var(--library-highlight)' : '3px solid transparent',
                  transition: 'background 0.1s',
                }}
              >
                <Icon style={{ width: 13, height: 13, marginRight: 7, flexShrink: 0 }} />
                <span style={{ flex: 1 }}>{label}</span>
                {count > 0 && (
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: '#6b7280', fontWeight: 400 }}>{count}</span>
                )}
              </button>
            )
          })}

          <OrganizationHelp />
          {/* Folders section — personal and team scopes */}
          {(
            <div style={{ marginTop: 16 }}>
              {/* Folders header row */}
              <div
                style={{
                  padding: '0 8px 0 12px',
                  marginBottom: 4,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', color: '#666', letterSpacing: '0.5px' }}>
                  Folders
                </span>
                <button
                  type="button"
                  title="New folder"
                  aria-label="New folder"
                  disabled={folderSaving}
                  onClick={() => { setNewFolderMode(true); setNewFolderName(''); setFolderSaveError(null) }}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: '2px 4px',
                    cursor: 'pointer',
                    color: '#6b7280',
                    display: 'flex',
                    alignItems: 'center',
                    borderRadius: 4,
                    lineHeight: 1,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = '#555' }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = '#6b7280' }}
                >
                  <FolderPlus style={{ width: 13, height: 13 }} />
                </button>
              </div>

              {foldersError && <div role="alert" style={{ padding: 12, fontSize: 12, color: '#b91c1c' }}>Folders unavailable. {foldersError} <button type="button" onClick={() => void refreshFolders()}>Retry folders</button></div>}
              {folderSaveError && <p role="alert" style={{ padding: '0 12px', fontSize: 12, color: '#b91c1c' }}>{folderSaveError}</p>}
              {foldersLoading && <p role="status" style={{ padding: '0 12px', fontSize: 12 }}>Loading folders…</p>}
              {/* New folder input */}
              {newFolderMode && (
                <div style={{ padding: '4px 8px 4px 12px' }}>
                  <input
                    autoFocus
                    type="text"
                    aria-label="New Library folder name"
                    disabled={folderSaving}
                    value={newFolderName}
                    maxLength={MAX_NAME_LENGTH}
                    onChange={(e) => setNewFolderName(e.target.value)}
                    placeholder="Folder name"
                    onKeyDown={(e) => {
                      if (e.nativeEvent.isComposing) return
                      if (e.key === 'Enter' && newFolderName.trim()) {
                        e.preventDefault(); void submitFolder()
                      } else if (e.key === 'Escape' && !folderSaving) {
                        setNewFolderMode(false)
                        setNewFolderName('')
                      }
                    }}
                    style={{
                      width: '100%',
                      fontSize: 12,
                      padding: '4px 6px',
                      border: '1px solid #dadce0',
                      borderRadius: 5,
                      outline: 'none',
                      fontFamily: 'inherit',
                      boxSizing: 'border-box',
                    }}
                  />
                  <div className="library-folder-form-actions"><button type="button" disabled={folderSaving || !newFolderName.trim()} onClick={() => void submitFolder()}>{folderSaving ? 'Saving…' : 'Create folder'}</button><button type="button" disabled={folderSaving} onClick={() => { setNewFolderMode(false); setFolderSaveError(null) }}>Cancel</button></div>
                </div>
              )}

              {/* Folder list */}
              {folders.length === 0 && !newFolderMode && !foldersLoading && !foldersError && (
                <div style={{ padding: '4px 12px', fontSize: 11, color: '#6b7280', fontStyle: 'italic' }}>
                  No folders yet
                </div>
              )}
              {folders.map((folder) => {
                const isActive = viewFilter === folder.uuid
                const isRenaming = renamingFolder === folder.uuid
                const isMenuOpen = folderMenuOpen === folder.uuid
                return (
                  <div
                    key={folder.uuid}
                    style={{ position: 'relative' }}
                  >
                    {isRenaming ? (
                      <div style={{ padding: '4px 8px 4px 12px' }}>
                        <input
                          autoFocus
                          type="text"
                          aria-label="Rename Library folder"
                          disabled={folderSaving}
                          value={renameValue}
                          maxLength={MAX_NAME_LENGTH}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.nativeEvent.isComposing) return
                            if (e.key === 'Enter' && renameValue.trim()) {
                              e.preventDefault(); void submitFolder(folder.uuid)
                            } else if (e.key === 'Escape' && !folderSaving) {
                              setRenamingFolder(null)
                            }
                          }}
                          style={{
                            width: '100%',
                            fontSize: 12,
                            padding: '4px 6px',
                            border: '1px solid #dadce0',
                            borderRadius: 5,
                            outline: 'none',
                            fontFamily: 'inherit',
                            boxSizing: 'border-box',
                          }}
                        />
                        <div className="library-folder-form-actions"><button type="button" disabled={folderSaving || !renameValue.trim()} onClick={() => void submitFolder(folder.uuid)}>{folderSaving ? 'Saving…' : 'Save folder name'}</button><button type="button" disabled={folderSaving} onClick={() => { setRenamingFolder(null); setFolderSaveError(null) }}>Cancel</button></div>
                      </div>
                    ) : (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          padding: '7px 6px 7px 12px',
                          cursor: 'pointer',
                          fontSize: 12,
                          fontWeight: isActive ? 600 : 500,
                          color: isActive ? 'var(--library-highlight-ink)' : '#4a4a4a',
                          backgroundColor: isActive ? 'var(--library-highlight-soft)' : 'transparent',
                          borderLeft: isActive ? '3px solid var(--library-highlight)' : '3px solid transparent',
                          transition: 'background 0.1s',
                          gap: 0,
                        }}
                        onMouseEnter={(e) => {
                          if (!isActive) e.currentTarget.style.backgroundColor = '#f0f0f0'
                          const btn = e.currentTarget.querySelector('.folder-menu-btn') as HTMLElement
                          if (btn) btn.style.opacity = '1'
                        }}
                        onMouseLeave={(e) => {
                          if (!isActive) e.currentTarget.style.backgroundColor = 'transparent'
                          if (!isMenuOpen) {
                            const btn = e.currentTarget.querySelector('.folder-menu-btn') as HTMLElement
                            if (btn) btn.style.opacity = '0'
                          }
                        }}
                      >
                        <button type="button" aria-label={`Open folder ${folder.name}`} aria-pressed={isActive} onClick={() => { setViewFilter(folder.uuid); setMobileViewsOpen(false) }} style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0, background: 'none', border: 0, padding: '4px 0', textAlign: 'left', color: 'inherit', font: 'inherit', cursor: 'pointer' }}>
                        {isActive
                          ? <FolderOpen style={{ width: 13, height: 13, marginRight: 7, flexShrink: 0 }} />
                          : <Folder style={{ width: 13, height: 13, marginRight: 7, flexShrink: 0 }} />
                        }
                        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {folder.name}
                        </span>
                        <span style={{ fontSize: 12, color: '#59616b', marginRight: 4, flexShrink: 0 }}>
                          {folder.item_count}
                        </span>
                        </button>
                        <button
                          type="button"
                          aria-label={`Folder actions: ${folder.name}`}
                          aria-expanded={isMenuOpen}
                          className="folder-menu-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            folderMenuTrigger.current = e.currentTarget
                            if (!isMenuOpen) {
                              const rect = e.currentTarget.getBoundingClientRect()
                              setFolderMenuPos({ top: Math.min(rect.bottom + 4, window.innerHeight - 108), left: Math.min(rect.left, window.innerWidth - 160) })
                            }
                            setFolderMenuOpen(isMenuOpen ? null : folder.uuid)
                          }}
                          style={{
                            background: 'none',
                            border: 'none',
                            padding: '2px 3px',
                            cursor: 'pointer',
                            color: '#666',
                            display: 'flex',
                            alignItems: 'center',
                            borderRadius: 4,
                            opacity: 1,
                            transition: 'opacity 0.1s',
                            flexShrink: 0,
                          }}
                        >
                          <MoreHorizontal style={{ width: 16, height: 16 }} />
                        </button>
                      </div>
                    )}

                    {/* Folder context menu — rendered via portal to escape overflow:hidden */}
                    {isMenuOpen && createPortal(
                      <div
                        ref={folderMenuRef}
                        role="group"
                        aria-label={`Actions for folder ${folder.name}`}
                        onKeyDown={e => {
                          if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setFolderMenuOpen(null); folderMenuTrigger.current?.focus() }
                        }}
                        style={{
                          position: 'fixed',
                          left: folderMenuPos.left,
                          top: folderMenuPos.top,
                          zIndex: 9999,
                          minWidth: 140,
                          borderRadius: 8,
                          border: '1px solid rgba(0,0,0,0.14)',
                          background: '#fff',
                          boxShadow: '0 6px 18px rgba(0,0,0,0.14)',
                          padding: 4,
                        }}
                      >
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setRenamingFolder(folder.uuid)
                            setRenameValue(folder.name)
                            setFolderSaveError(null)
                            setFolderMenuOpen(null)
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            width: '100%',
                            background: 'none',
                            border: 'none',
                            padding: '8px 10px',
                            fontSize: 12,
                            color: '#1f2937',
                            cursor: 'pointer',
                            borderRadius: 5,
                            textAlign: 'left',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                        >
                          <Pencil style={{ width: 12, height: 12, color: '#6b7280' }} />
                          Rename
                        </button>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation()
                            const ok = await confirm({
                              title: 'Delete folder?',
                              message: (
                                <>
                                  Are you sure you want to delete the folder <strong>{folder.name}</strong>? Items inside will be moved out of the folder (not deleted). This action cannot be undone.
                                </>
                              ),
                              confirmLabel: 'Delete',
                              destructive: true,
                            })
                            if (!ok) {
                              setFolderMenuOpen(null)
                              return
                            }
                            if (folderSavingRef.current) return
                            const scopeAtStart = currentScope.current
                            folderSavingRef.current = true; setFolderSaving(true); setFolderSaveError(null)
                            try {
                              await removeFolder(folder.uuid)
                              await refreshItems()
                              if (currentScope.current === scopeAtStart) {
                                setViewFilter(current => current === folder.uuid ? 'all' : current)
                                setFolderMenuOpen(null)
                              }
                            } catch (reason) {
                              if (currentScope.current === scopeAtStart) { setFolderSaveError(reason instanceof Error ? reason.message : 'Could not delete this folder.'); setFolderMenuOpen(null) }
                            } finally { folderSavingRef.current = false; setFolderSaving(false) }
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            width: '100%',
                            background: 'none',
                            border: 'none',
                            padding: '8px 10px',
                            fontSize: 12,
                            color: '#dc2626',
                            cursor: 'pointer',
                            borderRadius: 5,
                            textAlign: 'left',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#fef2f2' }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                        >
                          <Trash2 style={{ width: 12, height: 12 }} />
                          Delete
                        </button>
                      </div>,
                      document.body,
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Drag handle — resize the sidebar */}
        <div className="library-sidebar-resizer"
          onMouseDown={(e) => {
            sidebarLeftRef.current = sidebarRef.current?.getBoundingClientRect().left ?? 0
            setResizing(true)
            e.preventDefault()
          }}
          onDoubleClick={() => setSidebarWidth(SIDEBAR_MIN)}
          title="Drag to resize · double-click to reset"
          style={{
            width: 6,
            flexShrink: 0,
            cursor: 'col-resize',
            backgroundColor: resizing ? 'var(--library-highlight)' : 'transparent',
            transition: resizing ? 'none' : 'background 0.15s',
            zIndex: 1,
          }}
          onMouseEnter={(e) => { if (!resizing) e.currentTarget.style.backgroundColor = '#e0e0e0' }}
          onMouseLeave={(e) => { if (!resizing) e.currentTarget.style.backgroundColor = 'transparent' }}
        />

        {/* Results pane */}
        <div className="library-results" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'hidden', backgroundColor: '#fff', borderRight: '1px solid #f0f0f0' }}>
          {/* Collection filter banner */}
          {selectedCollection && (
            <div style={{ padding: '12px 24px', background: '#f8f9fa', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#202124' }}>{selectedCollection.title}</div>
                {selectedCollection.description && (
                  <div style={{ fontSize: 12, color: '#666', marginTop: 2 }}>{selectedCollection.description}</div>
                )}
              </div>
              <button
                type="button"
                aria-label="Clear collection filter"
                onClick={() => setViewFilter('all')}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: 4,
                  cursor: 'pointer',
                  color: '#666',
                  display: 'flex',
                  alignItems: 'center',
                  borderRadius: 4,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = '#333' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = '#666' }}
              >
                <X style={{ width: 16, height: 16 }} />
              </button>
            </div>
          )}

          {/* List header */}
          <div className="library-list-header"
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 100px',
              padding: '10px 24px',
              backgroundColor: '#fff',
              borderBottom: '1px solid #f0f0f0',
              fontSize: 12,
              fontWeight: 500,
              color: '#5f6368',
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}
          >
            <div>Name</div>
            <div style={{ textAlign: 'right' }}>Last Used</div>
          </div>

          {/* Items list */}
          <div style={{ flexGrow: 1, overflowY: 'auto', minHeight: 0, padding: 0 }}>
            <div className="library-recovery-feedback">
            {error && <div role="alert" className="library-feedback">{error} <button type="button" onClick={() => void refresh()}>Retry libraries</button></div>}
            {itemsError && <div role="alert" className="library-feedback">Items unavailable. {itemsError} <button type="button" onClick={() => void refreshItems()}>Retry items</button></div>}
            {itemAction?.scope === currentScope.current && <div role={itemAction.error ? 'alert' : 'status'} className="library-feedback">{itemAction.pending ? 'Saving… ' : itemAction.error ? 'Not saved. ' : 'Saved. '}{itemAction.label}{itemAction.error && <> — {itemAction.error} <button type="button" onClick={itemAction.retry}>Retry item action</button></>}</div>}
            {itemsLoading && items.length > 0 && <div role="status" className="library-feedback">Refreshing items…</div>}
            </div>
            {itemsLoading && !items.length ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#666', fontSize: 13 }}>Loading...</div>
            ) : itemsError && !items.length ? null : sorted.length === 0 ? (
              <div style={{ maxWidth: 360, margin: '0 auto', padding: '64px 32px', textAlign: 'center' }}>
                <h2 style={{ margin: 0, color: '#303030', fontSize: 16, fontWeight: 700 }}>
                  {selectedFolder && !search.trim() && kindFilter === 'all' ? 'This folder is empty' : hasActiveFilters ? 'No items match these filters' : 'Your library is ready for its first tool'}
                </h2>
                <p style={{ margin: '10px 0 18px', color: '#5f6368', fontSize: 13, lineHeight: 1.55 }}>
                  {hasActiveFilters
                    ? selectedFolder && !search.trim() && kindFilter === 'all' ? 'Move tools here from their item actions, or return to all items.' : 'Try clearing a filter or searching with a different term.'
                    : 'Create a workflow, extraction, prompt, or formatter to reuse reliable work, or start from a ready-made one in the catalog.'}
                </p>
                {hasActiveFilters ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSearch('')
                      setViewFilter('all')
                      setKindFilter('all')
                    }}
                    style={{ border: '1px solid #dadce0', borderRadius: 8, padding: '8px 12px', background: '#fff', color: '#303030', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                  >
                    Clear filters
                  </button>
                ) : (
                  <div style={{ display: 'flex', gap: 14, justifyContent: 'center', alignItems: 'center', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      onClick={() => openCreateModal('workflow')}
                      style={{ border: 0, borderRadius: 8, padding: '8px 12px', background: 'var(--library-highlight, #eab308)', color: 'var(--highlight-text-color, #000)', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}
                    >
                      Create a workflow
                    </button>
                    {/* Ready-made starting points live under Everyone (#961). */}
                    <button
                      type="button"
                      onClick={() => setScope('explore')}
                      style={{ border: 0, padding: 0, background: 'none', color: '#303030', fontSize: 13, fontWeight: 600, fontFamily: 'inherit', cursor: 'pointer' }}
                    >
                      Browse the catalog →
                    </button>
                  </div>
                )}
              </div>
            ) : (
              sorted.map((item) => (
                <LibraryItemRow
                  key={item.id}
                  item={item}
                  busy={itemAction?.scope === currentScope.current && itemAction.pending}
                  scope={scope}
                  onPin={handlePin}
                  onFavorite={handleFavorite}
                  onClone={handleClone}
                  onShare={handleShare}
                  onRemove={handleRemove}
                  onEdit={(it) => openPromptModal(it, 'edit')}
                  onMoveToFolder={handleMoveToFolder}
                  folders={folders}
                  qualityTier={item.quality_tier}
                  qualityScore={item.quality_score}
                  regressionPending={item.regression_pending_review}
                  onOpen={(it) => {
                    if (it.kind === 'workflow') {
                      markUsed(it.id)
                      openWorkflow(it.item_id)
                    } else if (it.set_type === 'prompt' || it.set_type === 'formatter') {
                      // Preview first — the prompt only launches into the
                      // Assistant (an LLM call) from the modal's Use button,
                      // which is also what bumps last-used.
                      openPromptModal(it, 'preview')
                    } else if (it.kind === 'search_set') {
                      markUsed(it.id)
                      openExtraction(it.item_uuid || it.item_id)
                    }
                  }}
                />
              ))
            )}
          </div>
        </div>
      </div>
      )}

      {/* Delete-choice Modal: remove bookmark vs. permanently delete the object */}
      {deleteTarget && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 2000,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'center',
            paddingTop: '8%',
            backgroundColor: 'rgba(0,0,0,0.4)',
          }}
          onClick={() => { if (!deleting) setDeleteTarget(null) }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={`Delete ${itemKindLabel(deleteTarget)}?`}
            style={{
              backgroundColor: '#fff',
              borderRadius: 'var(--ui-radius, 12px)',
              padding: '28px 32px',
              width: '90%',
              maxWidth: 480,
              boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
            }}
          >
            <h2 style={{ margin: '0 0 12px', fontSize: 20, fontWeight: 600, color: '#202124', textAlign: 'left' }}>
              Delete {itemKindLabel(deleteTarget)}?
            </h2>
            <p style={{ margin: '0 0 20px', fontSize: 14, color: '#5f6368', lineHeight: 1.5 }}>
              <strong style={{ color: '#202124' }}>{deleteTarget.name}</strong> can be removed from
              this library only — it still exists, keeps its name, and can be added back later.
              Or delete it permanently, which removes the {itemKindLabel(deleteTarget)} and its run
              history everywhere and cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <button
                onClick={() => handleDeleteChoice(true)}
                disabled={deleting}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontWeight: 700,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: 'none',
                  backgroundColor: '#dc2626',
                  color: '#fff',
                  cursor: deleting ? 'not-allowed' : 'pointer',
                  opacity: deleting ? 0.5 : 1,
                }}
              >
                {deleting ? 'Deleting...' : 'Delete permanently'}
              </button>
              <button
                onClick={() => handleDeleteChoice(false)}
                disabled={deleting}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: '1px solid #dadce0',
                  backgroundColor: '#fff',
                  color: '#202124',
                  cursor: deleting ? 'not-allowed' : 'pointer',
                  opacity: deleting ? 0.5 : 1,
                }}
              >
                Remove from library only
              </button>
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: 'none',
                  backgroundColor: 'transparent',
                  color: '#5f6368',
                  cursor: deleting ? 'not-allowed' : 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Creation Modal (workflow / extraction / prompt / formatter) */}
      {createModalType && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 2000,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'center',
            paddingTop: '8%',
            backgroundColor: 'rgba(0,0,0,0.4)',
          }}
          onClick={closeCreateModal}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: '#fff',
              borderRadius: 'var(--ui-radius, 12px)',
              padding: '28px 32px',
              width: '90%',
              maxWidth: 480,
              boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
            }}
          >
            <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 600, color: '#202124', textAlign: 'left' }}>
              {modalConfig[createModalType].title}
            </h2>
            <div style={{ marginBottom: 16 }}>
              <input
                type="text"
                value={createName}
                onChange={(e) => { setCreateName(e.target.value); if (createError) setCreateError(null) }}
                placeholder={modalConfig[createModalType].namePlaceholder}
                autoFocus
                maxLength={MAX_NAME_LENGTH}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  border: '1px solid #dadce0',
                  borderRadius: 8,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
                onKeyDown={(e) => e.key === 'Enter' && !modalConfig[createModalType].showDesc && handleCreate()}
              />
              <div style={{ marginTop: 4, textAlign: 'right', fontSize: 11, color: createName.length >= MAX_NAME_LENGTH ? '#dc2626' : '#9aa0a6' }}>
                {createName.length}/{MAX_NAME_LENGTH}
              </div>
            </div>
            {modalConfig[createModalType].showDesc && (
              <div style={{ marginBottom: 20 }}>
                <textarea
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  placeholder={modalConfig[createModalType].descPlaceholder}
                  rows={createModalType === 'workflow' ? 5 : 10}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    fontSize: 14,
                    fontFamily: 'inherit',
                    border: '1px solid #dadce0',
                    borderRadius: 8,
                    outline: 'none',
                    resize: 'vertical',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            )}
            {createError && (
              <div style={{ marginBottom: 12, padding: '10px 14px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, fontSize: 13, color: '#dc2626' }}>
                {createError}
              </div>
            )}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <button
                onClick={handleCreate}
                disabled={creating || uploading || !createName.trim()}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontWeight: 700,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: 'none',
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  color: 'var(--highlight-text-color, #000)',
                  cursor: creating || uploading || !createName.trim() ? 'not-allowed' : 'pointer',
                  opacity: creating || uploading || !createName.trim() ? 0.5 : 1,
                }}
              >
                {creating
                  ? 'Creating...'
                  : createModalType === 'workflow' ? 'Create Workflow'
                  : createModalType === 'prompt' ? 'Create Prompt'
                  : createModalType === 'formatter' ? 'Create Formatter'
                  : 'Create Extraction'}
              </button>
              <button
                onClick={closeCreateModal}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: '1px solid #dadce0',
                  backgroundColor: '#fff',
                  color: '#5f6368',
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
              {createModalType && (
                <>
                  <button
                    onClick={() => uploadInputRef.current?.click()}
                    disabled={creating || uploading}
                    title={`Upload a ${createModalType} JSON definition`}
                    style={{
                      marginLeft: 'auto',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '6px 10px',
                      fontSize: 12,
                      fontFamily: 'inherit',
                      borderRadius: 6,
                      border: '1px solid #dadce0',
                      backgroundColor: '#fff',
                      color: '#5f6368',
                      cursor: creating || uploading ? 'not-allowed' : 'pointer',
                      opacity: creating || uploading ? 0.5 : 1,
                    }}
                  >
                    <Upload style={{ width: 14, height: 14 }} />
                    {uploading ? 'Uploading…' : 'Upload JSON'}
                  </button>
                  <input
                    ref={uploadInputRef}
                    type="file"
                    accept=".json,application/json"
                    style={{ display: 'none' }}
                    onChange={handleUploadDefinition}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Preview / Edit Modal (prompts / formatters) */}
      {editingItem && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 2000,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'center',
            padding: 12,
            backgroundColor: 'rgba(0,0,0,0.4)',
          }}
          onClick={closeEditModal}
        >
          <FocusTrap focusTrapOptions={{ escapeDeactivates: false, allowOutsideClick: true, tabbableOptions: { displayCheck: 'none' } }}>
          <div
            role="dialog"
            aria-modal="true"
            aria-label={`${editMode === 'edit' ? 'Edit' : 'Preview'} ${editingItem.name}`}
            onKeyDown={e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeEditModal() } }}
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: '#fff',
              borderRadius: 'var(--ui-radius, 12px)',
              padding: 20,
              width: '100%',
              maxHeight: '100%',
              overflowY: 'auto',
              maxWidth: 480,
              boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
            }}
          >
            {editLoadError && <div role="alert" className="library-feedback">{editLoadError} <button type="button" onClick={() => void openPromptModal(editingItem, editMode)}>Retry item content</button></div>}
            {editMode === 'preview' ? (
              <>
                <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 600, color: '#202124', overflowWrap: 'anywhere' }}>
                  {editingItem.name}
                </h2>
                <div style={{ fontSize: 12, color: '#70757a', marginBottom: 16 }}>
                  {editingItem.set_type === 'formatter' ? 'Formatter' : 'Prompt'}
                </div>
                <div
                  role="region"
                  aria-label="Library item content"
                  tabIndex={0}
                  style={{
                    marginBottom: 20,
                    padding: '12px 14px',
                    fontSize: 14,
                    lineHeight: 1.5,
                    color: '#3c4043',
                    backgroundColor: '#f8f9fa',
                    border: '1px solid #e8eaed',
                    borderRadius: 8,
                    whiteSpace: 'pre-wrap',
                    overflowWrap: 'anywhere',
                    maxHeight: '45vh',
                    overflowY: 'auto',
                  }}
                >
                  {editLoading
                    ? 'Loading…'
                    : editContent.trim()
                      ? editContent
                      : `This ${editingItem.set_type === 'formatter' ? 'formatter' : 'prompt'} has no content yet — click Edit to add some.`}
                </div>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <button
                    onClick={usePromptInAssistant}
                    disabled={editLoading || !!editLoadError || !editContent.trim()}
                    style={{
                      padding: '10px 20px',
                      fontSize: 14,
                      fontWeight: 700,
                      fontFamily: 'inherit',
                      borderRadius: 8,
                      border: 'none',
                      backgroundColor: 'var(--highlight-color, #eab308)',
                      color: 'var(--highlight-text-color, #000)',
                      cursor: editLoading || !editContent.trim() ? 'not-allowed' : 'pointer',
                      opacity: editLoading || !editContent.trim() ? 0.5 : 1,
                    }}
                  >
                    Use in Assistant
                  </button>
                  <button
                    disabled={editLoading || !!editLoadError}
                    onClick={() => setEditMode('edit')}
                    style={{
                      padding: '10px 20px',
                      fontSize: 14,
                      fontFamily: 'inherit',
                      borderRadius: 8,
                      border: '1px solid #dadce0',
                      backgroundColor: '#fff',
                      color: '#5f6368',
                      cursor: 'pointer',
                    }}
                  >
                    Edit
                  </button>
                  <button
                    onClick={closeEditModal}
                    style={{
                      padding: '10px 20px',
                      fontSize: 14,
                      fontFamily: 'inherit',
                      borderRadius: 8,
                      border: '1px solid #dadce0',
                      backgroundColor: '#fff',
                      color: '#5f6368',
                      cursor: 'pointer',
                    }}
                  >
                    Close
                  </button>
                </div>
              </>
            ) : (
              <>
            <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 600, color: '#202124' }}>
              Edit {editingItem.set_type === 'formatter' ? 'Formatter' : 'Prompt'}
            </h2>
            <div style={{ marginBottom: 16 }}>
              <input
                type="text"
                value={editTitle}
                onChange={(e) => { setEditTitle(e.target.value); if (editError) setEditError(null) }}
                placeholder="Title"
                autoFocus
                aria-label="Library item title"
                disabled={editLoading || !!editLoadError || editSaving}
                maxLength={MAX_NAME_LENGTH}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  border: '1px solid #dadce0',
                  borderRadius: 8,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <textarea
                aria-label="Library item content"
                disabled={editLoading || !!editLoadError || editSaving}
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                placeholder={editingItem.set_type === 'formatter' ? 'Write your formatting instructions here' : 'Write your prompt here'}
                rows={10}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  border: '1px solid #dadce0',
                  borderRadius: 8,
                  outline: 'none',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                }}
              />
            </div>
            {editError && (
              <div style={{ marginBottom: 12, padding: '10px 14px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, fontSize: 13, color: '#dc2626' }}>
                {editError}
              </div>
            )}
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button
                onClick={handleEditSave}
                disabled={editLoading || !!editLoadError || editSaving || !editTitle.trim()}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontWeight: 700,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: 'none',
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  color: 'var(--highlight-text-color, #000)',
                  cursor: editSaving || !editTitle.trim() ? 'not-allowed' : 'pointer',
                  opacity: editSaving || !editTitle.trim() ? 0.5 : 1,
                }}
              >
                {editSaving ? 'Saving...' : 'Update'}
              </button>
              <button
                onClick={closeEditModal}
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  borderRadius: 8,
                  border: '1px solid #dadce0',
                  backgroundColor: '#fff',
                  color: '#5f6368',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
              </>
            )}
          </div>
          </FocusTrap>
        </div>
      )}

      {shareDialogItem && (
        <ShareWithTeamDialog
          itemName={shareDialogItem.name}
          teams={teams.map((t) => ({ id: t.id, name: t.name }))}
          defaultTeamId={teamId}
          onCancel={() => setShareDialogItem(null)}
          onConfirm={confirmShare}
        />
      )}
    </div>
  )
}

function NewMenuItem({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        width: '100%',
        alignItems: 'center',
        gap: 10,
        borderRadius: 8,
        padding: '10px 12px',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: 14,
        color: '#1f2937',
        textAlign: 'left',
        minHeight: 40,
        transition: 'background 0.1s',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(0,0,0,0.04)' }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
    >
      <span style={{ width: 18, display: 'flex', justifyContent: 'center', flexShrink: 0, color: '#5f6368' }}>{icon}</span>
      {label}
    </button>
  )
}
