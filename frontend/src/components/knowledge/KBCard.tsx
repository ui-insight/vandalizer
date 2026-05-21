import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import {
  ShieldCheck,
  Tag,
  Pencil,
  Trash2,
  BookmarkCheck,
  Copy,
  MessageSquare,
  MoreHorizontal,
  Share2,
  Link2,
  Send,
  Bookmark,
  Users,
} from 'lucide-react'
import type { KnowledgeBase } from '../../types/knowledge'
import type { Organization } from '../../api/organizations'
import { useShareLink } from '../../lib/shareLink'

const STATUS_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  empty: { label: 'Empty', color: '#6b7280', bg: '#f3f4f6' },
  building: { label: 'Building', color: '#d97706', bg: '#fef3c7' },
  ready: { label: 'Ready', color: '#15803d', bg: '#dcfce7' },
  error: { label: 'Error', color: '#b91c1c', bg: '#fef2f2' },
}

interface KBCardProps {
  kb: KnowledgeBase
  allOrgs: Organization[]
  onSelect: (uuid: string) => void
  onChat: (uuid: string, title: string) => void
  onEdit?: (uuid: string) => void
  onDelete?: (uuid: string) => void
  onAdopt?: (uuid: string) => void
  onRemoveRef?: (refUuid: string) => void
  onClone?: (uuid: string) => void
  onExplore?: (kb: KnowledgeBase) => void
  onShare?: (kb: KnowledgeBase) => void
  onSubmitVerify?: (kb: KnowledgeBase) => void
}

export function KBCard({
  kb, allOrgs, onSelect, onChat, onEdit, onDelete, onAdopt, onRemoveRef, onClone, onExplore,
  onShare, onSubmitVerify,
}: KBCardProps) {
  const badge = STATUS_BADGE[kb.status] || STATUS_BADGE.empty
  const isReady = kb.status === 'ready'
  const isReference = kb.is_reference
  const shareLink = useShareLink()

  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const [menuPos, setMenuPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 })
  const [flipUp, setFlipUp] = useState(false)

  const updateMenuPos = useCallback(() => {
    const btn = triggerRef.current
    if (!btn) return
    const rect = btn.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom
    const shouldFlip = spaceBelow < 280
    setFlipUp(shouldFlip)
    setMenuPos({
      top: shouldFlip ? rect.top : rect.bottom + 4,
      left: rect.right - 220,
    })
  }, [])

  useEffect(() => {
    if (!menuOpen) return
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

  const hasMenu =
    (!!onEdit && !isReference) ||
    (!!onShare && !isReference) ||
    (!!onSubmitVerify && !isReference && isReady && !kb.verified) ||
    (!!onAdopt && !isReference) ||
    !!onClone ||
    (!!onRemoveRef && isReference && !!kb.reference_uuid) ||
    (!!onDelete && !isReference)

  return (
    <div
      onClick={() => onExplore ? onExplore(kb) : (isReady ? onChat(isReference ? kb.source_kb_uuid! : kb.uuid, kb.title) : onSelect(kb.uuid))}
      style={{
        display: 'block', width: '100%', textAlign: 'left',
        padding: '14px 16px', backgroundColor: '#2a2a2a',
        border: isReference ? '1px solid rgba(37, 99, 235, 0.3)' : '1px solid #3a3a3a',
        borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
        transition: 'background-color 0.15s',
        position: 'relative',
      }}
      onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#333')}
      onMouseLeave={e => (e.currentTarget.style.backgroundColor = '#2a2a2a')}
    >
      {/* Title row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        {isReference && (
          <BookmarkCheck size={13} style={{ color: '#2563eb', flexShrink: 0 }} />
        )}
        <span style={{
          fontSize: 14, fontWeight: 600, color: '#e5e5e5', flex: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
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
        <span style={{
          fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
          color: badge.color, backgroundColor: badge.bg,
        }}>
          {badge.label}
        </span>
      </div>

      {/* Stats */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: '#999' }}>
        <span>{kb.total_sources} sources</span>
        <span>{kb.total_chunks} chunks</span>
      </div>

      {/* Org badges */}
      {(kb.organization_ids?.length ?? 0) > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
          {kb.organization_ids.map(gid => {
            const o = allOrgs.find(x => x.uuid === gid)
            return (
              <span key={gid} style={{
                display: 'inline-flex', alignItems: 'center', gap: 3,
                fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
                color: '#2563eb', backgroundColor: 'rgba(37, 99, 235, 0.1)',
              }}>
                <Tag size={9} />
                {o?.name || gid}
              </span>
            )
          })}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
        {isReady && (
          <button
            onClick={(e) => { e.stopPropagation(); onChat(isReference ? kb.source_kb_uuid! : kb.uuid, kb.title) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
              color: 'var(--highlight-text-color, #000)',
              backgroundColor: 'var(--highlight-color, #eab308)',
              border: 'none', borderRadius: 4, cursor: 'pointer',
            }}
          >
            <MessageSquare size={11} />
            Chat
          </button>
        )}
        <div style={{ flex: 1 }} />
        {hasMenu && (
          <button
            ref={triggerRef}
            onClick={(e) => {
              e.stopPropagation()
              if (!menuOpen) updateMenuPos()
              setMenuOpen(!menuOpen)
            }}
            title="More actions"
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 28, height: 24, fontFamily: 'inherit',
              color: '#aaa', backgroundColor: 'transparent',
              border: '1px solid #3a3a3a', borderRadius: 4, cursor: 'pointer',
            }}
          >
            <MoreHorizontal size={14} />
          </button>
        )}
      </div>

      {menuOpen && createPortal(
        <div
          ref={menuRef}
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'fixed',
            left: Math.max(8, menuPos.left),
            ...(flipUp ? { bottom: window.innerHeight - menuPos.top + 4 } : { top: menuPos.top }),
            zIndex: 9999,
            minWidth: 220,
            borderRadius: 8,
            border: '1px solid #3a3a3a',
            background: '#1e1e1e',
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
            padding: '6px 0',
          }}
        >
          {onEdit && !isReference && (
            <MenuItem
              icon={<Pencil size={14} />}
              label="Edit"
              onClick={() => {
                onEdit(kb.uuid)
                setMenuOpen(false)
              }}
            />
          )}
          {onShare && !isReference && (
            <MenuItem
              icon={kb.shared_with_team ? <Users size={14} /> : <Share2 size={14} />}
              label={kb.shared_with_team ? 'Unshare from team' : 'Share with team'}
              onClick={() => {
                onShare(kb)
                setMenuOpen(false)
              }}
            />
          )}
          {isReady && (
            <MenuItem
              icon={<Link2 size={14} />}
              label="Copy share link"
              onClick={() => {
                shareLink('kb', kb.uuid, kb.title)
                setMenuOpen(false)
              }}
            />
          )}
          {onSubmitVerify && !isReference && isReady && !kb.verified && (
            <MenuItem
              icon={<Send size={14} />}
              label="Submit for Verification"
              onClick={() => {
                onSubmitVerify(kb)
                setMenuOpen(false)
              }}
            />
          )}
          {onAdopt && !isReference && (
            <MenuItem
              icon={<Bookmark size={14} />}
              label="Add to My KBs"
              onClick={() => {
                onAdopt(kb.uuid)
                setMenuOpen(false)
              }}
            />
          )}
          {onClone && (
            <MenuItem
              icon={<Copy size={14} />}
              label={onAdopt ? 'Clone' : 'Add to My KBs'}
              onClick={() => {
                onClone(kb.uuid)
                setMenuOpen(false)
              }}
            />
          )}
          {onRemoveRef && isReference && kb.reference_uuid && (
            <MenuItem
              icon={<Trash2 size={14} />}
              label="Remove from My KBs"
              onClick={() => {
                onRemoveRef(kb.reference_uuid!)
                setMenuOpen(false)
              }}
            />
          )}
          {onDelete && !isReference && (
            <>
              <div style={{ borderTop: '1px solid #3a3a3a', margin: '4px 0' }} />
              <MenuItem
                icon={<Trash2 size={14} />}
                label="Delete"
                danger
                onClick={() => {
                  onDelete(kb.uuid)
                  setMenuOpen(false)
                }}
              />
            </>
          )}
        </div>,
        document.body,
      )}
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
        padding: '8px 14px',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: 13,
        fontFamily: 'inherit',
        color: danger ? '#ef4444' : '#e5e5e5',
        textAlign: 'left',
        transition: 'background 0.1s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = 'transparent'
      }}
    >
      <span style={{ width: 18, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>{icon}</span>
      {label}
    </button>
  )
}
