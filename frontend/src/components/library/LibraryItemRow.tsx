import { useState, useRef, useEffect, useLayoutEffect } from 'react'
import {
  Ellipsis,
  Pin,
  Star,
  Copy,
  Share2,
  Trash2,
  Pencil,
  ShieldCheck,
  FolderInput,
  Check,
} from 'lucide-react'
import { QualityBadge } from './QualityBadge'
import { submitForVerification } from '../../api/library'
import { relativeTime } from '../../utils/time'
import type { LibraryItem, LibraryFolder } from '../../types/library'

interface Props {
  item: LibraryItem
  scope: 'mine' | 'team'
  onPin: (id: string, pinned: boolean) => void
  onFavorite: (id: string, favorited: boolean) => void
  onClone: (id: string) => void
  onShare: (id: string) => void
  onRemove: (id: string) => void
  onOpen?: (item: LibraryItem) => void
  onEdit?: (item: LibraryItem) => void
  onMoveToFolder?: (itemId: string, folderUuid: string | null) => void
  folders?: LibraryFolder[]
  qualityTier?: string | null
  qualityScore?: number | null
}

export function LibraryItemRow({ item, scope, onPin, onFavorite, onClone, onShare, onRemove, onOpen, onEdit, onMoveToFolder, folders, qualityTier, qualityScore }: Props) {
  const [hovered, setHovered] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [folderSubmenuOpen, setFolderSubmenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const [flipUp, setFlipUp] = useState(false)

  useLayoutEffect(() => {
    if (!menuOpen) { setFlipUp(false); return }
    const el = dropdownRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (rect.bottom + 8 > window.innerHeight) setFlipUp(true)
  }, [menuOpen])

  const kindLabel =
    item.kind === 'workflow'
      ? 'Workflow'
      : item.set_type === 'prompt'
        ? 'Prompt'
        : item.set_type === 'formatter'
          ? 'Formatter'
          : 'Extraction Task'

  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onOpen?.(item)}
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr auto',
        padding: '12px 24px',
        borderBottom: '1px solid #f0f0f0',
        alignItems: 'center',
        cursor: 'pointer',
        transition: 'background-color 0.1s',
        height: 72,
        position: 'relative',
        backgroundColor: hovered ? '#f8f9fa' : 'transparent',
      }}
    >
      {/* Name column */}
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', overflow: 'hidden', paddingRight: 16 }}>
        <div
          style={{
            fontWeight: 500,
            fontSize: 14,
            color: '#202124',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          {item.name}
          {item.favorited && !hovered && (
            <Star size={12} fill="#fbbc04" style={{ color: '#fbbc04', flexShrink: 0 }} />
          )}
          {item.pinned && !hovered && (
            <Pin size={12} style={{ color: 'var(--library-highlight, #eab308)', flexShrink: 0 }} />
          )}
        </div>
        <div style={{ fontSize: 12, color: '#70757a', marginTop: 4 }}>{kindLabel}</div>
        {item.tags.length > 0 && (
          <div style={{ marginTop: 4, display: 'flex', gap: 4 }}>
            {item.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: 11,
                  color: 'var(--library-highlight-ink, #78640c)',
                  background: 'color-mix(in srgb, var(--library-highlight, #eab308) 12%, #ffffff)',
                  padding: '2px 6px',
                  borderRadius: 4,
                }}
              >
                {tag}
              </span>
            ))}
            {item.tags.length > 3 && (
              <span style={{ fontSize: 10, color: '#888', alignSelf: 'center' }}>
                +{item.tags.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Last used / actions column */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2, flexShrink: 0 }}>
        {!hovered && !menuOpen ? (
          <div style={{ fontSize: 12, color: '#9aa0a6', whiteSpace: 'nowrap' }}>
            {item.last_used_at ? relativeTime(item.last_used_at) : item.created_at ? relativeTime(item.created_at) : 'Never'}
          </div>
        ) : (
          <>
            {/* Top row: action buttons */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {/* Favorite */}
            <button
              onClick={(e) => {
                e.stopPropagation()
                onFavorite(item.id, !item.favorited)
              }}
              title="Favorite"
              style={{
                background: 'none',
                border: 'none',
                width: 32,
                height: 32,
                borderRadius: 16,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: item.favorited ? '#fbbc04' : '#9aa0a6',
              }}
            >
              <Star size={14} fill={item.favorited ? '#fbbc04' : 'none'} />
            </button>

            {/* Pin */}
            <button
              onClick={(e) => {
                e.stopPropagation()
                onPin(item.id, !item.pinned)
              }}
              title="Pin"
              style={{
                background: 'none',
                border: 'none',
                width: 32,
                height: 32,
                borderRadius: 16,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: item.pinned ? 'var(--library-highlight, #eab308)' : '#9aa0a6',
              }}
            >
              <Pin size={14} />
            </button>

            {/* Ellipsis menu */}
            <div ref={menuRef} style={{ position: 'relative', display: 'inline-block' }}>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setMenuOpen(!menuOpen)
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  width: 32,
                  height: 32,
                  borderRadius: 16,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: '#9aa0a6',
                }}
              >
                <Ellipsis size={14} />
              </button>

              {menuOpen && (
                <div
                  ref={dropdownRef}
                  style={{
                    position: 'absolute',
                    right: 0,
                    ...(flipUp ? { bottom: '100%' } : { top: '100%' }),
                    zIndex: 1000,
                    minWidth: 200,
                    borderRadius: 'var(--ui-radius, 12px)',
                    border: '1px solid rgba(0,0,0,0.15)',
                    background: '#fff',
                    boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                    padding: '6px 0',
                  }}
                >
                  <MenuItem
                    icon={<Pin size={14} />}
                    label={item.pinned ? 'Unpin' : 'Pin'}
                    onClick={() => {
                      onPin(item.id, !item.pinned)
                      setMenuOpen(false)
                    }}
                  />
                  <MenuItem
                    icon={<Star size={14} />}
                    label={item.favorited ? 'Unfavorite' : 'Favorite'}
                    onClick={() => {
                      onFavorite(item.id, !item.favorited)
                      setMenuOpen(false)
                    }}
                  />
                  {onEdit && (item.set_type === 'prompt' || item.set_type === 'formatter') && (
                    <MenuItem
                      icon={<Pencil size={14} />}
                      label="Edit"
                      onClick={() => {
                        onEdit(item)
                        setMenuOpen(false)
                      }}
                    />
                  )}
                  <div style={{ borderTop: '1px solid #e0e0e0', margin: '4px 0' }} />
                  {scope === 'mine' ? (
                    <>
                      <MenuItem
                        icon={<Copy size={14} />}
                        label="Duplicate"
                        onClick={() => {
                          onClone(item.id)
                          setMenuOpen(false)
                        }}
                      />
                      <MenuItem
                        icon={<Share2 size={14} />}
                        label="Send to team"
                        onClick={() => {
                          onShare(item.id)
                          setMenuOpen(false)
                        }}
                      />
                    </>
                  ) : (
                    <MenuItem
                      icon={<Copy size={14} />}
                      label="Add to my library"
                      onClick={() => {
                        onClone(item.id)
                        setMenuOpen(false)
                      }}
                    />
                  )}
                  {!item.verified && (
                    <MenuItem
                      icon={<ShieldCheck size={14} />}
                      label="Submit for Verification"
                      onClick={async () => {
                        setMenuOpen(false)
                        try {
                          await submitForVerification({
                            item_kind: item.kind,
                            item_id: item.item_id,
                            summary: item.name,
                          })
                          alert('Submitted for verification!')
                        } catch {
                          alert('Failed to submit. Please try again.')
                        }
                      }}
                    />
                  )}
                  {onMoveToFolder && folders && folders.length > 0 && (
                    <>
                      <div style={{ borderTop: '1px solid #e0e0e0', margin: '4px 0' }} />
                      {/* Move to folder submenu trigger */}
                      <div style={{ position: 'relative' }}>
                        <button
                          onMouseEnter={() => setFolderSubmenuOpen(true)}
                          onMouseLeave={() => setFolderSubmenuOpen(false)}
                          style={{
                            display: 'flex',
                            width: '100%',
                            alignItems: 'center',
                            gap: 10,
                            padding: '8px 16px',
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            fontSize: 13,
                            color: '#1f2937',
                            textAlign: 'left',
                          }}
                          onFocus={() => setFolderSubmenuOpen(true)}
                          onBlur={() => setFolderSubmenuOpen(false)}
                        >
                          <span style={{ width: 20, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
                            <FolderInput size={14} />
                          </span>
                          Move to folder
                        </button>

                        {folderSubmenuOpen && (
                          <div
                            onMouseEnter={() => setFolderSubmenuOpen(true)}
                            onMouseLeave={() => setFolderSubmenuOpen(false)}
                            style={{
                              position: 'absolute',
                              right: 'calc(100% + 4px)',
                              top: 0,
                              zIndex: 1100,
                              minWidth: 180,
                              borderRadius: 'var(--ui-radius, 12px)',
                              border: '1px solid rgba(0,0,0,0.15)',
                              background: '#fff',
                              boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                              padding: '6px 0',
                            }}
                          >
                            {/* Remove from folder option */}
                            {item.folder && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onMoveToFolder(item.id, null)
                                  setMenuOpen(false)
                                  setFolderSubmenuOpen(false)
                                }}
                                style={{
                                  display: 'flex',
                                  width: '100%',
                                  alignItems: 'center',
                                  gap: 10,
                                  padding: '8px 16px',
                                  background: 'none',
                                  border: 'none',
                                  cursor: 'pointer',
                                  fontSize: 13,
                                  color: '#6b7280',
                                  textAlign: 'left',
                                  fontStyle: 'italic',
                                }}
                                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(0,0,0,0.04)' }}
                                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                              >
                                Remove from folder
                              </button>
                            )}
                            {folders.map((folder) => (
                              <button
                                key={folder.uuid}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onMoveToFolder(item.id, folder.uuid)
                                  setMenuOpen(false)
                                  setFolderSubmenuOpen(false)
                                }}
                                style={{
                                  display: 'flex',
                                  width: '100%',
                                  alignItems: 'center',
                                  gap: 10,
                                  padding: '8px 16px',
                                  background: 'none',
                                  border: 'none',
                                  cursor: 'pointer',
                                  fontSize: 13,
                                  color: '#1f2937',
                                  textAlign: 'left',
                                }}
                                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(0,0,0,0.04)' }}
                                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                              >
                                <span style={{ width: 20, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
                                  {item.folder === folder.uuid && <Check size={12} style={{ color: '#22c55e' }} />}
                                </span>
                                {folder.name}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </>
                  )}
                  <div style={{ borderTop: '1px solid #e0e0e0', margin: '4px 0' }} />
                  <MenuItem
                    icon={<Trash2 size={14} />}
                    label="Delete"
                    danger
                    onClick={() => {
                      onRemove(item.id)
                      setMenuOpen(false)
                    }}
                  />
                </div>
              )}
            </div>
            </div>
            {/* Bottom row: quality badge (workflows and extraction tasks only) */}
            {(qualityTier != null || qualityScore != null) && item.set_type !== 'prompt' && item.set_type !== 'formatter' && (
              <QualityBadge tier={qualityTier ?? null} score={qualityScore ?? null} />
            )}
          </>
        )}
      </div>
    </div>
  )
}

function MenuItem({
  icon,
  label,
  danger,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  danger?: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      style={{
        display: 'flex',
        width: '100%',
        alignItems: 'center',
        gap: 10,
        padding: '8px 16px',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: 13,
        color: danger ? '#d93025' : '#1f2937',
        textAlign: 'left',
        transition: 'background 0.1s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = 'rgba(0,0,0,0.04)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = 'transparent'
      }}
    >
      <span style={{ width: 20, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>{icon}</span>
      {label}
    </button>
  )
}
