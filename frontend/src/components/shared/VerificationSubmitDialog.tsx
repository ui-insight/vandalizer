import { useState } from 'react'
import { createPortal } from 'react-dom'
import { X, Send } from 'lucide-react'
import { submitForVerification } from '../../api/library'
import { useAuth } from '../../hooks/useAuth'

const CATEGORIES = [
  'Compliance & Regulatory',
  'Financial & Budgeting',
  'Research Administration',
  'Contracts & Legal',
  'Human Resources',
  'Operations & Logistics',
  'Data Extraction',
  'Document Review',
  'Other',
]

interface Props {
  itemKind: 'workflow' | 'search_set'
  itemId: string
  itemTitle?: string
  onClose: () => void
  onSuccess: () => void
}

export function VerificationSubmitDialog({ itemKind, itemId, itemTitle, onClose, onSuccess }: Props) {
  const { user } = useAuth()
  const [summary, setSummary] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [submitterOrg, setSubmitterOrg] = useState('')
  const [runInstructions, setRunInstructions] = useState('')
  const [knownLimitations, setKnownLimitations] = useState('')
  const [tagsInput, setTagsInput] = useState('')
  const [evaluationNotes, setEvaluationNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const kindLabel = itemKind === 'workflow' ? 'workflow' : 'extraction'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!summary.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const tags = tagsInput.split(',').map(t => t.trim()).filter(Boolean)
      await submitForVerification({
        item_kind: itemKind,
        item_id: itemId,
        submitter_name: user?.name || user?.email || undefined,
        submitter_org: submitterOrg.trim() || undefined,
        summary: summary.trim(),
        description: description.trim() || undefined,
        category: category || undefined,
        run_instructions: runInstructions.trim() || undefined,
        known_limitations: knownLimitations.trim() || undefined,
        evaluation_notes: evaluationNotes.trim() || undefined,
        intended_use_tags: tags.length ? tags : undefined,
      })
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '8px 12px',
    border: '1px solid #d1d5db', borderRadius: 8,
    fontSize: 13, fontFamily: 'inherit', outline: 'none',
    boxSizing: 'border-box',
  }
  const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 5,
  }
  const hintStyle: React.CSSProperties = {
    fontSize: 11, color: '#9ca3af', marginTop: 3,
  }

  const content = (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      backgroundColor: 'rgba(0,0,0,0.4)',
    }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: '#fff', borderRadius: 12, width: '100%', maxWidth: 560,
        maxHeight: '90vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(0,0,0,0.2)', margin: '0 16px',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '18px 24px 14px', borderBottom: '1px solid #e5e7eb',
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#111' }}>
              Submit to Public Library
            </div>
            {itemTitle && (
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                {itemTitle}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 4 }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ overflowY: 'auto', flex: 1 }}>
          <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <p style={{ fontSize: 12, color: '#6b7280', margin: 0, lineHeight: 1.5 }}>
              Your {kindLabel} will be reviewed by our team before appearing in the catalog. Providing context helps reviewers understand its purpose and intended use.
            </p>

            {/* Summary — required */}
            <div>
              <label style={labelStyle}>
                Summary <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <input
                type="text"
                value={summary}
                onChange={e => setSummary(e.target.value)}
                placeholder={`Briefly describe what this ${kindLabel} does`}
                required
                style={inputStyle}
              />
              <p style={hintStyle}>1–2 sentences shown in the catalog listing.</p>
            </div>

            {/* Category */}
            <div>
              <label style={labelStyle}>Category</label>
              <select
                value={category}
                onChange={e => setCategory(e.target.value)}
                style={{ ...inputStyle, backgroundColor: '#fff' }}
              >
                <option value="">Select a category...</option>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            {/* Two-column row: org + tags */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={labelStyle}>Your Organization</label>
                <input
                  type="text"
                  value={submitterOrg}
                  onChange={e => setSubmitterOrg(e.target.value)}
                  placeholder="e.g. University of Idaho"
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Tags</label>
                <input
                  type="text"
                  value={tagsInput}
                  onChange={e => setTagsInput(e.target.value)}
                  placeholder="e.g. NIH, grants, budget"
                  style={inputStyle}
                />
                <p style={hintStyle}>Comma-separated.</p>
              </div>
            </div>

            {/* Description */}
            <div>
              <label style={labelStyle}>Detailed Description</label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={3}
                placeholder="Any additional context about what this does, when to use it, etc."
                style={{ ...inputStyle, resize: 'vertical' }}
              />
            </div>

            {/* Run instructions */}
            <div>
              <label style={labelStyle}>How to Use It</label>
              <textarea
                value={runInstructions}
                onChange={e => setRunInstructions(e.target.value)}
                rows={2}
                placeholder="What kind of documents should this run against? Any setup required?"
                style={{ ...inputStyle, resize: 'vertical' }}
              />
            </div>

            {/* Known limitations */}
            <div>
              <label style={labelStyle}>Known Limitations</label>
              <textarea
                value={knownLimitations}
                onChange={e => setKnownLimitations(e.target.value)}
                rows={2}
                placeholder="Any edge cases, document types it struggles with, etc."
                style={{ ...inputStyle, resize: 'vertical' }}
              />
            </div>

            {/* Notes for examiner */}
            <div>
              <label style={labelStyle}>Notes for Reviewer</label>
              <textarea
                value={evaluationNotes}
                onChange={e => setEvaluationNotes(e.target.value)}
                rows={2}
                placeholder="Anything the reviewer should know when evaluating this submission"
                style={{ ...inputStyle, resize: 'vertical' }}
              />
            </div>

            {error && (
              <div style={{
                padding: '10px 14px', borderRadius: 8,
                background: '#fef2f2', border: '1px solid #fecaca',
                fontSize: 12, color: '#991b1b',
              }}>
                {error}
              </div>
            )}
          </div>

          {/* Footer */}
          <div style={{
            padding: '14px 24px', borderTop: '1px solid #e5e7eb',
            display: 'flex', justifyContent: 'flex-end', gap: 10, flexShrink: 0,
          }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '8px 18px', borderRadius: 8, border: '1px solid #d1d5db',
                background: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer', color: '#374151',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !summary.trim()}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '8px 20px', borderRadius: 8, border: 'none',
                background: '#111827', color: '#fff', fontSize: 13, fontWeight: 600,
                cursor: submitting || !summary.trim() ? 'not-allowed' : 'pointer',
                opacity: submitting || !summary.trim() ? 0.6 : 1,
              }}
            >
              <Send size={14} />
              {submitting ? 'Submitting...' : 'Submit for Review'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )

  return createPortal(content, document.body)
}
