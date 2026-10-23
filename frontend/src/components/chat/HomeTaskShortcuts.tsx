import { useId, useState } from 'react'
import { Calculator, ClipboardList, FileSearch, FileText } from 'lucide-react'
import { FocusTrap } from '../shared/PanelFocusTrap'

const TASKS = [
  { title: 'Review a solicitation', description: 'Eligibility, deadlines & materials', icon: FileSearch, prompt: 'Review the selected solicitation. Identify eligibility, deadlines with time zones, required materials, and submission instructions. Cite the source passages and flag missing or ambiguous information.' },
  { title: 'Summarize an award', description: 'Funding, terms & next steps', icon: FileText, prompt: 'Summarize the selected award notice: funding, project period, reporting requirements, restrictions, and next actions. Cite the source passages and distinguish explicit requirements from your interpretation.' },
  { title: 'Check a budget', description: 'Totals, rates & limits', icon: Calculator, prompt: 'Review the selected budget. Check totals, units, rates, and stated limits against the supplied evidence. Show the arithmetic, cite sources, and identify any missing rules or documents needed to finish the review.' },
  { title: 'Find requirements', description: 'Required actions & sources', icon: ClipboardList, prompt: 'Find the requirements in the selected document. Group required actions and materials, identify responsible parties and deadlines where stated, and cite each source passage. Flag ambiguities and missing information.' },
]

export interface TaskDocument { uuid: string; title: string }

export function HomeTaskShortcuts({ documents, disabled, onPrepare, onChooseDocuments, onHide }: {
  documents: TaskDocument[]
  disabled?: boolean
  onPrepare: (prompt: string, document?: TaskDocument) => void
  onChooseDocuments?: () => void
  /** Hides the starters on this browser; "More ways to work" brings them back. */
  onHide?: () => void
}) {
  const descriptionId = useId()
  const [task, setTask] = useState<(typeof TASKS)[number] | null>(null)
  const [documentUuid, setDocumentUuid] = useState('')
  const selected = documents.find(doc => doc.uuid === documentUuid)
  const prepare = (chooseInFiles = false) => {
    if (!task || (!chooseInFiles && !selected)) return
    onPrepare(task.prompt, chooseInFiles ? undefined : selected)
    setTask(null)
    if (chooseInFiles) onChooseDocuments?.()
  }
  return <section className="home-tasks" aria-label="Start an RA task">
    <div className="home-section-heading"><h3>Start a task</h3>{onHide && <button type="button" className="home-text-action" onClick={onHide} aria-label="Hide task starters. You can show them again under More ways to work.">Hide</button>}</div>
    <div className="home-task-buttons">{TASKS.map((item, index) => <button type="button" key={item.title} aria-label={item.title} aria-describedby={`${descriptionId}-${index}`} disabled={disabled} onClick={() => { setDocumentUuid(''); setTask(item) }}>
      <item.icon size={20} aria-hidden="true" />
      <strong>{item.title}</strong>
      <span id={`${descriptionId}-${index}`}>{item.description}</span>
    </button>)}</div>
    {task && <div className="home-task-overlay" onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); setTask(null) } }}>
      <FocusTrap focusTrapOptions={{ escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div role="dialog" aria-modal="true" aria-labelledby="home-task-title" aria-describedby="home-task-description" className="home-task-dialog">
          <h2 id="home-task-title">{task.title}</h2>
          <p id="home-task-description">Choose a source and prepare an editable request. Your existing draft is kept. Send the request when you are ready.</p>
          {documents.length > 0 ? <>
            <label htmlFor="home-task-document">Recent readable documents</label>
            <select id="home-task-document" value={documentUuid} onChange={e => setDocumentUuid(e.target.value)}>
              <option value="">Choose a document</option>
              {documents.map(doc => <option key={doc.uuid} value={doc.uuid}>{doc.title}</option>)}
            </select>
          </> : <p>No recent readable documents are available. Choose or upload a source in Files.</p>}
          <details><summary>Preview request</summary><p>{task.prompt}</p></details>
          <div className="home-task-actions">
            <button type="button" disabled={!selected || disabled} onClick={() => prepare()}>Prepare request</button>
            {onChooseDocuments && <button type="button" disabled={disabled} onClick={() => prepare(true)}>Choose a source in Files</button>}
            <button type="button" onClick={() => setTask(null)}>Cancel</button>
          </div>
        </div>
      </FocusTrap>
    </div>}
  </section>
}
