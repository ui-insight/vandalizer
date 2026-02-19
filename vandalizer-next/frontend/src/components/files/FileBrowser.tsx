import { useCallback, useMemo, useState, useRef, useEffect } from 'react'
import { Plus, Folder as FolderIcon, Upload, Search, X } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
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
import { deleteFile, renameFile, downloadFileUrl } from '../../api/files'
import { createFolder, renameFolder, deleteFolder } from '../../api/folders'
import type { Document, Folder } from '../../types/document'

interface FileBrowserProps {
  onDocClick?: (doc: Document) => void
}

export function FileBrowser({ onDocClick }: FileBrowserProps) {
  const { user } = useAuth()
  const { currentTeam } = useTeams()
  const space = user?.user_id || ''

  const [currentFolder, setCurrentFolder] = useState<string | null>(null)
  const { documents, folders, loading, refresh } = useDocuments(space, currentFolder, currentTeam?.uuid)
  const { breadcrumbs } = useBreadcrumbs(currentFolder)
  const { uploads, upload } = useUpload(space, currentFolder, refresh)

  // Search
  const [searchQuery, setSearchQuery] = useState('')
  const filteredFolders = useMemo(() => {
    if (!searchQuery.trim()) return folders
    const q = searchQuery.toLowerCase()
    return folders.filter(f => f.title.toLowerCase().includes(q))
  }, [folders, searchQuery])
  const filteredDocuments = useMemo(() => {
    if (!searchQuery.trim()) return documents
    const q = searchQuery.toLowerCase()
    return documents.filter(d => d.title.toLowerCase().includes(q))
  }, [documents, searchQuery])

  // Context menu state
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
        space,
        ...(createTeamFolder ? { folder_type: 'team' } : {}),
      })
      setShowCreateFolder(false)
      setCreateTeamFolder(false)
      refresh()
    },
    [currentFolder, space, createTeamFolder, refresh],
  )

  const handleDelete = useCallback(
    async (type: 'folder' | 'doc', uuid: string) => {
      if (type === 'doc') {
        await deleteFile(uuid)
      } else {
        await deleteFolder(uuid)
      }
      refresh()
    },
    [refresh],
  )

  if (loading && documents.length === 0 && folders.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-highlight border-t-transparent" />
      </div>
    )
  }

  return (
    <div style={{ padding: '0px 45px 45px 45px' }}>
      <UploadZone onFilesSelected={(files) => upload(files)} />
      <UploadProgress uploads={uploads} />

      {/* + Add button with dropdown menu - matches Flask _add_button.html */}
      <div ref={addMenuRef} className="relative inline-block mt-4">
        <button
          onClick={() => setAddMenuOpen(!addMenuOpen)}
          className="flex items-center gap-1 rounded-[var(--ui-radius)] bg-highlight text-highlight-text px-3 py-1.5 text-sm font-bold hover:brightness-90 transition-all"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <Plus className="h-4 w-4" />
          Add
        </button>

        {addMenuOpen && (
          <div
            className="absolute left-0 z-[1000] mt-2 min-w-[180px] rounded-lg border bg-white p-1.5"
            style={{
              borderColor: 'rgba(0,0,0,.15)',
              boxShadow: '0 8px 24px rgba(0,0,0,.12)',
            }}
          >
            <button
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
          accept=".pdf,.docx,.xlsx,.xls"
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) upload(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      {/* Breadcrumbs - matches Flask _breadcrumbs.html */}
      <Breadcrumbs items={breadcrumbs} onNavigate={setCurrentFolder} />

      {/* Search bar */}
      <div className="relative mt-3 mb-2">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="Search files and folders..."
          className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-9 text-sm text-gray-900 placeholder-gray-400 focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-gray-400 hover:text-gray-600"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* File table - matches Flask .styled-table */}
      <div
        className="mt-2.5 rounded-[12px] overflow-hidden"
        style={{ boxShadow: '0 0 20px rgba(0, 0, 0, 0.15)' }}
      >
        <FileList
          folders={filteredFolders}
          documents={filteredDocuments}
          onFolderClick={setCurrentFolder}
          onFolderContextMenu={handleFolderContextMenu}
          onDocContextMenu={handleDocContextMenu}
          onDocClick={onDocClick}
        />
      </div>

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          onRename={() => {
            const item = contextMenu.item
            setRenameTarget({
              type: contextMenu.type,
              uuid: item.uuid,
              name: item.title,
            })
          }}
          onDelete={() => handleDelete(contextMenu.type, contextMenu.item.uuid)}
          onDownload={
            contextMenu.type === 'doc'
              ? () => {
                  window.open(downloadFileUrl(contextMenu.item.uuid), '_blank')
                }
              : undefined
          }
          onCopyUuid={() => {
            navigator.clipboard.writeText(contextMenu.item.uuid)
          }}
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
    </div>
  )
}
