import { useCallback, useEffect, useState } from 'react'
import { FileText, Loader2, Mail, X } from 'lucide-react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { fetchAwardHighlights, type AwardHighlightFact, type AwardHighlights } from '../../api/files'
import { quoteSearchTerms } from '../../api/obligations'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useToast } from '../../contexts/ToastContext'
import { composeHighlightsEmail, mailtoUrl, MAILTO_SAFE_LENGTH, NOT_FOUND } from '../../lib/awardHighlightsEmail'

const CAVEAT: Record<string, string> = {
  unassessed: 'Passage found, value not checked',
  quote_unsupported: 'Not confirmed by the passage',
}

function open(url: string) { window.location.href = url }

/** Email highlights to PI (support ticket #1200). Reads a fixed set of facts
 * from one award document, shows each with the page it came from, and offers
 * an editable draft. The person sends it from their own mail program;
 * Vandalizer sends nothing. */
export function AwardHighlightsDialog({ docUuid, docTitle, onClose, openUrl = open }: {
  docUuid: string
  docTitle: string
  onClose: () => void
  /** Test seam for opening the mail program. */
  openUrl?: (url: string) => void
}) {
  const { viewDocument } = useWorkspace()
  const { toast } = useToast()
  const [data, setData] = useState<AwardHighlights | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [chosen, setChosen] = useState<number | null>(null)
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [bodyEdited, setBodyEdited] = useState(false)
  // Opening a source shows the document behind this dialog, so the dialog
  // steps aside without losing the draft.
  const [minimized, setMinimized] = useState(false)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    fetchAwardHighlights(docUuid)
      .then(result => {
        if (cancelled) return
        const pi = result.suggested_pi === null ? null : result.pis[result.suggested_pi] ?? null
        const draft = composeHighlightsEmail(result, pi)
        setData(result)
        setChosen(pi ? result.suggested_pi : null)
        // Pre-filled only with an address found in the document; otherwise empty.
        setTo(pi?.email ?? '')
        setSubject(draft.subject)
        setBody(draft.body)
        setBodyEdited(false)
      })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not read the document') })
    return () => { cancelled = true }
  }, [docUuid, attempt])

  const choose = useCallback((index: number) => {
    if (!data) return
    const pi = data.pis[index]
    setChosen(index)
    setTo(pi.email ?? '')
    // Keep the reader's edits; only an untouched draft is rewritten for the new PI.
    if (!bodyEdited) setBody(composeHighlightsEmail(data, pi).body)
  }, [data, bodyEdited])

  const showSource = (fact: AwardHighlightFact) => {
    viewDocument(docUuid, docTitle, {
      terms: fact.quote ? [quoteSearchTerms(fact.quote)] : [], page: fact.page,
      pageApproximate: fact.page_approximate,
    })
    setMinimized(true)
  }

  const copy = () => {
    const text = `To: ${to}\nSubject: ${subject}\n\n${body}`
    void navigator.clipboard.writeText(text)
      .then(() => toast('Draft copied', 'success'))
      .catch(() => toast('Could not copy the draft. Select the text to copy it.', 'error'))
  }

  if (minimized) {
    return (
      <div className="fixed bottom-4 right-4 flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-lg" style={{ zIndex: 700 }} role="region" aria-label="Email draft">
        <Mail className="h-4 w-4 text-gray-500" aria-hidden="true" />
        <button type="button" className="text-sm font-medium text-gray-900 underline" onClick={() => setMinimized(false)}>Back to email draft</button>
        <button type="button" onClick={onClose} aria-label="Discard email draft" className="text-gray-500 hover:text-gray-700"><X className="h-4 w-4" /></button>
      </div>
    )
  }

  const pi = data && chosen !== null ? data.pis[chosen] : null
  const mustChoose = !!data && data.pis.length > 1 && chosen === null
  const tooLong = mailtoUrl(to, subject, body).length > MAILTO_SAFE_LENGTH

  const factRow = (fact: AwardHighlightFact) => (
    <li key={fact.key} className="py-2 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div style={{ minWidth: 0 }}>
          <span className="font-medium text-gray-900">{fact.label}: </span>
          {fact.value
            ? <span className="text-gray-800" style={{ wordBreak: 'break-word' }}>{fact.value}</span>
            : <span className="italic text-gray-500">{NOT_FOUND}</span>}
          {fact.value && fact.support && CAVEAT[fact.support] && <div className="text-xs text-amber-700">{CAVEAT[fact.support]}. Check the source.</div>}
        </div>
        {fact.value && (
          <button type="button" onClick={() => showSource(fact)} title={fact.quote ?? undefined}
            aria-label={`Open the source of ${fact.label}${fact.page ? `, page ${fact.page}` : ''}`}
            className="inline-flex shrink-0 items-center gap-1 rounded border border-gray-200 px-1.5 py-0.5 text-xs text-gray-700 hover:bg-gray-50">
            <FileText className="h-3 w-3" aria-hidden="true" />{fact.page ? `p. ${fact.page_approximate ? '~' : ''}${fact.page}` : 'Source'}
          </button>
        )}
      </div>
    </li>
  )

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/50" style={{ zIndex: 700 }}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="award-highlights-title"
          style={{ maxHeight: '90vh', overflowY: 'auto' }}>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h3 id="award-highlights-title" className="text-lg font-medium text-gray-900">Email highlights to PI</h3>
              <div className="text-sm text-gray-500" style={{ wordBreak: 'break-word' }}>{docTitle}</div>
            </div>
            <button onClick={onClose} aria-label="Close dialog" className="shrink-0 text-gray-500 hover:text-gray-600"><X className="h-5 w-5" /></button>
          </div>

          {error && (
            <div role="alert" className="text-sm text-red-700">
              {error}{' '}
              <button type="button" className="font-medium underline" onClick={() => setAttempt(n => n + 1)}>Try again</button>
            </div>
          )}
          {!data && !error && (
            <div role="status" className="flex items-center gap-2 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />Reading the document for its highlights. This can take a minute.
            </div>
          )}

          {data && (
            <>
              <section aria-labelledby="award-highlights-facts">
                <h4 id="award-highlights-facts" className="text-sm font-semibold text-gray-900">What was found</h4>
                <ul className="divide-y divide-gray-100">
                  {data.facts.map(factRow)}
                  {data.contacts.map(factRow)}
                </ul>
              </section>

              <section className="mt-4" aria-labelledby="award-highlights-draft">
                <h4 id="award-highlights-draft" className="text-sm font-semibold text-gray-900">Email draft</h4>

                {data.pis.length === 0 && <p className="mt-1 text-sm text-gray-600">No principal investigator was found in this document. Enter the address yourself.</p>}
                {data.pis.length > 1 && (
                  <fieldset className="mt-2">
                    <legend className="text-sm text-gray-700">
                      {mustChoose
                        ? 'This document names two principal investigators. Choose who this goes to.'
                        : data.suggestion_reason === 'your_institution' && chosen === data.suggested_pi
                          ? 'This document names two principal investigators. The one at your institution is selected.'
                          : 'This document names two principal investigators.'}
                    </legend>
                    {data.pis.map((option, index) => (
                      <label key={option.role} className="mt-1 flex items-start gap-2 text-sm text-gray-800">
                        <input type="radio" name="award-highlights-pi" className="mt-1" checked={chosen === index} onChange={() => choose(index)} />
                        <span>{option.name.value}{option.institution.value ? `, ${option.institution.value}` : ''} <span className="text-gray-500">({option.role_label})</span></span>
                      </label>
                    ))}
                  </fieldset>
                )}

                <label className="mt-3 block text-sm font-medium text-gray-700" htmlFor="award-highlights-to">To</label>
                <input id="award-highlights-to" type="email" value={to} onChange={e => setTo(e.target.value)}
                  aria-describedby="award-highlights-to-help"
                  className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" />
                <p id="award-highlights-to-help" className="mt-1 text-xs text-gray-500">
                  {pi?.email
                    ? `From the document${pi.email_source.page ? `, p. ${pi.email_source.page}` : ''}. Check it before sending.`
                    : pi
                      ? `No email address for ${pi.name.value} was found in the document. Enter it yourself.`
                      : 'Left empty: no address was found for a recipient.'}
                </p>

                <label className="mt-3 block text-sm font-medium text-gray-700" htmlFor="award-highlights-subject">Subject</label>
                <input id="award-highlights-subject" value={subject} onChange={e => setSubject(e.target.value)}
                  className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 text-sm" />

                <label className="mt-3 block text-sm font-medium text-gray-700" htmlFor="award-highlights-body">Message</label>
                <textarea id="award-highlights-body" value={body} rows={14}
                  onChange={e => { setBody(e.target.value); setBodyEdited(true) }}
                  className="mt-1 w-full rounded border border-gray-300 px-2 py-1.5 font-mono text-xs" />
              </section>

              <p className="mt-3 text-xs text-gray-600">
                Vandalizer does not send this email. Review it, then open it in your email app or copy it and send it yourself.
                {tooLong && ' This draft is long: if your email app cuts it short, use Copy draft instead.'}
              </p>
              <div className="mt-3 flex justify-end gap-2">
                <button type="button" onClick={copy} className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-800 hover:bg-gray-50">Copy draft</button>
                <button type="button" disabled={mustChoose} onClick={() => openUrl(mailtoUrl(to, subject, body))}
                  title={mustChoose ? 'Choose who this goes to first' : undefined}
                  className="inline-flex items-center gap-1.5 rounded bg-highlight px-3 py-1.5 text-sm font-medium text-highlight-text hover:bg-highlight-hover disabled:cursor-not-allowed disabled:opacity-50">
                  <Mail className="h-4 w-4" aria-hidden="true" />Open in email app
                </button>
              </div>
            </>
          )}
        </div>
      </FocusTrap>
    </div>
  )
}
