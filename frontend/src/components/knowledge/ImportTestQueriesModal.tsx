import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { Upload, X, FileSpreadsheet, Download, Loader2 } from 'lucide-react'
import { importKBTestQueries, type KBTestQueryImportResult } from '../../api/knowledge'

interface Props {
  kbUuid: string
  onImported: () => void
  onClose: () => void
}

const TEMPLATE_CSV = [
  'Question,Expected Answer,Category,Source or Section,Notes,ID',
  '"What is the indirect cost rate for on-campus research?","52% of modified total direct costs",factual,"Rate Agreement FY26","Verify against the current rate agreement",RATE-001',
  '"Who approves a subaward budget revision?","The Federal awarding agency, per 2 CFR 200.308",factual,"Subpart D-ii — Procurement; Subpart E — Cost Principles","Two sources in one cell: separate them with a semicolon",SUB-002',
].join('\n')

function downloadTemplate() {
  const blob = new Blob([TEMPLATE_CSV], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'test-query-import-template.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function ImportTestQueriesModal({ kbUuid, onImported, onClose }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<KBTestQueryImportResult | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const pickFile = (f: File | undefined | null) => {
    if (!f) return
    setError(null)
    setResult(null)
    setFile(f)
  }

  const handleImport = async () => {
    if (!file) return
    setImporting(true)
    setError(null)
    try {
      const res = await importKBTestQueries(kbUuid, file)
      setResult(res)
      if (res.created > 0 || res.updated > 0) onImported()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setImporting(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Import test queries"
        style={{
          width: 480, padding: 20, backgroundColor: '#1f1f1f',
          border: '1px solid #2e2e2e', borderRadius: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Upload size={16} style={{ color: '#0ea5e9' }} aria-hidden="true" />
          <h3 style={{ margin: 0, fontSize: 15, color: '#fff' }}>Import test queries</h3>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ marginLeft: 'auto', background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: '#888' }}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        <div style={{ fontSize: 12, color: '#aaa', marginBottom: 12 }}>
          Upload a CSV or Excel (.xlsx) file with a <strong>Question</strong> column;
          Expected Answer, Category, Source or Section, Notes, and ID columns are
          optional. Rows whose ID matches a previously imported question update it
          instead of creating a duplicate — re-import the same sheet as your KB evolves.
          To list several sources in one cell, separate them with{' '}
          <strong>semicolons</strong>. A cell with no semicolon is split on commas, so a
          source name that itself contains one is best written with the semicolon form —
          in a CSV, quoting the cell does not protect it, because the quotes are consumed
          when the file is parsed.
        </div>

        <button
          type="button"
          onClick={downloadTemplate}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 12,
            padding: 0, background: 'transparent', border: 'none', cursor: 'pointer',
            fontSize: 12, color: '#0ea5e9', fontFamily: 'inherit',
          }}
        >
          <Download size={12} aria-hidden="true" />
          Download CSV template
        </button>

        {/* Drop zone / picker */}
        <div
          role="button"
          tabIndex={0}
          aria-label="Choose a file to import"
          onClick={() => inputRef.current?.click()}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click() }}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => {
            e.preventDefault()
            setDragOver(false)
            pickFile(e.dataTransfer.files?.[0])
          }}
          style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
            padding: '22px 12px', marginBottom: 12, cursor: 'pointer',
            backgroundColor: dragOver ? 'rgba(14,165,233,0.08)' : '#262626',
            border: `1px dashed ${dragOver ? '#0ea5e9' : '#3a3a3a'}`, borderRadius: 8,
          }}
        >
          <FileSpreadsheet size={20} style={{ color: file ? '#22c55e' : '#666' }} aria-hidden="true" />
          <div style={{ fontSize: 12, color: file ? '#e5e5e5' : '#888', textAlign: 'center' }}>
            {file ? file.name : 'Drop a .csv or .xlsx file here, or click to browse'}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx"
            style={{ display: 'none' }}
            onChange={e => {
              pickFile(e.target.files?.[0])
              e.target.value = ''
            }}
          />
        </div>

        {error && (
          <div role="alert" style={{
            padding: '8px 10px', marginBottom: 12, fontSize: 12, color: '#fca5a5',
            backgroundColor: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: 6, whiteSpace: 'pre-wrap',
          }}>
            {error}
          </div>
        )}

        {result && (
          <div role="status" style={{
            padding: '8px 10px', marginBottom: 12, fontSize: 12, color: '#e5e5e5',
            backgroundColor: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.3)',
            borderRadius: 6,
          }}>
            <div>
              Imported: <strong>{result.created}</strong> created,{' '}
              <strong>{result.updated}</strong> updated
              {result.skipped > 0 && <>, {result.skipped} skipped (already in the set)</>}
              {' '}of {result.total_rows} rows.
            </div>
            {result.errors.length > 0 && (
              <div style={{ marginTop: 6, color: '#fbbf24' }}>
                {result.errors.length} row{result.errors.length === 1 ? '' : 's'} could not be imported:
                <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                  {result.errors.slice(0, 8).map(e => (
                    <li key={e.row}>Row {e.row}: {e.error}</li>
                  ))}
                  {result.errors.length > 8 && <li>…and {result.errors.length - 8} more</li>}
                </ul>
              </div>
            )}
            {(result.unmatched_source_labels?.length ?? 0) > 0 && (
              <div style={{ marginTop: 6, color: '#fbbf24' }}>
                {result.unmatched_source_labels!.length} source label
                {result.unmatched_source_labels!.length === 1 ? '' : 's'} match no source in
                this knowledge base. Questions using them always score 0 retrieval
                precision, which pulls the run score down for a naming mismatch rather
                than a retrieval problem — rename them to match a source, or clear them:
                <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                  {result.unmatched_source_labels!.slice(0, 8).map(u => (
                    <li key={u.label}>
                      "{u.label}" — {u.questions} question{u.questions === 1 ? '' : 's'}
                    </li>
                  ))}
                  {result.unmatched_source_labels!.length > 8 && (
                    <li>…and {result.unmatched_source_labels!.length - 8} more</li>
                  )}
                </ul>
              </div>
            )}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" onClick={onClose} style={{
            padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            color: '#aaa', background: 'transparent', border: '1px solid #333',
            borderRadius: 6, cursor: 'pointer',
          }}>
            {result ? 'Done' : 'Cancel'}
          </button>
          <button
            type="button"
            onClick={handleImport}
            disabled={!file || importing}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
              color: '#fff', backgroundColor: !file || importing ? '#134e6b' : '#0ea5e9',
              border: '1px solid #0ea5e9', borderRadius: 6,
              cursor: !file || importing ? 'not-allowed' : 'pointer',
              opacity: !file || importing ? 0.7 : 1,
            }}
          >
            {importing && <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />}
            {importing ? 'Importing…' : 'Import'}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
