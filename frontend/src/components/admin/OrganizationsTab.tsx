import { FocusTrap } from '../shared/PanelFocusTrap'
import { TableRegion } from './shared/TableRegion'
import { useAdminQuery } from './shared/useAdminQuery'
import React, { useEffect, useState, useCallback, useRef } from 'react'
import {
  Users, Building2, Plus, Trash2, Pencil, ChevronRight, Download, AlertCircle, FolderTree, X, MoveRight,
} from 'lucide-react'
import { useConfirm } from '../shared/useConfirm'
import { useToast } from '../../contexts/ToastContext'
import { adminListAllTeams } from '../../api/admin'
import * as orgApi from '../../api/organizations'
import type { Organization, OrgMember } from '../../api/organizations'

const ORG_TYPE_LABELS: Record<string, string> = {
  university: 'University', college: 'College', central_office: 'Central Office',
  department: 'Department', unit: 'Unit',
}
const ORG_TYPE_COLORS: Record<string, string> = {
  university: 'bg-purple-100 text-purple-800', college: 'bg-blue-100 text-blue-800',
  central_office: 'bg-amber-100 text-amber-800', department: 'bg-green-100 text-green-800',
  unit: 'bg-gray-100 text-gray-800',
}
const VALID_CHILD_TYPES: Record<string, string[]> = {
  university: ['college', 'central_office'], college: ['department'],
  central_office: ['department'], department: ['unit'], unit: [],
}
const DEPTH_TYPE_DEFAULTS = ['university', 'college', 'department', 'unit'] as const

function OrgNodeRow({
  org, depth = 0, onEdit, onDelete, onAddChild, onTypeChange, onDrop, onMove, onReload, onSelect, selectedUuid,
}: {
  org: Organization; depth?: number
  onEdit: (o: Organization) => void; onDelete: (o: Organization) => void
  onAddChild: (parentId: string, parentType: string) => void
  onTypeChange: (uuid: string, newType: string) => void
  onDrop: (draggedUuid: string, targetUuid: string) => void
  onMove: (org: Organization) => void
  onReload: () => void
  onSelect: (o: Organization) => void
  selectedUuid: string | null
}) {
  const [expanded, setExpanded] = useState(depth < 2)
  const [dragOver, setDragOver] = useState(false)
  const hasChildren = org.children && org.children.length > 0
  const childTypes = VALID_CHILD_TYPES[org.org_type] || []
  const totalMembers = (org.user_count || 0) + (org.team_count || 0)
  const isSelected = selectedUuid === org.uuid

  return (
    <div>
      <div
        className={`org-node-row flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 transition-colors ${
          dragOver ? 'bg-blue-50 ring-2 ring-blue-300' : isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'
        }`}
        style={{ paddingLeft: `${Math.min(depth, 3) * 12 + 12}px` }}
        draggable
        onDragStart={e => { e.dataTransfer.setData('text/plain', org.uuid); e.dataTransfer.effectAllowed = 'move' }}
        onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); const uuid = e.dataTransfer.getData('text/plain'); if (uuid && uuid !== org.uuid) onDrop(uuid, org.uuid) }}
      >
        {hasChildren && <button aria-label={`${expanded ? 'Collapse' : 'Expand'} ${org.name}`} aria-expanded={expanded} onClick={() => setExpanded(!expanded)} className="flex h-7 w-7 items-center justify-center shrink-0"><ChevronRight className={`h-4 w-4 text-gray-600 transition-transform ${expanded ? 'rotate-90' : ''}`} /></button>}
        <button onClick={() => onSelect(org)} aria-label={`Manage ${org.name}`} aria-pressed={isSelected} className="org-node-name flex items-center gap-2 min-w-0 flex-1 text-left">
          <Building2 className="h-4 w-4 text-gray-500 shrink-0" />
          <span className="font-medium text-gray-900 break-words">{org.name}</span>
        </button>
        <select
          aria-label={`Organization type for ${org.name}`}
          value={org.org_type}
          onChange={e => onTypeChange(org.uuid, e.target.value)}
          className={`rounded-full px-2 py-0.5 text-xs font-medium border-0 cursor-pointer ${ORG_TYPE_COLORS[org.org_type] || 'bg-gray-100 text-gray-600'}`}
        >
          {Object.entries(ORG_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {totalMembers > 0 && (
          <button onClick={() => onSelect(org)}
            className="flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-200" aria-label={`Manage members of ${org.name}`} title="Manage members">
            <Users className="h-3 w-3" />{totalMembers}
          </button>
        )}
        <div className="flex items-center gap-0.5 shrink-0">
          {childTypes.length > 0 && (
            <button onClick={() => onAddChild(org.uuid, org.org_type)}
              className="rounded p-1 text-gray-600 hover:bg-gray-100 hover:text-gray-600" aria-label={`Add child to ${org.name}`} title="Add child">
              <Plus className="h-3.5 w-3.5" />
            </button>
          )}
          <button onClick={() => onEdit(org)} className="rounded p-1 text-gray-600 hover:bg-gray-100 hover:text-gray-600" aria-label={`Rename ${org.name}`} title="Rename">
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => onMove(org)} className="rounded p-1 text-gray-600 hover:bg-gray-100" aria-label={`Move ${org.name}`} title="Move to another parent"><MoveRight className="h-3.5 w-3.5" /></button>
          <button onClick={() => onDelete(org)} className="rounded p-1 text-gray-600 hover:bg-gray-100 hover:text-red-700" aria-label={`Delete ${org.name}`} title="Delete">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      {expanded && hasChildren && org.children!.map(child => (
        <OrgNodeRow key={child.uuid} org={child} depth={depth + 1} onEdit={onEdit} onDelete={onDelete}
          onAddChild={onAddChild} onTypeChange={onTypeChange} onDrop={onDrop} onMove={onMove} onReload={onReload}
          onSelect={onSelect} selectedUuid={selectedUuid} />
      ))}
    </div>
  )
}

function OrgMemberPanel({ org, onClose, onReload }: { org: Organization; onClose: () => void; onReload: () => void }) {
  const { toast } = useToast()
  const requestMembers = useCallback(() => orgApi.getOrgMembers(org.uuid), [org.uuid])
  const { data: members, loading, error: membersError, load: loadMembers } = useAdminQuery(requestMembers)
  const busyRef = useRef(false)
  const [busy, setBusy] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [searchQ, setSearchQ] = useState('')
  const [searchResults, setSearchResults] = useState<OrgMember[]>([])
  const [searching, setSearching] = useState(false)
  const requestTeams = useCallback(() => adminListAllTeams(), [])
  const { data: teamData, error: teamError, load: loadTeams } = useAdminQuery(requestTeams)
  const teams = teamData?.items ?? []

  // Debounced user search
  useEffect(() => {
    if (!searchQ.trim()) { setSearchResults([]); return }
    let cancelled = false
    const timer = setTimeout(async () => {
      setSearching(true)
      setSearchError(null)
      try {
        const data = await orgApi.searchUsers(searchQ.trim())
        if (!cancelled) setSearchResults(data.users)
      } catch (e) {
        if (!cancelled) { setSearchResults([]); setSearchError(e instanceof Error ? e.message : 'Search unavailable. Try again.') }
      } finally {
        if (!cancelled) setSearching(false)
      }
    }, 300)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [searchQ])

  const assignUser = async (userId: string) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try {
      await orgApi.assignUserToOrg(org.uuid, userId)
      setSearchQ(''); setSearchResults([]); loadMembers(); onReload()
    } catch (e) {
      toast(`Failed to add user to organization: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally { busyRef.current = false; setBusy(false) }
  }
  const unassignUser = async (userId: string) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try {
      await orgApi.unassignUserFromOrg(org.uuid, userId)
      loadMembers(); onReload()
    } catch (e) {
      toast(`Failed to remove user from organization: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally { busyRef.current = false; setBusy(false) }
  }
  const assignTeam = async (teamUuid: string) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try {
      await orgApi.assignTeamToOrg(org.uuid, teamUuid)
      loadMembers(); onReload()
    } catch (e) {
      toast(`Failed to add team to organization: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally { busyRef.current = false; setBusy(false) }
  }
  const unassignTeam = async (teamUuid: string) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try {
      await orgApi.unassignTeamFromOrg(org.uuid, teamUuid)
      loadMembers(); onReload()
    } catch (e) {
      toast(`Failed to remove team from organization: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally { busyRef.current = false; setBusy(false) }
  }

  const memberUserIds = new Set(members?.users.map(u => u.user_id) || [])
  const memberTeamUuids = new Set(members?.teams.map(t => t.uuid) || [])

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-900 flex items-center gap-2">
          <Users className="h-4 w-4 shrink-0" /> Members of &ldquo;{org.name}&rdquo;
        </h3>
        <button type="button" onClick={onClose} className="text-gray-500 hover:text-gray-600 text-xs">Close</button>
      </div>

      <fieldset disabled={busy} className="min-w-0 border-0 p-0">
      {/* Add user search */}
      <div className="mb-3">
        <label htmlFor="org-user-search" className="block text-xs font-medium text-gray-600 mb-1">Add User</label>
        <input id="org-user-search" type="text" value={searchQ} onChange={e => setSearchQ(e.target.value)}
          placeholder="Search by name or email..." className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm" />
        {searchQ.trim() && (
          <div className="mt-1 rounded border border-gray-200 bg-white max-h-32 overflow-y-auto">
            {searching ? <div className="p-2 text-xs text-gray-500">Searching...</div>
            : searchError ? <div role="alert" className="p-2 text-xs text-red-700">{searchError}</div> : searchResults.length === 0 ? <div className="p-2 text-xs text-gray-500">No results</div>
            : searchResults.map(u => (
              <div key={u.user_id} className="flex items-center justify-between px-3 py-1.5 hover:bg-gray-50">
                <span className="text-sm text-gray-700 truncate">{u.name || u.user_id}{u.email ? ` (${u.email})` : ''}</span>
                {memberUserIds.has(u.user_id) ? <span className="text-xs text-gray-500">Assigned</span>
                : <button onClick={() => assignUser(u.user_id)}
                    className="text-xs px-2 py-0.5 rounded bg-blue-600 text-white hover:bg-blue-700">Add</button>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add team dropdown */}
      <div className="mb-3">
        <label htmlFor="org-team-select" className="block text-xs font-medium text-gray-600 mb-1">Add Team</label>
        {teamError && <p role="alert" className="text-sm text-red-700">{teamError} <button onClick={loadTeams}>Retry teams</button></p>}
        <select id="org-team-select" onChange={e => { if (e.target.value) { assignTeam(e.target.value); e.target.value = '' } }}
          className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm" defaultValue="">
          <option value="" disabled>Select a team...</option>
          {teams.filter(t => !memberTeamUuids.has(t.uuid)).map(t => <option key={t.uuid} value={t.uuid}>{t.name}</option>)}
        </select>
      </div>

      {/* Current members */}
      {loading ? <div className="text-sm text-gray-500">Loading...</div> : (
        <div>
          {membersError && (
            <div className="mb-2 flex items-center gap-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              <span role="alert">{membersError}</span><button onClick={loadMembers}>Retry members</button>
            </div>
          )}
          {(members?.users.length || 0) > 0 && (
            <div className="mb-2">
              <div className="text-xs font-semibold text-gray-500 mb-1">Users ({members!.users.length})</div>
              {members!.users.map(u => (
                <div key={u.user_id} className="flex flex-wrap items-center justify-between gap-2 py-1 break-words">
                  <span className="min-w-0 flex-1 basis-full text-sm text-gray-700 [overflow-wrap:anywhere]">{u.name || u.user_id}{u.email ? ` (${u.email})` : ''}</span>
                  <button aria-label={`Remove ${u.name || u.email || u.user_id} from ${org.name}`} onClick={() => unassignUser(u.user_id)} className="text-xs text-red-700 hover:text-red-800">Remove</button>
                </div>
              ))}
            </div>
          )}
          {(members?.teams.length || 0) > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-500 mb-1">Teams ({members!.teams.length})</div>
              {members!.teams.map(t => (
                <div key={t.uuid} className="flex flex-wrap items-center justify-between gap-2 py-1 break-words">
                  <span className="min-w-0 flex-1 basis-full text-sm text-gray-700 [overflow-wrap:anywhere]">{t.name}</span>
                  <button aria-label={`Remove ${t.name} from ${org.name}`} onClick={() => unassignTeam(t.uuid)} className="text-xs text-red-700 hover:text-red-800">Remove</button>
                </div>
              ))}
            </div>
          )}
          {!membersError && !members?.users.length && !members?.teams.length && (
            <div className="text-sm text-gray-600">No users or teams assigned yet.</div>
          )}
        </div>
      )}
      </fieldset>
    </div>
  )
}

/**
 * Tokenize one CSV record into fields, honoring RFC 4180 quoting basics: a
 * double-quoted field may contain commas, and a doubled quote (`""`) inside a
 * quoted field is a literal quote. Unquoted fields are trimmed; the interior
 * spacing of quoted fields is preserved.
 *
 * Known limitation: this is a per-line tokenizer, so it does NOT support a
 * newline embedded inside a quoted field — that would require tokenizing the
 * whole document rather than one line at a time. Not attempted here.
 */
function splitCsvLine(line: string): string[] {
  const fields: string[] = []
  const len = line.length
  let i = 0
  while (i <= len) {
    while (i < len && (line[i] === ' ' || line[i] === '\t')) i++
    if (line[i] === '"') {
      i++ // consume opening quote
      let field = ''
      while (i < len) {
        if (line[i] === '"') {
          if (line[i + 1] === '"') { field += '"'; i += 2; continue }
          i++ // consume closing quote
          break
        }
        field += line[i]
        i++
      }
      // discard anything between the closing quote and the next comma
      while (i < len && line[i] !== ',') i++
      fields.push(field)
    } else {
      const start = i
      while (i < len && line[i] !== ',') i++
      fields.push(line.slice(start, i).trim())
    }
    if (i < len && line[i] === ',') { i++; continue }
    break
  }
  return fields
}

export function parseCSV(text: string): { name: string; parent_name: string; org_type: string }[] {
  // Strip a trailing \r explicitly (Windows line endings) before tokenizing,
  // rather than relying on incidental whole-line trimming.
  const rawLines = text.split('\n').map(l => l.replace(/\r$/, ''))
  const lines = rawLines.filter(l => l.trim().length > 0)
  if (lines.length < 2) return []
  const header = splitCsvLine(lines[0]).map(h => h.trim().toLowerCase())
  const nameIdx = header.findIndex(h => h === 'name')
  const parentIdx = header.findIndex(h => h === 'parent' || h === 'parent_name')
  if (nameIdx < 0) return []

  // Phase 1: collect raw rows (name + parent_name) in file order, with no
  // depth computation yet — CSV row order is not guaranteed to be
  // topological (a child row may appear before its parent).
  const raw: { name: string; parent_name: string }[] = []
  for (let i = 1; i < lines.length; i++) {
    const cols = splitCsvLine(lines[i])
    const name = cols[nameIdx] || ''
    const parent = parentIdx >= 0 ? (cols[parentIdx] || '') : ''
    if (!name) continue
    raw.push({ name, parent_name: parent })
  }

  // Phase 2: resolve each row's depth order-independently by walking up the
  // parent chain, memoizing as we go. A dangling parent reference (a name
  // that never appears as any row's `name`) is treated as depth 0, matching
  // today's fallback behavior. The walk is capped at the number of rows and
  // tracks the names currently being resolved, so a cyclic reference
  // (A -> B -> A) cannot recurse forever.
  const parentOf: Record<string, string> = {}
  for (const r of raw) if (r.parent_name) parentOf[r.name] = r.parent_name

  const depthCache: Record<string, number> = {}
  const cap = raw.length
  const resolveDepth = (name: string, visiting: Set<string>): number => {
    if (name in depthCache) return depthCache[name]
    if (visiting.has(name) || visiting.size >= cap) return 0
    const parent = parentOf[name]
    if (!parent) { depthCache[name] = 0; return 0 }
    visiting.add(name)
    const depth = resolveDepth(parent, visiting) + 1
    visiting.delete(name)
    depthCache[name] = depth
    return depth
  }

  const rows: { name: string; parent_name: string; org_type: string }[] = []
  for (const r of raw) {
    const myDepth = resolveDepth(r.name, new Set())
    const autoType = DEPTH_TYPE_DEFAULTS[Math.min(myDepth, DEPTH_TYPE_DEFAULTS.length - 1)]
    rows.push({ name: r.name, parent_name: r.parent_name, org_type: autoType })
  }
  return topoSortRows(rows)
}

/**
 * Reorder rows so that every row's parent (matched by name, when that name
 * appears elsewhere in the file) comes before it — the order the backend
 * importer requires (see bulk_import_organizations in
 * organization_service.py, which walks `nodes` in order and raises if a
 * child's parent hasn't been created yet).
 *
 * Fast path: if the input is already parent-before-child (using each name's
 * first occurrence as "when it becomes available"), it is returned
 * untouched — this guarantees byte-for-byte stability for already-correct
 * files rather than merely an equivalent reordering.
 *
 * Slow path: a stable-as-possible Kahn's-style topological sort. Each pass
 * scans rows in their original order and emits any row whose parent (if it
 * has one present in the file) has already been emitted; repeated passes
 * let a row whose parent appears later in the file "catch up" once that
 * parent is emitted. A row with no parent, or whose parent name never
 * appears in the file (a dangling reference — it may already exist
 * server-side), is emitted on the first pass. The pass loop is bounded by
 * "no progress made", so a cycle (A -> B -> A) cannot loop forever: once no
 * row can be emitted, whatever remains (the cycle members) is appended in
 * original relative order so no row is ever dropped.
 */
function topoSortRows<T extends { name: string; parent_name: string }>(rows: T[]): T[] {
  const n = rows.length
  const nameFirstIndex = new Map<string, number>()
  for (let i = 0; i < n; i++) if (!nameFirstIndex.has(rows[i].name)) nameFirstIndex.set(rows[i].name, i)

  const isAlreadyOrdered = rows.every((r, i) => {
    if (!r.parent_name) return true
    const parentIdx = nameFirstIndex.get(r.parent_name)
    return parentIdx === undefined || parentIdx < i
  })
  if (isAlreadyOrdered) return rows

  const emitted = new Array(n).fill(false)
  const emittedNames = new Set<string>()
  const result: T[] = []
  let remaining = n
  while (remaining > 0) {
    let progressed = false
    for (let i = 0; i < n; i++) {
      if (emitted[i]) continue
      const parent = rows[i].parent_name
      const needsParent = !!parent && nameFirstIndex.has(parent)
      if (!needsParent || emittedNames.has(parent)) {
        emitted[i] = true
        emittedNames.add(rows[i].name)
        result.push(rows[i])
        remaining--
        progressed = true
      }
    }
    if (!progressed) break
  }
  if (remaining > 0) {
    for (let i = 0; i < n; i++) if (!emitted[i]) result.push(rows[i])
  }
  return result
}

function ImportDialog({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [rows, setRows] = useState<{ name: string; parent_name: string; org_type: string }[]>([])
  const [importing, setImporting] = useState(false)
  const importingRef = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const errorRef = useRef<HTMLDivElement>(null)
  // Disabling the submit button can send browser focus to the document body.
  // Bring a rejected import back inside the dialog, where retry and Escape work.
  useEffect(() => { if (error && !importing) errorRef.current?.focus() }, [error, importing])

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const result = ev.target?.result
      if (typeof result !== 'string') {
        setError('Could not read the file as text.')
        return
      }
      const lines = result.split('\n').map(l => l.replace(/\r$/, '')).filter(l => l.trim().length > 0)
      if (lines.length === 0) { setError('The CSV file is empty.'); return }
      const header = splitCsvLine(lines[0]).map(h => h.trim().toLowerCase())
      if (!header.includes('name')) { setError('CSV must have a "name" column.'); return }
      const parsed = parseCSV(result)
      if (parsed.length === 0) { setError('CSV has a "name" column but no data rows.'); return }
      setError(null)
      setRows(parsed)
    }
    reader.onerror = () => { setError('Failed to read the file.') }
    reader.readAsText(file)
  }

  const handleImport = async () => {
    if (importingRef.current || !rows.length) return
    importingRef.current = true
    setImporting(true); setError(null)
    try {
      await orgApi.importOrganizations(rows)
      onImported(); onClose()
    } catch (e) { setError(e instanceof Error ? e.message : 'Import failed') }
    finally { importingRef.current = false; setImporting(false) }
  }

  const updateRow = (idx: number, field: 'name' | 'parent_name' | 'org_type', value: string) => {
    setRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }
  const removeRow = (idx: number) => setRows(prev => prev.filter((_, i) => i !== idx))

  return (
    <FocusTrap focusTrapOptions={{ escapeDeactivates: false, allowOutsideClick: true, tabbableOptions: { displayCheck: import.meta.env.MODE === 'test' ? 'none' : 'full' } }}>
    <div role="dialog" aria-modal="true" aria-labelledby="org-import-title" onKeyDown={e => { if (e.key === 'Escape' && !importingRef.current) { e.stopPropagation(); onClose() } }} className="fixed inset-0 bg-black/40 flex items-center justify-center p-4" style={{ zIndex: 700 }}>
      <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full min-w-0 max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h3 id="org-import-title" className="text-lg font-semibold text-gray-900">Import Organization Structure</h3>
          <button disabled={importing} aria-label="Close organization import" onClick={onClose} className="text-gray-600 hover:text-gray-800"><X className="h-5 w-5" /></button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
          {rows.length === 0 ? (
            <div>
              <p className="text-sm text-gray-600 mb-3">
                Upload a CSV with your university&apos;s organizational structure. The CSV should have columns:
              </p>
              <div className="bg-gray-50 rounded-lg p-3 mb-4 font-mono text-xs text-gray-700 break-words">
                name,parent<br/>
                University of Idaho,<br/>
                College of Engineering,University of Idaho<br/>
                College of Science,University of Idaho<br/>
                Department of Computer Science,College of Engineering<br/>
                Department of Physics,College of Science
              </div>
              <p className="text-xs text-gray-500 mb-3">
                The <strong>name</strong> column is required. The <strong>parent</strong> column references the parent node by name. Rows without a parent become root nodes. Types (university, college, department, unit) are auto-detected based on depth.
              </p>
              <input ref={fileRef} type="file" accept=".csv,.txt" onChange={handleFile} className="hidden" />
              <button onClick={() => fileRef.current?.click()}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                <Download className="h-4 w-4" /> Choose CSV File
              </button>
            </div>
          ) : (
            <div>
              <p className="text-sm text-gray-600 mb-2">
                {rows.length} organizations to import. Review and edit types before importing.
              </p>
              <div className="border rounded-lg overflow-hidden">
                <TableRegion label="Organization import preview — scroll for more columns"><table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th scope="col" className="px-3 py-2 text-left text-xs font-medium text-gray-500">Name</th>
                      <th scope="col" className="px-3 py-2 text-left text-xs font-medium text-gray-500">Parent</th>
                      <th scope="col" className="px-3 py-2 text-left text-xs font-medium text-gray-500">Type</th>
                      <th scope="col" className="px-3 py-2 w-8"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {rows.map((r, i) => (
                      <tr key={i} className="hover:bg-gray-50">
                        <td className="px-3 py-1.5">
                          <input disabled={importing} aria-label={`Organization name in row ${i + 1}`} value={r.name} onChange={e => updateRow(i, 'name', e.target.value)}
                            className="w-full border-0 bg-transparent text-sm p-0 focus:ring-0" />
                        </td>
                        <td className="px-3 py-1.5 text-gray-500">{r.parent_name || '(root)'}</td>
                        <td className="px-3 py-1.5">
                          <select disabled={importing} aria-label={`Organization type in row ${i + 1}`} value={r.org_type} onChange={e => updateRow(i, 'org_type', e.target.value)}
                            className={`rounded-full px-2 py-0.5 text-xs font-medium border-0 cursor-pointer ${ORG_TYPE_COLORS[r.org_type] || 'bg-gray-100'}`}>
                            {Object.entries(ORG_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                          </select>
                        </td>
                        <td className="px-3 py-1.5">
                          <button type="button" disabled={importing} aria-label={`Remove row ${i + 1}`} onClick={() => removeRow(i)} className="text-gray-500 hover:text-red-700"><Trash2 className="h-3.5 w-3.5" aria-hidden="true" /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table></TableRegion>
              </div>
              <div className="mt-2 flex gap-2">
                <button disabled={importing} onClick={() => setRows([])} className="text-xs text-gray-500 hover:text-gray-700">Clear & re-upload</button>
              </div>
            </div>
          )}
          {error && (
            <div ref={errorRef} tabIndex={-1} role="alert" className="flex items-center gap-2 text-sm text-red-700 bg-red-50 rounded-lg px-4 py-3">
              <AlertCircle className="h-4 w-4 shrink-0" />{error}
            </div>
          )}
        </div>
        {rows.length > 0 && (
          <div className="flex flex-wrap items-center justify-end gap-2 px-4 py-4 border-t">
            <button disabled={importing} onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
            <button onClick={handleImport} disabled={importing}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
              {importing ? 'Importing...' : `Import ${rows.length} Organizations`}
            </button>
          </div>
        )}
      </div>
    </div>
    </FocusTrap>
  )
}

export function OrganizationsTab() {
  const confirm = useConfirm()
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createParentId, setCreateParentId] = useState<string | undefined>()
  const [editOrg, setEditOrg] = useState<Organization | null>(null)
  const [formName, setFormName] = useState('')
  const [formType, setFormType] = useState('department')
  const [allowedTypes, setAllowedTypes] = useState<string[]>(Object.keys(ORG_TYPE_LABELS))
  const [showImport, setShowImport] = useState(false)
  const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null)
  const [movingOrg, setMovingOrg] = useState<Organization | null>(null)
  const [moveParent, setMoveParent] = useState('')

  const requestTree = useCallback(() => orgApi.getOrgTree(), [])
  const { data: treeData, loading, error: treeError, load: loadTree } = useAdminQuery(requestTree)
  const tree = treeData?.tree ?? []
  const savingRef = useRef(false)
  const [saving, setSaving] = useState(false)

  const handleCreate = async () => {
    if (!formName.trim() || savingRef.current) return
    savingRef.current = true; setSaving(true)
    setError(null)
    try {
      await orgApi.createOrganization({ name: formName.trim(), org_type: formType, parent_id: createParentId })
      setShowCreate(false); setFormName(''); setCreateParentId(undefined); loadTree()
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to create organization') }
    finally { savingRef.current = false; setSaving(false) }
  }
  const handleUpdate = async () => {
    if (!editOrg || !formName.trim() || savingRef.current) return
    savingRef.current = true; setSaving(true)
    setError(null)
    try { await orgApi.updateOrganization(editOrg.uuid, { name: formName.trim() }); setSelectedOrg(previous => previous?.uuid === editOrg.uuid ? { ...previous, name: formName.trim() } : previous); setEditOrg(null); setFormName(''); loadTree() }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to update') }
    finally { savingRef.current = false; setSaving(false) }
  }
  const handleDelete = async (org: Organization) => {
    const ok = await confirm({
      title: 'Delete organization?',
      message: (
        <>
          Are you sure you want to delete <strong>{org.name}</strong>? Any child organizations will be re-parented to its parent.
        </>
      ),
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok || savingRef.current) return
    savingRef.current = true; setSaving(true)
    setError(null)
    try { await orgApi.deleteOrganization(org.uuid); if (selectedOrg?.uuid === org.uuid) setSelectedOrg(null); loadTree() }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to delete') }
    finally { savingRef.current = false; setSaving(false) }
  }
  const handleTypeChange = async (uuid: string, newType: string) => {
    if (savingRef.current) return
    savingRef.current = true; setSaving(true)
    setError(null)
    try { await orgApi.updateOrgType(uuid, newType); loadTree() }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to change type') }
    finally { savingRef.current = false; setSaving(false) }
  }
  const handleDrop = async (draggedUuid: string, targetUuid: string | null) => {
    if (savingRef.current) return
    savingRef.current = true; setSaving(true)
    setError(null)
    try { await orgApi.moveOrganization(draggedUuid, targetUuid); setMovingOrg(null); loadTree() }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to move') }
    finally { savingRef.current = false; setSaving(false) }
  }

  const moveTargets: Organization[] = []
  const collectTargets = (nodes: Organization[]) => {
    for (const node of nodes) {
      if (node.uuid === movingOrg?.uuid) continue // Exclude this whole subtree to prevent cycles.
      moveTargets.push(node)
      collectTargets(node.children ?? [])
    }
  }
  collectTargets(tree)

  return (
    <div>
      {/* Header */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <FolderTree className="h-6 w-6 text-gray-700" />
          <h2 className="text-xl font-bold text-gray-900">Organization Hierarchy</h2>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowImport(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
            <Download className="h-4 w-4" /> Import CSV
          </button>
          <button onClick={() => {
            setShowCreate(true); setCreateParentId(undefined); setFormName('')
            setAllowedTypes(tree.length === 0 ? ['university'] : Object.keys(ORG_TYPE_LABELS))
            setFormType(tree.length === 0 ? 'university' : 'college')
          }} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700">
            <Plus className="h-4 w-4" /> Add
          </button>
        </div>
      </div>

      {/* Explanation */}
      <div className="mb-4 rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 text-sm text-gray-600">
        <strong className="text-gray-800">What is this?</strong> The org hierarchy models your university&apos;s structure
        (University &rarr; Colleges &rarr; Departments &rarr; Units). When you assign users and teams to org nodes, it controls
        which shared items and knowledge bases they can see. Users in a department see items scoped to their department and
        any parent college/university. <strong>Move</strong> a node to choose a new parent, or drag it onto another node. Select its name to manage members.
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />{error}
        </div>
      )}

      {movingOrg && <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold">Move: {movingOrg.name}</h3>
        <p className="mb-3 text-sm text-gray-600">Moving this node also moves its children and changes which parent organizations provide shared content access.</p>
        <fieldset disabled={saving} className="flex flex-wrap items-end gap-3 border-0 p-0 min-w-0">
          <label className="min-w-0 flex-1 basis-48 text-sm">New parent
            <select autoFocus value={moveParent} onChange={event => setMoveParent(event.target.value)} className="mt-1 w-full min-w-0 rounded border border-gray-300 px-2 py-2">
              {movingOrg.org_type === 'university' ? <option value="">No parent (root university)</option> : <option value="" disabled>Choose a parent</option>}
              {moveTargets.map(target => <option key={target.uuid} value={target.uuid}>{target.name}</option>)}
            </select>
          </label>
          <button type="button" disabled={moveParent === (movingOrg.parent_id ?? '') || (!moveParent && movingOrg.org_type !== 'university')} onClick={() => handleDrop(movingOrg.uuid, moveParent || null)} className="rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white">Move organization</button>
          <button type="button" onClick={() => { setMovingOrg(null); setError(null) }} className="rounded border px-3 py-2 text-sm">Cancel move</button>
        </fieldset>
      </div>}
      {/* Create/Edit form */}
      {(showCreate || editOrg) && (
        <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h3 className="mb-3 font-medium text-sm">{editOrg ? `Rename: ${editOrg.name}` : createParentId ? 'Add child node' : 'Create organization'}</h3>
          <fieldset disabled={saving} className="flex flex-wrap items-end gap-3 border-0 p-0 min-w-0">
            <div className="flex-1 min-w-0 basis-48">
              <input aria-label="Organization name" type="text" value={formName} onChange={e => setFormName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (editOrg ? handleUpdate() : handleCreate())}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="e.g., College of Science" autoFocus />
            </div>
            {!editOrg && (
              <select aria-label="Organization type" value={formType} onChange={e => setFormType(e.target.value)}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
                {allowedTypes.map(k => <option key={k} value={k}>{ORG_TYPE_LABELS[k] || k}</option>)}
              </select>
            )}
            <button onClick={editOrg ? handleUpdate : handleCreate}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
              {editOrg ? 'Save' : 'Create'}
            </button>
            <button onClick={() => { setShowCreate(false); setEditOrg(null); setFormName(''); setError(null) }}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">Cancel</button>
          </fieldset>
        </div>
      )}

      {/* Tree + member panel side by side */}
      <div className="flex flex-col xl:flex-row gap-4">
        <div className={`rounded-lg border border-gray-200 bg-white shadow-sm ${selectedOrg ? 'flex-1 min-w-0' : 'w-full'}`}>
          {loading ? (
            <div className="p-8 text-center text-gray-500">Loading...</div>
          ) : treeError ? <div className="p-4"><p role="alert" className="text-red-700">{treeError}</p><button onClick={loadTree} className="admin-open-record">Retry organizations</button></div> : tree.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <Building2 className="mx-auto mb-3 h-10 w-10 text-gray-300" />
              <p className="font-medium text-gray-700 mb-1">No organizations yet</p>
              <p className="text-sm">Create a root &ldquo;University&rdquo; node to get started, or import your structure from a CSV file.</p>
            </div>
          ) : (
            <fieldset disabled={saving} className="py-1 border-0 m-0 min-w-0">
              {tree.map(org => (
                <OrgNodeRow key={org.uuid} org={org}
                  onEdit={o => { setEditOrg(o); setFormName(o.name) }}
                  onDelete={handleDelete}
                  onAddChild={(parentId, parentType) => {
                    const ct = VALID_CHILD_TYPES[parentType] || []
                    setShowCreate(true); setCreateParentId(parentId); setFormName('')
                    setAllowedTypes(ct.length > 0 ? ct : Object.keys(ORG_TYPE_LABELS))
                    setFormType(ct[0] || 'department')
                  }}
                  onTypeChange={handleTypeChange}
                  onDrop={handleDrop}
                  onMove={org => { setMovingOrg(org); setMoveParent(org.parent_id ?? ''); setError(null) }}
                  onReload={loadTree}
                  onSelect={o => setSelectedOrg(prev => prev?.uuid === o.uuid ? null : o)}
                  selectedUuid={selectedOrg?.uuid || null}
                />
              ))}
            </fieldset>
          )}
        </div>

        {/* Member management panel */}
        {selectedOrg && (
          <div className="w-full xl:w-80 shrink-0 min-w-0">
            <OrgMemberPanel key={selectedOrg.uuid} org={selectedOrg} onClose={() => setSelectedOrg(null)} onReload={loadTree} />
          </div>
        )}
      </div>

      {/* Import dialog */}
      {showImport && <ImportDialog onClose={() => setShowImport(false)} onImported={loadTree} />}
    </div>
  )
}
