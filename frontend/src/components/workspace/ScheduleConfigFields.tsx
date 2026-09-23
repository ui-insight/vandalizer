import { useEffect, useMemo, useState } from 'react'
import { CalendarClock, FileText, X } from 'lucide-react'
import { previewSchedule } from '../../api/automations'
import { CollapsibleSection } from '../shared/CollapsibleSection'
import { DocumentPickerDialog } from '../shared/DocumentPickerDialog'
import type { ScheduleFrequency, ScheduleTriggerConfig } from '../../types/automation'
import {
  WEEKDAYS, browserTimeZone, describeSchedule, formatRunTime, scheduleConfigPayload, timeZoneOptions,
} from '../../utils/schedule'

/**
 * The schedule trigger's settings — when it runs and what it runs on — plus
 * the next run times, so the person setting it can check it means what they
 * meant. Shared by the creation wizard and the automation editor. The next
 * runs come from the backend's own schedule computation, never re-derived
 * here, so the preview and the scheduler cannot disagree.
 */
export function ScheduleConfigFields({
  value,
  onChange,
  folders,
  foldersLoading = false,
  pickerZIndex,
  onPickerOpenChange,
  disabled = false,
}: {
  value: ScheduleTriggerConfig
  onChange: (next: ScheduleTriggerConfig) => void
  folders: { uuid: string; path: string }[]
  foldersLoading?: boolean
  /** Raise the document picker above a surrounding modal. */
  pickerZIndex?: number
  onPickerOpenChange?: (open: boolean) => void
  disabled?: boolean
}) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const zones = useMemo(timeZoneOptions, [])
  const ownZone = browserTimeZone()
  const set = (patch: Partial<ScheduleTriggerConfig>) => onChange({ ...value, ...patch })

  const openPicker = (open: boolean) => {
    setPickerOpen(open)
    onPickerOpenChange?.(open)
  }

  const docUuids = value.document_uuids ?? []
  const docTitles = value.document_titles ?? {}
  const folderPath = folders.find(f => f.uuid === value.folder_id)?.path
  const runsOnSummary = value.source === 'folder'
    ? (folderPath ? `${folderPath}${value.only_new ? ' · new documents only' : ''}` : 'No folder chosen')
    : `${docUuids.length} document${docUuids.length === 1 ? '' : 's'}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <CollapsibleSection title="When" summary={`${describeSchedule(value)} · ${value.timezone}`} testId="schedule-when">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 8 }}>
          <div role="radiogroup" aria-label="Frequency" style={{ display: 'flex', gap: 6 }}>
            {(['daily', 'weekly', 'monthly'] as ScheduleFrequency[]).map(f => (
              <button
                key={f}
                type="button"
                role="radio"
                aria-checked={value.frequency === f}
                disabled={disabled}
                onClick={() => set({ frequency: f })}
                style={segmentStyle(value.frequency === f)}
              >
                {f[0].toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {value.frequency === 'weekly' && (
              <label style={fieldLabel}>
                On
                <select
                  value={value.weekday ?? 0}
                  disabled={disabled}
                  onChange={e => set({ weekday: Number(e.target.value) })}
                  style={controlStyle}
                >
                  {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                </select>
              </label>
            )}
            {value.frequency === 'monthly' && (
              <label style={fieldLabel}>
                Day of month
                <select
                  value={value.day_of_month ?? 1}
                  disabled={disabled}
                  onChange={e => set({ day_of_month: Number(e.target.value) })}
                  style={controlStyle}
                >
                  {Array.from({ length: 28 }, (_, i) => i + 1).map(d => <option key={d} value={d}>{d}</option>)}
                </select>
              </label>
            )}
            <label style={fieldLabel}>
              At
              <input
                type="time"
                value={value.time}
                disabled={disabled}
                onChange={e => e.target.value && set({ time: e.target.value })}
                style={controlStyle}
              />
            </label>
            <label style={{ ...fieldLabel, flex: 1, minWidth: 180 }}>
              Time zone
              <select
                value={value.timezone}
                disabled={disabled}
                onChange={e => set({ timezone: e.target.value })}
                style={controlStyle}
              >
                {zones.map(z => (
                  <option key={z} value={z}>{z === ownZone ? `${z} (your time zone)` : z}</option>
                ))}
              </select>
            </label>
          </div>
          {value.frequency === 'monthly' && (
            <div style={{ fontSize: 12, color: '#6b7280' }}>
              Days 1–28 only, so the schedule runs in every month.
            </div>
          )}
        </div>
      </CollapsibleSection>

      <CollapsibleSection title="Runs on" summary={runsOnSummary} testId="schedule-runs-on">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 8 }}>
          <div role="radiogroup" aria-label="Runs on" style={{ display: 'flex', gap: 6 }}>
            <button type="button" role="radio" aria-checked={value.source === 'folder'} disabled={disabled}
              onClick={() => set({ source: 'folder' })} style={segmentStyle(value.source === 'folder')}>
              A folder
            </button>
            <button type="button" role="radio" aria-checked={value.source === 'documents'} disabled={disabled}
              onClick={() => set({ source: 'documents' })} style={segmentStyle(value.source === 'documents')}>
              Specific documents
            </button>
          </div>

          {value.source === 'folder' ? (
            <>
              {foldersLoading ? (
                <div style={{ fontSize: 13, color: '#6b7280' }}>Loading folders...</div>
              ) : (
                <select
                  aria-label="Folder"
                  value={value.folder_id ?? ''}
                  disabled={disabled}
                  onChange={e => set({ folder_id: e.target.value || undefined })}
                  style={{ ...controlStyle, width: '100%' }}
                >
                  <option value="">Select a folder</option>
                  {folders.map(f => <option key={f.uuid} value={f.uuid}>{f.path}</option>)}
                </select>
              )}
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, color: '#374151', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={!!value.only_new}
                  disabled={disabled}
                  onChange={e => set({ only_new: e.target.checked })}
                  style={{ width: 16, height: 16, marginTop: 1, accentColor: '#3b82f6' }}
                />
                <span>
                  <span style={{ fontWeight: 500 }}>Only documents added since the last run</span>
                  <span style={{ display: 'block', fontSize: 12, color: '#6b7280' }}>
                    The first run takes the whole folder; after that, each run takes only what is new. A run with nothing new is skipped.
                  </span>
                </span>
              </label>
            </>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {docUuids.map(uuid => (
                <div key={uuid} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#374151' }}>
                  <FileText aria-hidden="true" style={{ width: 14, height: 14, color: '#6b7280', flexShrink: 0 }} />
                  <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {docTitles[uuid] || uuid}
                  </span>
                  {!disabled && (
                    <button
                      type="button"
                      aria-label={`Remove ${docTitles[uuid] || 'document'}`}
                      onClick={() => {
                        const rest = { ...docTitles }
                        delete rest[uuid]
                        set({ document_uuids: docUuids.filter(u => u !== uuid), document_titles: rest })
                      }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 2, display: 'flex' }}
                    >
                      <X style={{ width: 14, height: 14 }} />
                    </button>
                  )}
                </div>
              ))}
              {!disabled && (
                <button type="button" onClick={() => openPicker(true)} style={addButtonStyle}>
                  {docUuids.length ? 'Add more documents' : 'Choose documents'}
                </button>
              )}
            </div>
          )}
        </div>
      </CollapsibleSection>

      <NextRuns config={value} ownZone={ownZone} />

      {pickerOpen && (
        <DocumentPickerDialog
          title="Documents to run on each time"
          excludeUuids={docUuids}
          zIndex={pickerZIndex}
          onClose={() => openPicker(false)}
          onSelect={docs => {
            const titles = { ...docTitles }
            for (const d of docs) titles[d.uuid] = d.title
            set({ document_uuids: [...docUuids, ...docs.map(d => d.uuid)], document_titles: titles })
            openPicker(false)
          }}
        />
      )}
    </div>
  )
}

/** Next run times, from the backend — with the viewer's local time when the zones differ. */
function NextRuns({ config, ownZone }: { config: ScheduleTriggerConfig; ownZone: string }) {
  const [runs, setRuns] = useState<string[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const key = JSON.stringify([config.frequency, config.time, config.weekday, config.day_of_month, config.timezone])

  useEffect(() => {
    let cancelled = false
    const t = setTimeout(() => {
      previewSchedule(scheduleConfigPayload(config))
        .then(r => { if (!cancelled) { setRuns(r.next_runs); setError(null) } })
        .catch(e => { if (!cancelled) { setRuns(null); setError(e instanceof Error ? e.message : 'Could not compute the next run') } })
    }, 250)
    return () => { cancelled = true; clearTimeout(t) }
    // Only the timing fields change the next run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const otherZone = config.timezone !== ownZone
  return (
    <div role="status" aria-live="polite" style={{
      display: 'flex', gap: 10, padding: '10px 12px', borderRadius: 8,
      backgroundColor: error ? '#fef2f2' : '#f0f9ff', border: `1px solid ${error ? '#fecaca' : '#bae6fd'}`,
    }}>
      <CalendarClock aria-hidden="true" style={{ width: 16, height: 16, color: error ? '#b91c1c' : '#0369a1', flexShrink: 0, marginTop: 2 }} />
      <div style={{ fontSize: 13, color: '#0f172a', minWidth: 0 }}>
        {error ? (
          <span style={{ color: '#b91c1c' }}>{error}</span>
        ) : !runs ? (
          <span style={{ color: '#6b7280' }}>Working out the next run…</span>
        ) : (
          <>
            <div>
              <span style={{ fontWeight: 600 }}>Next run: </span>
              {formatRunTime(runs[0], config.timezone)}
              {otherZone && <span style={{ color: '#6b7280' }}> · {formatRunTime(runs[0], ownZone)} your time</span>}
            </div>
            {runs.length > 1 && (
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                Then {runs.slice(1).map(r => formatRunTime(r, config.timezone)).join(', ')}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

const fieldLabel: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 4,
  fontSize: 12, fontWeight: 600, color: '#6b7280',
}

const controlStyle: React.CSSProperties = {
  padding: '8px 10px', fontSize: 13, fontFamily: 'inherit', fontWeight: 400,
  border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff', color: '#202124',
}

const addButtonStyle: React.CSSProperties = {
  alignSelf: 'flex-start', padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
  border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff', color: '#374151', cursor: 'pointer',
}

function segmentStyle(selected: boolean): React.CSSProperties {
  return {
    padding: '6px 14px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit', borderRadius: 6, cursor: 'pointer',
    border: selected ? '1.5px solid #3b82f6' : '1px solid #d1d5db',
    backgroundColor: selected ? '#eff6ff' : '#fff',
    color: selected ? '#1d4ed8' : '#374151',
  }
}
