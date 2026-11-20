const HINT = '<p class="print-hint">To save as PDF, use your browser’s Print (Ctrl+P or ⌘P) and choose Save as PDF.</p>'
const HINT_STYLE = '<style>.print-hint{font:13px sans-serif;color:#4b5563;background:#fef9c3;padding:8px 12px;border-radius:6px}@media print{.print-hint{display:none}}</style>'
const PRINT_ON_LOAD = '<script>addEventListener("load",function(){print()})</script>'

/**
 * *html* as a page that opens its own print dialog, and says how to print
 * it if a content policy stops that script.
 */
export function withPrintOnLoad(html: string): string {
  return html
    .replace('</head>', `${HINT_STYLE}</head>`)
    .replace(/<body([^>]*)>/, `<body$1>${HINT}`)
    .replace('</body>', `${PRINT_ON_LOAD}</body>`)
}

/**
 * Open *html* in a new tab that prints itself.
 *
 * The tab is opened with noopener so it runs in its own browsing context.
 * A tab the app opens and calls print() on shares the app's thread: while
 * its print dialog was open, every click in Vandalizer waited on it (support
 * ticket: "Export → PDF freezes the whole app until the PDF tab is closed").
 * A link click, unlike window.open, isn't stopped by a pop-up blocker.
 */
export function openPrintPage(html: string): void {
  const url = URL.createObjectURL(new Blob([withPrintOnLoad(html)], { type: 'text/html' }))
  const a = document.createElement('a')
  a.href = url
  a.target = '_blank'
  a.rel = 'noopener noreferrer'
  a.click()
  // The new tab reads the page from this URL as it loads.
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
