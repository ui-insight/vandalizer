import { useCallback, useEffect, useMemo, useState } from 'react'
import { Search, RefreshCw, Pencil, Check, X, CheckCircle2, ArrowUpDown } from 'lucide-react'
import {
  getAdminKnowledgeBases,
  type AdminKBSummary,
} from '../../api/admin'
import { updateKnowledgeBase } from '../../api/knowledge'

interface Props {
  /** Full admins can rename any KB; staff get a read-only inventory (the
   * backend rename path requires is_admin, so we hide the affordance for them
   * rather than let a save 403/404). */
  canEdit: boolean
}

type SortKey = 'title' | 'updated'

function formatDate(d: string | null): string {
  if (!d) return '—'
  const iso = !d.endsWith('Z') && !d.includes('+') && !d.includes('-', 10) ? d + 'Z' : d
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/** Org-wide KB inventory — built for reviewing names/versions and renaming KBs
 * in place (e.g. adding a date/version to the title). Source provenance per KB
 * is verified in the KB detail view; this surface is the bulk-rename overview. */
export function KnowledgeBasesTab({ canEdit }: Props) {
  const [kbs, setKbs] = useState<AdminKBSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortKey>('title')

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    // Pull the whole inventory once and filter client-side — org KB counts are
    // small enough that this is snappier than round-tripping every keystroke.
    getAdminKnowledgeBases({ limit: 5000 })
      .then(res => setKbs(res.knowledge_bases))
      .catch(e => setError((e as Error).message || 'Failed to load knowledge bases'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const rows = q
      ? kbs.filter(kb =>
          kb.title.toLowerCase().includes(q)
          || (kb.owner_email ?? '').toLowerCase().includes(q)
          || (kb.team_name ?? '').toLowerCase().includes(q)
          || kb.tags.some(t => t.toLowerCase().includes(q)))
      : kbs
    const sorted = [...rows]
    if (sort === 'title') {
      sorted.sort((a, b) => a.title.localeCompare(b.title))
    } else {
      sorted.sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? ''))
    }
    return sorted
  }, [kbs, search, sort])

  const applyRename = useCallback((uuid: string, title: string) => {
    setKbs(prev => prev.map(kb => (kb.uuid === uuid ? { ...kb, title } : kb)))
  }, [])

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: '#111827' }}>Knowledge Bases</h2>
          <p style={{ fontSize: 13, color: '#6b7280', margin: '2px 0 0 0' }}>
            Every KB across all users and teams. {canEdit
              ? 'Click the pencil to rename — e.g. add a date/version.'
              : 'Read-only (renaming requires full admin).'}
          </p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              aria-label="Search knowledge bases"
              placeholder="Search title, owner, team, tag…"
              style={{
                padding: '8px 10px 8px 30px', fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #e5e7eb', borderRadius: 8, width: 260, color: '#111827',
              }}
            />
          </div>
          <button
            onClick={load}
            title="Refresh"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 12px',
              fontSize: 13, fontFamily: 'inherit', border: '1px solid #e5e7eb', borderRadius: 8,
              background: '#fff', color: '#374151', cursor: 'pointer',
            }}
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, marginBottom: 12, background: '#fee2e2', color: '#991b1b', borderRadius: 8, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading…</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            {kbs.length === 0 ? 'No knowledge bases found.' : 'No matches.'}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <Th>#</Th>
                <Th ariaSort={sort === 'title' ? 'ascending' : 'none'}>
                  <button type="button" onClick={() => setSort('title')} style={sortBtn(sort === 'title')}>
                    Title <ArrowUpDown size={11} aria-hidden="true" />
                  </button>
                </Th>
                <Th>Tags</Th>
                <Th>Owner</Th>
                <Th>Team</Th>
                <Th align="right">Sources</Th>
                <Th align="right">Chunks</Th>
                <Th>Status</Th>
                <Th align="right" ariaSort={sort === 'updated' ? 'descending' : 'none'}>
                  <button type="button" onClick={() => setSort('updated')} style={sortBtn(sort === 'updated')}>
                    Updated <ArrowUpDown size={11} aria-hidden="true" />
                  </button>
                </Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((kb, i) => (
                <KBRow key={kb.uuid} kb={kb} index={i} canEdit={canEdit} onRenamed={applyRename} />
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
        {filtered.length} of {kbs.length} knowledge base{kbs.length === 1 ? '' : 's'}
      </div>
    </div>
  )
}

function KBRow({
  kb, index, canEdit, onRenamed,
}: {
  kb: AdminKBSummary
  index: number
  canEdit: boolean
  onRenamed: (uuid: string, title: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(kb.title)
  const [saving, setSaving] = useState(false)
  const [rowError, setRowError] = useState<string | null>(null)

  const startEdit = () => { setDraft(kb.title); setRowError(null); setEditing(true) }
  const cancel = () => { setEditing(false); setRowError(null) }

  const save = async () => {
    const next = draft.trim()
    if (!next || next === kb.title) { setEditing(false); return }
    setSaving(true)
    setRowError(null)
    try {
      await updateKnowledgeBase(kb.uuid, { title: next })
      onRenamed(kb.uuid, next)
      setEditing(false)
    } catch (e) {
      setRowError((e as Error).message || 'Rename failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <tr style={{ borderBottom: '1px solid #f3f4f6' }}>
      <Td style={{ color: '#6b7280', fontWeight: 600 }}>{index + 1}</Td>
      <Td>
        {editing ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              autoFocus
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); save() }
                if (e.key === 'Escape') cancel()
              }}
              maxLength={300}
              style={{
                flex: 1, minWidth: 220, padding: '5px 8px', fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, color: '#111827',
              }}
            />
            <button onClick={save} disabled={saving} title="Save" style={iconBtn('#16a34a')}>
              <Check size={15} />
            </button>
            <button onClick={cancel} disabled={saving} title="Cancel" style={iconBtn('#6b7280')}>
              <X size={15} />
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 500, color: '#111827' }}>{kb.title}</span>
            {kb.verified && (
              <span title="Verified" style={{ display: 'inline-flex', color: '#16a34a' }}>
                <CheckCircle2 size={14} />
              </span>
            )}
            {canEdit && (
              <button onClick={startEdit} title="Rename" style={{ ...iconBtn('#9ca3af'), opacity: 0.8 }}>
                <Pencil size={13} />
              </button>
            )}
          </div>
        )}
        {rowError && <div style={{ fontSize: 11, color: '#dc2626', marginTop: 3 }}>{rowError}</div>}
      </Td>
      <Td>
        {kb.tags.length > 0 ? (
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {kb.tags.map(t => (
              <span key={t} style={{
                fontSize: 10, padding: '1px 6px', borderRadius: 9999,
                background: '#f3f4f6', color: '#4b5563',
              }}>{t}</span>
            ))}
          </div>
        ) : <span style={{ color: '#6b7280' }}>—</span>}
      </Td>
      <Td style={{ fontSize: 13, color: '#6b7280' }}>{kb.owner_email || kb.owner_id}</Td>
      <Td style={{ fontSize: 13, color: '#6b7280' }}>{kb.team_name || '—'}</Td>
      <Td align="right" style={{ fontFamily: 'ui-monospace, monospace', fontSize: 13 }}>{kb.total_sources}</Td>
      <Td align="right" style={{ fontFamily: 'ui-monospace, monospace', fontSize: 13 }}>{kb.total_chunks}</Td>
      <Td><StatusPill status={kb.status} /></Td>
      <Td align="right" style={{ fontSize: 13, color: '#6b7280' }}>{formatDate(kb.updated_at)}</Td>
    </tr>
  )
}

function StatusPill({ status }: { status: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    ready: { bg: '#dcfce7', text: '#166534' },
    building: { bg: '#dbeafe', text: '#1e40af' },
    error: { bg: '#fee2e2', text: '#991b1b' },
    empty: { bg: '#f3f4f6', text: '#6b7280' },
  }
  const c = colors[status] || { bg: '#f3f4f6', text: '#374151' }
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 9999,
      fontSize: 11, fontWeight: 600, backgroundColor: c.bg, color: c.text,
    }}>
      {status}
    </span>
  )
}

function Th({ children, align = 'left', ariaSort }: {
  children: React.ReactNode
  align?: 'left' | 'right'
  ariaSort?: 'ascending' | 'descending' | 'none'
}) {
  return (
    <th
      scope="col"
      aria-sort={ariaSort}
      style={{
        padding: '10px 16px', textAlign: align, fontSize: 11, fontWeight: 600,
        color: '#6b7280', textTransform: 'uppercase', whiteSpace: 'nowrap',
      }}
    >
      {children}
    </th>
  )
}

function Td({ children, align = 'left', style }: { children: React.ReactNode; align?: 'left' | 'right'; style?: React.CSSProperties }) {
  return <td style={{ padding: '12px 16px', textAlign: align, verticalAlign: 'top', ...style }}>{children}</td>
}

function iconBtn(color: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color,
  }
}

function sortBtn(active: boolean): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 4, background: 'transparent',
    border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'inherit',
    fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
    color: active ? '#111827' : '#6b7280',
  }
}
