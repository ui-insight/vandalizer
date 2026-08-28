import { ListPlus } from 'lucide-react'

/**
 * What the Validate tab shows for an extraction that has no fields yet.
 * Tuning, test cases, cross-field rules and detailed validation all score
 * fields; with none defined a "Validate & improve" run could only fail
 * (support ticket: it ran for a few seconds, then "Optimization failed - No
 * extraction fields defined"). So the tab says what to do first and offers
 * the one action that unblocks it, instead of five controls that can't work.
 */
export function ExtractionNeedsFieldsNotice({
  savedTestCaseCount = 0,
  canManage = true,
  onAddFields,
}: {
  /** Test cases already saved for this extraction — kept, and usable once fields exist. */
  savedTestCaseCount?: number
  canManage?: boolean
  /** Jump to where fields are added (the Design tab). */
  onAddFields?: () => void
}) {
  return (
    <div
      role="status"
      data-testid="extraction-needs-fields"
      style={{
        border: '1px dashed #d1d5db', borderRadius: 8, padding: 20,
        backgroundColor: '#fafafa', display: 'flex', gap: 14, alignItems: 'flex-start',
      }}
    >
      <div style={{
        width: 36, height: 36, borderRadius: 8, backgroundColor: '#eef2ff', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <ListPlus style={{ width: 18, height: 18, color: '#4f46e5' }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', marginBottom: 4 }}>
          Add fields first
        </div>
        <div style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.6 }}>
          Validation scores how well each field is extracted, so this extraction needs at least one
          field before <strong>Validate &amp; improve</strong>, test cases, cross-field rules or detailed
          validation have anything to work against.
          {savedTestCaseCount > 0 && (
            <> {savedTestCaseCount} saved test case{savedTestCaseCount === 1 ? '' : 's'} will be ready to use as soon as a field exists.</>
          )}
        </div>
        {canManage && onAddFields && (
          <button
            type="button"
            onClick={onAddFields}
            style={{
              marginTop: 12, display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              borderRadius: 6, border: 'none', cursor: 'pointer',
              backgroundColor: 'var(--highlight-color, #eab308)', color: 'var(--highlight-text-color, #000)',
            }}
          >
            <ListPlus style={{ width: 14, height: 14 }} />
            Add fields on the Design tab
          </button>
        )}
        {!canManage && (
          <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 8 }}>
            You can view this extraction but not edit it — ask its owner to add fields.
          </div>
        )}
      </div>
    </div>
  )
}
