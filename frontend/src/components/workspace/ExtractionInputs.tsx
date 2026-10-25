import { useState } from 'react'
import { FileText, Plus, X } from 'lucide-react'
import { DocumentPickerDialog } from '../shared/DocumentPickerDialog'
import { createPortal } from '../shared/panelPortal'

type InputDocument = { uuid: string; title: string }

export function ExtractionInputs({ documents, usesProjectFiles, combined, onCombinedChange, onAdd, onRemove }: {
  documents: InputDocument[]
  usesProjectFiles: boolean
  combined: boolean
  onCombinedChange: (value: boolean) => void
  onAdd: (documents: InputDocument[]) => void
  onRemove: (uuid: string) => void
}) {
  const [picking, setPicking] = useState(false)
  return <section className="extraction-inputs" aria-label="Extraction documents">
    <div className="extraction-input-heading">
      <div><strong><FileText size={15} aria-hidden="true" /> Documents</strong>
        <p>{documents.length ? `${documents.length} selected` : usesProjectFiles ? 'All project files will be used' : 'Choose the files to extract from'}</p>
      </div>
      <button type="button" onClick={() => setPicking(true)}><Plus size={14} aria-hidden="true" />{documents.length ? 'Add documents' : 'Choose documents'}</button>
    </div>
    {documents.length > 0 && <details className="extraction-selected-documents">
      <summary>{documents.length === 1 ? documents[0].title : `Review ${documents.length} selected documents`}</summary>
      <ul>{documents.map(doc => <li key={doc.uuid}><span>{doc.title}</span><button type="button" aria-label={`Remove ${doc.title} from extraction`} onClick={() => onRemove(doc.uuid)}><X size={14} aria-hidden="true" /></button></li>)}</ul>
      {usesProjectFiles && <p>Removing all selections uses all project files.</p>}
    </details>}
    {documents.length > 1 && <label className="extraction-combine">
      <input type="checkbox" checked={combined} onChange={event => onCombinedChange(event.target.checked)} />
      <span><strong>Combine input</strong><span>{combined ? 'One result from all selected documents together.' : 'Off: a separate result for each document.'}</span></span>
    </label>}
    {picking && createPortal(<DocumentPickerDialog title="Choose extraction documents" excludeUuids={documents.map(doc => doc.uuid)} onSelect={onAdd} onClose={() => setPicking(false)} />, document.body)}
  </section>
}
