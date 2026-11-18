import type { ToolCallInfo, ToolResultInfo } from '../../types/chat'
import { BrowserActivity } from './BrowserActivity'

function record(content: unknown): Record<string, unknown> {
  return content && typeof content === 'object' && !Array.isArray(content) ? content as Record<string, unknown> : {}
}
function safeUrl(value: unknown) {
  if (typeof value !== 'string') return undefined
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined } catch { return undefined }
}
export function capturedTime(value: unknown) {
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value))) return ''
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value))
}

export function BrowserRun({ calls, results, running = false }: { calls: ToolCallInfo[]; results: Map<string, ToolResultInfo>; running?: boolean }) {
  const entries = calls.map(call => ({ call, result: results.get(call.tool_call_id), value: record(results.get(call.tool_call_id)?.content) }))
  const browser = entries.filter(entry => entry.call.tool_name.startsWith('browser_'))
  const latest = browser.at(-1)
  const active = running && entries.some(entry => !entry.result)
  const figures = entries.filter(entry => entry.call.tool_name === 'record_value' && entry.value.recorded === true)
  const errors = entries.filter(entry => entry.value.error && entry !== latest)
  return <section className="browser-panel browser-run" aria-label="Browser activity">
    {latest && <BrowserActivity key={latest.call.tool_call_id} result={latest.value} active={active} />}
    {figures.length > 0 && <details className="browser-figures" open={browser.length === 0 || undefined}>
      <summary>{figures.length === 1 ? '1 figure recorded' : `${figures.length} figures recorded`} <span>Values and sources</span></summary>
      <div className="browser-figures-scroll" role="region" aria-label="Recorded figures" tabIndex={0}><table>
        <thead><tr><th scope="col">Figure</th><th scope="col">Recorded value</th><th scope="col">Source</th></tr></thead>
        <tbody>{figures.map(({ call, value }) => <tr key={call.tool_call_id}>
          <th scope="row">{String(value.label || 'Figure')}</th><td>{String(value.value || '')}</td>
          <td>{safeUrl(value.url) ? <a href={safeUrl(value.url)} target="_blank" rel="noreferrer">{String(value.page_title || new URL(String(value.url)).hostname)}</a> : 'Source unavailable'}
            {capturedTime(value.captured_at) && <time dateTime={String(value.captured_at)}>Captured {capturedTime(value.captured_at)}</time>}
          </td>
        </tr>)}</tbody>
      </table></div>
    </details>}
    {errors.map(({ call, value }) => <p key={call.tool_call_id} className="browser-run-notice"><strong>{String(value.error).startsWith('blocked_') ? 'Action blocked.' : 'Step needs attention.'}</strong> {String(value.message || value.error)}</p>)}
    {browser.length > 0 && <details className="browser-run-log"><summary>Activity · {browser.length} {browser.length === 1 ? 'step' : 'steps'}</summary><ol>{browser.map(({ call, result, value }) => {
      const page = record(value.page)
      return <li key={call.tool_call_id}>{!result ? running ? 'Working…' : 'No result received' : value.error ? String(value.message || value.error) : page.title ? <>Read {String(page.title)}{page.truncated === true && ' (part of page)'}</> : 'Browser step completed'}</li>
    })}</ol></details>}
  </section>
}
