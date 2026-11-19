/**
 * What the browser card says about a step that did not go through.
 *
 * A tool result's `message` is written for the model ("Call browser_open…",
 * "Read the page again and copy the value exactly"), so the card never prints
 * it. Every error code gets wording for the person here; a code this file
 * doesn't know gets the general line.
 */

type Result = Record<string, unknown>

const text = (value: unknown) => typeof value === 'string' ? value.trim() : ''

/** Refusals: a rule stopped chat. Later steps succeeding doesn't undo that, so the notice stays. */
export function isBrowserRefusal(error: string) {
  return error.startsWith('blocked_') || ['browser_request_blocked', 'site_not_allowed', 'site_not_allowed_by_admin', 'vandalizer_itself'].includes(error)
}

const CONTROL = 'Chat could not use a control on the page. The page may have changed since chat read it.'
const UNREAD = 'Chat could not read the page. Check the working tab before continuing.'

export function browserMessage(result: Result, args: Result = {}): string {
  const error = text(result.error)
  const site = text(result.site)
  if (error.startsWith('blocked_')) return 'This control could change something on the site. Chat stopped without using it.'
  switch (error) {
    case 'browser_request_blocked': {
      const reason = text(result.reason)
      return `Vandalizer did not use the browser for this request${reason ? `: ${reason}` : '.'}`
    }
    case 'vandalizer_itself':
      return 'Chat’s browser can’t be used on Vandalizer itself, so chat did not open or read it.'
    case 'site_not_allowed_by_admin':
      return `${site || 'This site'} is not on the list of sites your Vandalizer administrator allows, so chat did not read it.`
    case 'site_not_allowed':
      return `You haven’t allowed ${site || 'this site'}, so chat did not open or read it.`
    case 'unapproved_site':
      return 'The working tab moved to a site you haven’t allowed, so chat did not read it.'
    case 'page_address_not_checked':
      return 'The working tab moved to a page Vandalizer could not check, so chat did not read it. If it is a sign-in page, sign in there yourself, then continue.'
    case 'browser_needs_approval':
      return `Chat needs your approval before it uses the browser${site ? ` on ${site}` : ''}. Ask it to open the site and you’ll get an approval card.`
    case 'browser_not_connected':
    case 'extension_unavailable':
    case 'browser_unavailable':
    case 'not_allowed':
      return 'Your browser was not connected to this Vandalizer site. Reconnect it in Assistant settings.'
    case 'browser_timeout':
      return 'The browser did not answer in time. Check that the working tab is still open and that no permission window is waiting.'
    case 'no_open_page':
      return 'The working tab was closed. Ask chat to open the site again.'
    case 'bad_url':
      return 'Chat tried an address that is not a web page, so nothing was opened.'
    case 'value_not_on_page': {
      const value = text(args.value)
      return `Chat could not find ${value ? `“${value}”` : 'a value'} on the pages it read, so it was not recorded.`
    }
    case 'read_the_page_first':
    case 'stale_ref':
    case 'not_a_text_field':
    case 'not_a_dropdown':
    case 'option_not_found':
      return CONTROL
    default:
      return UNREAD
  }
}
