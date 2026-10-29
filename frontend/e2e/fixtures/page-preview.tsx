import { createRoot } from 'react-dom/client'
import { ChatPageCard } from '../../src/components/artifacts/ChatPageCard'
import '../../src/styles/pages.css'

// Exercise the actual review card and expanded dialog, without a login or LLM.
const html = `<!doctype html><html><head>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; frame-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<style>body{font:16px/1.6 sans-serif;padding:20px}section{margin-top:900px}a{display:inline-block;margin-right:20px}</style>
</head><body><h1 id="top">Budget dashboard</h1>
<nav><a href="#budget-table">Full budget table</a><a href="#source-notes">Source notes</a></nav>
<a href="#personnel">Personnel</a>
<section id="personnel"><h2>Personnel chart</h2><p>Personnel: $100,000</p><a href="#top">Back to top</a></section>
<section id="budget-table"><h2>Full budget table</h2><table><tr><th>Personnel</th><td>$100,000</td></tr></table><a href="#top">Back to top</a></section>
<section id="source-notes"><details><summary>Source notes</summary><p>Figures are in USD.</p></details><details><summary>Calculated summary</summary><p>Total: $100,000.</p></details></section>
<script>window.untrustedPreviewScriptRan = true</script>
</body></html>`

createRoot(document.getElementById('root')!).render(<main style={{ maxWidth: 900, margin: '30px auto' }}>
  <ChatPageCard title="Budget dashboard" html={html} needsApproval decision={null} decisionError={null} onDecide={() => {}} revising />
</main>)
