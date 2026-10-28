import { FileText, Loader2, Check, AlertCircle } from 'lucide-react'
import { artifactContentUrl } from '../../api/artifacts'
import { PageActions, PagePreview } from './PagePrimitives'
import type { ApprovalRecord } from '../chat/approvalHistory'

export function ChatPageCard({ title, html, uuid, revision, warnings = [], running, saving, error, unconfirmed, canceled, needsApproval, history, decision, decisionError, onDecide, revising }: {
  title: string; html?: string; uuid?: string; revision?: string; running?: boolean; saving?: boolean; error?: string; unconfirmed?: boolean; canceled?: boolean
  warnings?: string[]
  needsApproval?: boolean; history?: ApprovalRecord; decision: 'approved' | 'canceled' | null; decisionError: string | null
  onDecide?: (decision: 'approved' | 'canceled') => void; revising: boolean
}) {
  const saved = !!uuid && !!revision && !running && !error && !needsApproval && !canceled
  const status = running ? (saving ? 'Saving your page' : 'Preparing your page preview') : error ? 'Page needs attention' : canceled ? 'Canceled' : unconfirmed ? 'Save not confirmed' : saved ? 'Page saved' : history ? history.label : decision === 'approved' ? 'Approval sent' : decision === 'canceled' ? 'Cancellation sent' : 'Ready for your review'
  const Icon = running ? Loader2 : saved ? Check : error ? AlertCircle : FileText
  return <section className="chat-page-card" aria-label={`Page: ${title}`}>
    <header className="chat-page-header"><span className="page-mark"><Icon size={20} className={running ? 'animate-spin' : undefined} aria-hidden="true" /></span><div><p role="status" className="page-eyebrow">{status}</p><h3>{title}</h3></div></header>
    {running && <div className="page-building"><div /><div /><div /><p>{saving ? 'Saving the approved page to your private Pages library.' : 'Preparing a preview for you to review before saving.'}</p></div>}
    {!running && !error && !canceled && (html || saved) && <div className="chat-page-footer">
      <p>Pages support static HTML and CSS. JavaScript charts, filters and table sorting are not supported.</p>
      {warnings.length > 0 && <div className="page-revision-note" role="alert"><strong>Some content was removed to keep this page safe.</strong>{warnings.map((warning, index) => <p key={index}>{warning}</p>)}</div>}
    </div>}
    {!running && !error && !canceled && (html || saved) && (history ? <details className="page-history-preview"><summary>View earlier preview</summary><PagePreview title={title} html={html} compact /></details> : <PagePreview title={title} html={needsApproval ? html : undefined} src={saved ? artifactContentUrl(uuid!, revision!) : undefined} compact />)}
    {saved && <footer className="chat-page-footer"><p>Saved in <a href="/?mode=files&files=pages">Files → Pages</a>. Use Share to manage access.</p><PageActions uuid={uuid!} revision={revision!} title={title} /></footer>}
    {needsApproval && <div className="chat-page-footer" role="region" aria-label={history ? 'Earlier action decision' : 'Review proposed action'}>
      {history ? <p>{history.detail}</p> : <><p>{revising ? 'Save a new version of this page. Any published version stays unchanged.' : 'Save this page to your private Pages library. You can share it later.'}</p>
        {decision && <p role="status">{decision === 'approved' ? 'Approval sent. Waiting for the saved page…' : 'Cancellation sent. Check the next response for confirmation.'}</p>}
        {!decision && onDecide && <div className="page-actions"><button type="button" className="page-button page-button-primary" onClick={() => onDecide('approved')}><Check size={16} />{revising ? 'Save new version' : 'Save page'}</button><button type="button" className="page-button" onClick={() => onDecide('canceled')}>Cancel action</button></div>}
        {!decision && !onDecide && <p>Continue from the latest reply to approve this page.</p>}
      </>}
      {decisionError && <p className="page-alert" role="alert">{decisionError}</p>}
    </div>}
    {(error || unconfirmed || canceled) && <p className="chat-page-footer" role={error ? 'alert' : undefined}>{error || (canceled ? 'This action was canceled. No successful save was reported.' : 'No saved page was returned. Ask the assistant to check its status before trying again.')}</p>}
  </section>
}
