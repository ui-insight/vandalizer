import { User as UserIcon, Mail } from 'lucide-react'
import type { AuthorRef } from '../../types/library'

interface Props {
  author: AuthorRef | null | undefined
  /** Visual size: 'sm' for table rows / cards, 'md' for header areas. */
  size?: 'sm' | 'md'
  /** Optional override label prefix (e.g. "Author"). Default is no prefix. */
  label?: string
  /** 'default' for light backgrounds; 'on-dark' for colored/gradient headers. */
  tone?: 'default' | 'on-dark'
  className?: string
}

/**
 * Small "by Jane Doe ✉" chip for surfacing the original author of a workflow,
 * extraction, or library item. Renders nothing when no author is provided so
 * callers can drop it in unconditionally.
 *
 * The chip is interactive: clicking opens the author's email so the viewer can
 * reach out for refinement help. Stops propagation so it works inside cards
 * that have their own click handler.
 */
export function AuthorChip({ author, size = 'sm', label, tone = 'default', className }: Props) {
  if (!author) return null

  const display = author.name || author.email || author.user_id
  const fontSize = size === 'sm' ? 11 : 12
  const iconSize = size === 'sm' ? 10 : 12

  const subject = encodeURIComponent('Question about your workflow')
  const mailto = author.email ? `mailto:${author.email}?subject=${subject}` : null

  const content = (
    <>
      <UserIcon size={iconSize} style={{ flexShrink: 0 }} />
      {label && <span style={{ opacity: 0.7 }}>{label}</span>}
      <span style={{ fontWeight: 500 }}>{display}</span>
      {mailto && <Mail size={iconSize} style={{ flexShrink: 0, opacity: 0.6 }} />}
    </>
  )

  const baseStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    fontSize,
    color: tone === 'on-dark' ? '#ffffff' : '#5f6368',
    background: tone === 'on-dark' ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.04)',
    padding: '2px 8px',
    borderRadius: 999,
    lineHeight: 1.4,
    whiteSpace: 'nowrap',
    maxWidth: '100%',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  }

  if (mailto) {
    return (
      <a
        href={mailto}
        onClick={(e) => e.stopPropagation()}
        title={`Email ${display} about this workflow`}
        className={className}
        style={{
          ...baseStyle,
          textDecoration: 'none',
          cursor: 'pointer',
        }}
      >
        {content}
      </a>
    )
  }

  return (
    <span
      title={`Created by ${display}`}
      className={className}
      style={baseStyle}
    >
      {content}
    </span>
  )
}
