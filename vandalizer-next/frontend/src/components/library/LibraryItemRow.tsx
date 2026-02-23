import { useState, useRef, useEffect } from 'react'
import {
  Ellipsis,
  Pin,
  Star,
  Copy,
  Share2,
  Trash2,
  Pencil,
} from 'lucide-react'
import { QualityBadge } from './QualityBadge'
import type { LibraryItem } from '../../types/library'

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
  qualityTier?: string | null
  qualityScore?: number | null
}

export function LibraryItemRow({ item, scope, onPin, onFavorite, onClone, onShare, onRemove, onOpen, onEdit, qualityTier, qualityScore }: Props) {
  const [hovered, setHovered] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

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
        gridTemplateColumns: '4fr 2fr 120px',
        padding: '12px 24px',
        borderBottom: '1px solid #f0f0f0',
        alignItems: 'center',
        cursor: 'pointer',
        transition: 'background-color 0.1s',
        height: 72,
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
          {qualityTier !== undefined && <QualityBadge tier={qualityTier ?? null} score={qualityScore ?? null} />}
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

      {/* Last used column */}
      <div style={{ fontSize: 12, color: '#9aa0a6', overflow: 'hidden', paddingRight: 16 }}>
        {item.last_used_at ? relativeTime(item.last_used_at) : item.created_at ? relativeTime(item.created_at) : 'Never'}
      </div>

      {/* Actions column */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: 4,
          position: 'relative',
        }}
      >
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
            opacity: item.favorited || hovered ? 1 : 0,
            transition: 'opacity 0.1s',
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
            opacity: item.pinned || hovered ? 1 : 0,
            transition: 'opacity 0.1s',
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
              opacity: hovered ? 1 : 0,
              transition: 'opacity 0.1s',
            }}
          >
            <Ellipsis size={14} />
          </button>

          {menuOpen && (
            <div
              style={{
                position: 'absolute',
                right: 0,
                top: '100%',
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
    </div>
  )
}

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.floor(months / 12)}y ago`
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
