import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { Loader2, Download, X } from 'lucide-react'
import { compareKBSourceVersions, getKBSourceVersion, listKBSourceVersions } from '../../api/knowledge'
import type { KBSourceVersion, KBSourceVersionCompare, KBSourceVersionDetail } from '../../types/knowledge'
import { formatCurrencyDate, formatCurrencyDateTime, shortHash } from './sourceCurrency'

interface Props {
  kbUuid: string
  sourceUuid: string
}

type Panel =
  | { kind: 'text'; version: KBSourceVersionDetail }
  | { kind: 'diff'; diff: KBSourceVersionCompare }

const ORIGIN_LABEL: Record<string, string> = {
  ingest: 'first fetch',
  refresh: 'refresh',
  supplied_text: 'supplied text',
  baseline: 'text held when history began',
}

export function effectiveRange(v: KBSourceVersion): string {
  const from = formatCurrencyDate(v.in_effect_from) ?? 'unknown'
  const to = v.superseded_at ? formatCurrencyDate(v.superseded_at) : 'now'
  return `${from} – ${to}`
}

/** End of the picked calendar day in the viewer's time zone, as UTC ISO —
 *  "what was in effect on Oct 3" means whatever was in effect by the end of it. */
export function endOfDayIso(day: string): string | null {
  const d = new Date(`${day}T23:59:59.999`)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

function downloadVersion(v: KBSourceVersionDetail) {
  const captured = (v.captured_at || v.in_effect_from || '').slice(0, 10) || 'undated'
  const header = [
    `URL: ${v.url ?? ''}`,
    `Version: ${v.number}`,
    `Captured: ${v.captured_at ?? 'unknown'}`,
    `In effect: ${v.in_effect_from ?? 'unknown'} to ${v.superseded_at ?? 'current'}`,
    `Content hash (${v.content_hash_algorithm}): ${v.content_hash}`,
    '',
    '',
  ].join('\n')
  const blob = new Blob([header + v.content], { type: 'text/plain;charset=utf-8' })
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = `source-v${v.number}-${captured}.txt`
  a.click()
  URL.revokeObjectURL(href)
}

const buttonStyle: CSSProperties = {
  fontSize: 11, padding: '2px 8px', fontFamily: 'inherit', cursor: 'pointer',
  color: '#cbd5e1', backgroundColor: 'transparent',
  border: '1px solid #2e2e2e', borderRadius: 4,
}

/**
 * A URL source's dated versions. A refresh that finds new page text keeps the
 * old text as an earlier version, so a user can read what the source said on
 * any date it was used, compare two versions, and download one as evidence.
 */
export function KBSourceVersionHistory({ kbUuid, sourceUuid }: Props) {
  const [versions, setVersions] = useState<KBSourceVersion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [day, setDay] = useState('')
  const [inEffect, setInEffect] = useState<{ day: string; uuid: string | null } | null>(null)
  const [panel, setPanel] = useState<Panel | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listKBSourceVersions(kbUuid, sourceUuid)
      .then(r => { if (!cancelled) setVersions(r.versions) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load version history') })
    return () => { cancelled = true }
  }, [kbUuid, sourceUuid])

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key)
    setError(null)
    try {
      await fn()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setBusy(null)
    }
  }

  const view = (v: KBSourceVersion) => run(`view:${v.uuid}`, async () => {
    setPanel({ kind: 'text', version: await getKBSourceVersion(kbUuid, sourceUuid, v.uuid) })
  })

  const compare = (base: KBSourceVersion, target: KBSourceVersion) => run(`diff:${target.uuid}`, async () => {
    setPanel({ kind: 'diff', diff: await compareKBSourceVersions(kbUuid, sourceUuid, base.uuid, target.uuid) })
  })

  const findInEffect = (picked: string) => {
    setDay(picked)
    const at = picked ? endOfDayIso(picked) : null
    if (!at) { setInEffect(null); return }
    run('at', async () => {
      const r = await listKBSourceVersions(kbUuid, sourceUuid, at)
      setVersions(r.versions)
      setInEffect({ day: picked, uuid: r.in_effect_version_uuid ?? null })
    })
  }

  if (versions === null && !error) {
    return (
      <div style={{ fontSize: 12, color: '#888', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
        <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
        Loading version history…
      </div>
    )
  }

  const list = versions ?? []
  const previousOf = (v: KBSourceVersion) => list.find(o => o.number === v.number - 1)

  return (
    <section aria-label="Version history" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#ccc', flex: 1 }}>
          Version history{list.length ? ` (${list.length})` : ''}
        </div>
        {list.length > 0 && (
          <label style={{ fontSize: 11, color: '#888', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            In effect on
            <input
              type="date"
              value={day}
              onChange={e => findInEffect(e.target.value)}
              style={{
                fontSize: 11, color: '#e5e5e5', backgroundColor: '#161616',
                border: '1px solid #2e2e2e', borderRadius: 4, padding: '2px 6px', fontFamily: 'inherit',
                colorScheme: 'dark',
              }}
            />
          </label>
        )}
      </div>

      {error && <div role="alert" style={{ fontSize: 12, color: '#f87171', marginBottom: 6 }}>{error}</div>}

      {inEffect && (
        <div role="status" style={{ fontSize: 12, color: '#cbd5e1', marginBottom: 6 }}>
          {inEffect.uuid
            ? <>On {formatCurrencyDate(endOfDayIso(inEffect.day))}, answers came from version {list.find(v => v.uuid === inEffect.uuid)?.number}.</>
            : <>No recorded version was in effect on {formatCurrencyDate(endOfDayIso(inEffect.day))}.</>}
        </div>
      )}

      {list.length === 0 ? (
        <div style={{ fontSize: 12, color: '#888', fontStyle: 'italic' }}>
          No versions recorded yet. History starts at this source's next refresh, which keeps the text below as the first version.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', border: '1px solid #2a2a2a', borderRadius: 6, maxHeight: 220, overflowY: 'auto' }}>
          {list.map(v => {
            const prev = previousOf(v)
            const highlighted = inEffect?.uuid === v.uuid
            return (
              <div
                key={v.uuid}
                data-testid={`version-${v.number}`}
                aria-current={highlighted ? 'true' : undefined}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '6px 10px',
                  borderBottom: '1px solid #242424', fontSize: 12, color: '#cbd5e1',
                  backgroundColor: highlighted ? 'rgba(37, 99, 235, 0.18)' : undefined,
                }}
              >
                <div style={{ width: 34, fontWeight: 600, color: '#fff' }}>v{v.number}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div>
                    In effect {effectiveRange(v)}
                    {v.is_current && <span style={{ color: '#34d399' }}> · current</span>}
                  </div>
                  <div style={{ fontSize: 11, color: '#888' }}>
                    Captured {formatCurrencyDateTime(v.captured_at) ?? 'unknown'}
                    {v.last_confirmed_at && <> · still matched the page {formatCurrencyDate(v.last_confirmed_at)}</>}
                    {' '}· {v.char_count.toLocaleString()} chars
                    {v.truncated && ' (cut off at the size limit)'}
                    {' '}· {ORIGIN_LABEL[v.origin] ?? v.origin}
                    {' '}· <span title={`${v.content_hash_algorithm} ${v.content_hash}`} style={{ fontFamily: 'monospace' }}>{shortHash(v.content_hash)}</span>
                  </div>
                </div>
                <button type="button" style={buttonStyle} onClick={() => view(v)} disabled={busy !== null} aria-label={`View version ${v.number}`}>
                  {busy === `view:${v.uuid}` ? '…' : 'View'}
                </button>
                <button
                  type="button"
                  style={{ ...buttonStyle, opacity: prev ? 1 : 0.4, cursor: prev ? 'pointer' : 'default' }}
                  onClick={() => prev && compare(prev, v)}
                  disabled={!prev || busy !== null}
                  aria-label={`Changes in version ${v.number}`}
                  title={prev ? `What changed from version ${prev.number}` : 'The first recorded version'}
                >
                  {busy === `diff:${v.uuid}` ? '…' : 'Changes'}
                </button>
              </div>
            )
          })}
        </div>
      )}

      {panel && (
        <div style={{ marginTop: 10, border: '1px solid #2a2a2a', borderRadius: 6, overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', backgroundColor: '#1a1a1a', fontSize: 12, color: '#cbd5e1' }}>
            <div style={{ flex: 1 }}>
              {panel.kind === 'text'
                ? <>Version {panel.version.number} · in effect {effectiveRange(panel.version)}</>
                : panel.diff.identical
                  ? <>Version {panel.diff.base.number} → {panel.diff.target.number}: identical text</>
                  : <>Version {panel.diff.base.number} → {panel.diff.target.number}: {panel.diff.added} lines added, {panel.diff.removed} removed</>}
            </div>
            {panel.kind === 'text' && (
              <button type="button" style={{ ...buttonStyle, display: 'inline-flex', alignItems: 'center', gap: 4 }} onClick={() => downloadVersion(panel.version)}>
                <Download size={11} aria-hidden="true" /> Download
              </button>
            )}
            <button type="button" aria-label="Close version" onClick={() => setPanel(null)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#888', padding: 2 }}>
              <X size={14} aria-hidden="true" />
            </button>
          </div>
          <pre style={{
            margin: 0, padding: 10, maxHeight: 320, overflowY: 'auto',
            fontSize: 12, lineHeight: 1.55, color: '#d1d5db', backgroundColor: '#161616',
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          }}>
            {panel.kind === 'text'
              ? panel.version.content
              : panel.diff.lines.map((l, i) => (
                <div
                  key={i}
                  style={{
                    color: l.op === '+' ? '#86efac' : l.op === '-' ? '#fca5a5' : l.op === '@' ? '#888' : undefined,
                    backgroundColor: l.op === '+' ? 'rgba(34,197,94,0.10)' : l.op === '-' ? 'rgba(239,68,68,0.10)' : undefined,
                  }}
                >
                  {l.op === '@' ? l.text : `${l.op} ${l.text}`}
                </div>
              ))}
            {panel.kind === 'diff' && panel.diff.truncated && (
              <div style={{ color: '#fbbf24', marginTop: 6 }}>The diff is too long to show in full. View each version to read it all.</div>
            )}
          </pre>
        </div>
      )}
    </section>
  )
}
