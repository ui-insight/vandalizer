import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from '../shared/panelPortal'
import {
  MoreHorizontal,
  Pin,
  Star,
  Copy,
  Share2,
  Link2,
  Trash2,
  Pencil,
  ShieldCheck,
  FolderInput,
  Check,
  Download,
} from 'lucide-react'
import { exportSearchSetUrl } from '../../api/extractions'
import { QualityBadge } from './QualityBadge'
import { VerificationSubmitModal } from './VerificationSubmitModal'
import { AuthorChip } from '../shared/AuthorChip'
import { useAuth } from '../../hooks/useAuth'
import { useShareLabel } from '../../lib/catalogLabels'
import { useToast } from '../../contexts/ToastContext'
import { useShareLink } from '../../lib/shareLink'
import { relativeTime } from '../../utils/time'
import type { LibraryItem, LibraryFolder } from '../../types/library'

interface Props {
  item: LibraryItem
  scope: 'mine' | 'team'
  busy?: boolean
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
  regressionPending?: boolean
}

export function LibraryItemRow({ item, scope, busy = false, onPin, onFavorite, onClone, onShare, onRemove, onOpen, onEdit, onMoveToFolder, folders, qualityTier, qualityScore, regressionPending }: Props) {
  const shareLabel = useShareLabel()
  const { user } = useAuth()
  const { toast } = useToast()
  const shareLink = useShareLink()
  const [hovered, setHovered] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [folderSubmenuOpen, setFolderSubmenuOpen] = useState(false)
  const [showVerifyModal, setShowVerifyModal] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const [menuPos, setMenuPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 })
  const [flipUp, setFlipUp] = useState(false)

  // The backend reports whether this user may delete the underlying object;
  // without it, removal is bookmark-only.
  const canDelete = item.can_delete_underlying === true

  const updateMenuPos = useCallback(() => {
    const btn = triggerRef.current
    if (!btn) return
    const rect = btn.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom
    const shouldFlip = spaceBelow < 320
    setFlipUp(shouldFlip)
    setMenuPos({
      top: shouldFlip ? rect.top : rect.bottom + 4,
      left: rect.right - 200, // align right edge with button
    })
  }, [])

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
    menuRef.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        menuRef.current && !menuRef.current.contains(target) &&
        triggerRef.current && !triggerRef.current.contains(target)
      ) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  return (
    <div className="library-item-row" data-menu-open={menuOpen}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onOpen?.(item)}
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) 100px',
        padding: "var(--workspace-space-12) var(--workspace-space-24)",
        borderBottom: '1px solid #f0f0f0',
        alignItems: 'center',
        cursor: 'pointer',
        transition: 'background-color 0.1s',
        minHeight: 88,
        position: 'relative',
        backgroundColor: hovered ? '#f8f9fa' : 'transparent',
      }}
    >
      {/* Name column */}
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', overflow: 'hidden', paddingRight: 'var(--workspace-space-16)' }}>
        <button type="button" aria-label={`Open ${item.name}`}
          style={{
            padding: 0, border: 0, background: 'transparent', textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit',
            fontWeight: 500,
            fontSize: 'var(--workspace-font-body)',
            color: '#202124',
            whiteSpace: 'normal',
            overflowWrap: 'anywhere',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--workspace-space-6)',
          }}
        >
          {item.name}
          {item.verified && (
            <span
              title="Shared with everyone — saved as a reference. Make a copy to edit."
              style={{ display: 'inline-flex', alignItems: 'center', flexShrink: 0 }}
            >
              <ShieldCheck size={13} style={{ color: '#b45309' }} />
            </span>
          )}
          {item.favorited && !hovered && (
            <Star size={12} fill="#fbbc04" style={{ color: '#fbbc04', flexShrink: 0 }} />
          )}
          {item.pinned && !hovered && (
            <Pin size={12} style={{ color: 'var(--library-highlight, #eab308)', flexShrink: 0 }} />
          )}
        </button>
        {item.kind === 'workflow' && item.description && (
          <div
            title={item.description}
            style={{
              fontSize: 'var(--workspace-font-meta)',
              color: '#5f6368',
              marginTop: 'var(--workspace-space-2)',
              whiteSpace: 'normal', overflowWrap: 'anywhere',
            }}
          >
            {item.description}
          </div>
        )}
        <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#5f6368', marginTop: 'var(--workspace-space-4)', display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)' }}>
          <span>{kindLabel}</span>
          {item.verified && (
            <span style={{ color: '#b45309', fontWeight: 500 }}>Shared with everyone</span>
          )}
          {item.created_by && item.created_by.user_id !== user?.user_id && (
            <AuthorChip author={item.created_by} />
          )}
          {(qualityTier != null || qualityScore != null) && item.set_type !== 'prompt' && item.set_type !== 'formatter' && (
            <QualityBadge
              tier={qualityTier ?? null}
              score={qualityScore ?? null}
              regressionPending={regressionPending}
            />
          )}
        </div>
        {item.tags.length > 0 && (
          <div style={{ marginTop: 'var(--workspace-space-4)', display: 'flex', gap: 'var(--workspace-space-4)' }}>
            {item.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: 'var(--workspace-font-meta)',
                  color: 'var(--library-highlight-ink, #78640c)',
                  background: 'color-mix(in srgb, var(--library-highlight, #eab308) 12%, #ffffff)',
                  padding: "var(--workspace-space-2) var(--workspace-space-6)",
                  borderRadius: 'var(--workspace-radius-small)',
                }}
              >
                {tag}
              </span>
            ))}
            {item.tags.length > 3 && (
              <span style={{ fontSize: 'var(--workspace-font-meta)', color: '#5f6368', alignSelf: 'center' }}>
                +{item.tags.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Last used column — right-aligned */}
      <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#5f6368', whiteSpace: 'nowrap', textAlign: 'right' }}>
        {item.last_used_at ? relativeTime(item.last_used_at) : 'Never'}
      </div>

      {/* Actions remain reachable by keyboard and touch. */}
      <div className="library-item-actions"
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute',
            right: 16,
            top: '50%',
            transform: 'translateY(-50%)',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--workspace-space-2)',
            background: '#fff',
            border: "1px solid var(--workspace-border)",
            borderRadius: 999,
            padding: "var(--workspace-space-2) var(--workspace-space-4)",
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            zIndex: 1,
          }}
        >
            {/* Favorite */}
            <button disabled={busy}
              onClick={(e) => {
                e.stopPropagation()
                onFavorite(item.id, !item.favorited)
              }}
              title={
                item.folder
                  ? item.favorited
                    ? 'Unfavorite (applies to this item everywhere, not just this folder)'
                    : 'Favorite (applies to this item everywhere, not just this folder)'
                  : item.favorited
                    ? 'Unfavorite'
                    : 'Favorite (shows in all views)'
              }
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
            <button disabled={busy}
              onClick={(e) => {
                e.stopPropagation()
                onPin(item.id, !item.pinned)
              }}
              title={
                item.folder
                  ? item.pinned
                    ? 'Unpin (applies to this item everywhere, not just this folder)'
                    : 'Pin (applies to this item everywhere, not just this folder)'
                  : item.pinned
                    ? 'Unpin'
                    : 'Pin (shows in all views)'
              }
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

            <div style={{ position: 'relative', display: 'inline-block' }}>
              <button disabled={busy}
                ref={triggerRef}
                aria-label="More actions"
                title="More actions"
                onClick={(e) => {
                  e.stopPropagation()
                  if (!menuOpen) updateMenuPos()
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
                <MoreHorizontal size={16} />
              </button>

              {menuOpen && createPortal(
                <div
                  ref={menuRef}
                  role="group"
                  aria-label={`Actions for ${item.name}`}
                  onKeyDown={e => {
                    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setMenuOpen(false); setFolderSubmenuOpen(false); triggerRef.current?.focus() }
                  }}
                  style={{
                    position: 'fixed',
                    left: Math.max(8, Math.min(menuPos.left, window.innerWidth - 248)),
                    ...(flipUp ? { bottom: window.innerHeight - menuPos.top + 4 } : { top: menuPos.top }),
                    zIndex: 9999,
                    width: Math.min(240, window.innerWidth - 16),
                    maxHeight: 'calc(100dvh - 24px)',
                    overflowY: 'auto',
                    borderRadius: 'var(--ui-radius, 12px)',
                    border: '1px solid rgba(0,0,0,0.15)',
                    background: '#fff',
                    boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                    padding: "var(--workspace-space-6) 0",
                  }}
                >
                  <MenuItem disabled={busy}
                    icon={<Pin size={14} />}
                    label={
                      item.folder
                        ? item.pinned ? 'Unpin (everywhere)' : 'Pin (everywhere)'
                        : item.pinned ? 'Unpin' : 'Pin'
                    }
                    title={item.folder ? 'Applies to this item everywhere, not just this folder' : undefined}
                    onClick={() => {
                      onPin(item.id, !item.pinned)
                      setMenuOpen(false)
                    }}
                  />
                  <MenuItem disabled={busy}
                    icon={<Star size={14} />}
                    label={
                      item.folder
                        ? item.favorited ? 'Unfavorite (everywhere)' : 'Favorite (everywhere)'
                        : item.favorited ? 'Unfavorite' : 'Favorite'
                    }
                    title={item.folder ? 'Applies to this item everywhere, not just this folder' : undefined}
                    onClick={() => {
                      onFavorite(item.id, !item.favorited)
                      setMenuOpen(false)
                    }}
                  />
                  {onEdit && (item.set_type === 'prompt' || item.set_type === 'formatter') && (
                    <MenuItem disabled={busy}
                      icon={<Pencil size={14} />}
                      label="Edit"
                      onClick={() => {
                        onEdit(item)
                        setMenuOpen(false)
                      }}
                    />
                  )}
                  {(item.set_type === 'prompt' || item.set_type === 'formatter') && item.item_uuid && (
                    <MenuItem disabled={busy}
                      icon={<Download size={14} />}
                      label="Download JSON"
                      title="Download as a shareable JSON file"
                      onClick={() => {
                        window.open(exportSearchSetUrl(item.item_uuid!), '_blank')
                        setMenuOpen(false)
                      }}
                    />
                  )}
                  <div style={{ borderTop: '1px solid #e0e0e0', margin: "var(--workspace-space-4) 0" }} />
                  {(item.kind === 'workflow' || item.kind === 'search_set') && (item.item_uuid || item.item_id) && (
                    <MenuItem disabled={busy}
                      icon={<Link2 size={14} />}
                      label="Copy share link"
                      onClick={() => {
                        const kind = item.kind === 'workflow' ? 'workflow' : 'extraction'
                        shareLink(kind, (item.item_uuid || item.item_id) as string, item.name)
                        setMenuOpen(false)
                      }}
                    />
                  )}
                  {scope === 'mine' ? (
                    <>
                      <MenuItem disabled={busy}
                        icon={<Copy size={14} />}
                        label="Duplicate"
                        onClick={() => {
                          onClone(item.id)
                          setMenuOpen(false)
                        }}
                      />
                      <MenuItem disabled={busy}
                        icon={<Share2 size={14} />}
                        label="Send to team…"
                        onClick={() => {
                          onShare(item.id)
                          setMenuOpen(false)
                        }}
                      />
                    </>
                  ) : (
                    <MenuItem disabled={busy}
                      icon={<Copy size={14} />}
                      label="Add to my library"
                      onClick={() => {
                        onClone(item.id)
                        setMenuOpen(false)
                      }}
                    />
                  )}
                  {!item.verified && (
                    <MenuItem disabled={busy}
                      icon={<ShieldCheck size={14} />}
                      label={shareLabel}
                      onClick={() => {
                        setMenuOpen(false)
                        setShowVerifyModal(true)
                      }}
                    />
                  )}
                  {onMoveToFolder && folders && folders.length > 0 && (
                    <>
                      <div style={{ borderTop: '1px solid #e0e0e0', margin: "var(--workspace-space-4) 0" }} />
                      {/* Move to folder submenu trigger */}
                      <div style={{ position: 'relative' }}>
                        <button disabled={busy}
                          onClick={(e) => {
                            e.stopPropagation()
                            setFolderSubmenuOpen(open => !open)
                          }}
                          style={{
                            display: 'flex',
                            width: '100%',
                            alignItems: 'center',
                            gap: 'var(--workspace-space-12)',
                            padding: "var(--workspace-space-8) var(--workspace-space-16)",
                            background: 'none',
                            border: 'none',
                            cursor: 'default',
                            fontSize: 'var(--workspace-font-control)',
                            color: '#1f2937',
                            textAlign: 'left',
                          }}
                          aria-expanded={folderSubmenuOpen}
                        >
                          <span style={{ width: 20, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
                            <FolderInput size={14} />
                          </span>
                          Move to folder
                        </button>

                        {folderSubmenuOpen && (
                          <div
                            style={{
                              position: 'relative',
                              margin: "var(--workspace-space-4) var(--workspace-space-8)",
                              zIndex: 1100,
                              minWidth: 180,
                              borderRadius: 'var(--ui-radius, 12px)',
                              border: '1px solid rgba(0,0,0,0.15)',
                              background: '#fff',
                              boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                              padding: "var(--workspace-space-6) 0",
                            }}
                          >
                            {/* Remove from folder option */}
                            {item.folder && (
                              <button disabled={busy}
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
                                  gap: 'var(--workspace-space-12)',
                                  padding: "var(--workspace-space-8) var(--workspace-space-16)",
                                  background: 'none',
                                  border: 'none',
                                  cursor: 'pointer',
                                  fontSize: 'var(--workspace-font-control)',
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
                              <button disabled={busy}
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
                                  gap: 'var(--workspace-space-12)',
                                  padding: "var(--workspace-space-8) var(--workspace-space-16)",
                                  background: 'none',
                                  border: 'none',
                                  cursor: 'pointer',
                                  fontSize: 'var(--workspace-font-control)',
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
                  <div style={{ borderTop: '1px solid #e0e0e0', margin: "var(--workspace-space-4) 0" }} />
                  {/* Only owners can truly delete. For a bookmark of someone
                      else's item (e.g. added from Explore) removal only drops
                      the bookmark, so label it "Remove" — same as KB cards. */}
                  <MenuItem disabled={busy}
                    icon={<Trash2 size={14} />}
                    label={canDelete ? 'Delete' : 'Remove'}
                    title={canDelete ? undefined : `Remove from library — the ${kindLabel.toLowerCase()} itself is kept by its owner`}
                    danger={canDelete}
                    onClick={() => {
                      onRemove(item.id)
                      setMenuOpen(false)
                    }}
                  />
                </div>,
                document.body,
              )}
            </div>
        </div>
      {showVerifyModal && (
        <VerificationSubmitModal
          itemKind={item.kind}
          itemId={item.item_id}
          itemTitle={item.name}
          onClose={() => setShowVerifyModal(false)}
          onSubmitted={() => {
            setShowVerifyModal(false)
            toast('Sent to the examiners — you\'ll hear back when someone has looked', 'success')
          }}
          onShareWithTeam={scope === 'mine' ? () => onShare(item.id) : undefined}
        />
      )}
    </div>
  )
}

function MenuItem({
  icon,
  disabled,
  label,
  title,
  danger,
  onClick,
}: {
  icon: React.ReactNode
  disabled?: boolean
  label: string
  title?: string
  danger?: boolean
  onClick: () => void
}) {
  return (
    <button disabled={disabled}
      title={title}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      style={{
        display: 'flex',
        width: '100%',
        alignItems: 'center',
        gap: 'var(--workspace-space-12)',
        padding: "var(--workspace-space-8) var(--workspace-space-16)",
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: 'var(--workspace-font-control)',
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
