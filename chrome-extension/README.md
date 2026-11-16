# Vandalizer Browser (Chrome extension)

Lets Vandalizer chat read sites in the person's own Chrome, signed in as them, so a Skill can collect figures from portals that have no API: financial systems, sponsor portals, payment systems.

It only reads. It refuses to click anything labelled like a change (submit, save, approve, send, delete, pay, log out and similar), never types into password fields, and can open only the sites the person allowed.

## How it works

```
Chat page (Vandalizer tab)                 Vandalizer backend
  │  tool_call chunk: browser_open {...}  ◀──  agent calls browser_open, waits (Redis)
  │  → content/bridge.js → service worker
  │       opens / reads the working tab
  │  POST /api/chat/browser-results   ──▶  tool gets the page, agent continues
```

- `content/bridge.js` is injected only into the Vandalizer address set in the popup. It passes chat's browser tool calls to the service worker and returns the answers.
- `background/service-worker.js` keeps one working tab next to the chat tab and runs `background/page-tools.js` in it.
- `browser_read` returns the page as text with numbered controls (`[12] button "Search"`). Same-origin frames are read; frames from other sites are not.
- A site the person has not allowed opens `permission/permission.html`, where they click Allow (Chrome then confirms). Allowed sites are listed and removable in the popup.
- If a redirect lands on a site that was not allowed (single sign-on, for example), the extension won't read or act there. Chat asks the person to sign in in that tab and say when they're done.
- In chat, `record_value` accepts a figure only if it appears on a page read that turn, and records the URL and time with it.

## Install (development)

1. `chrome://extensions` → turn on **Developer mode** → **Load unpacked** → choose this `chrome-extension/` folder.
2. Click the extension icon, enter your Vandalizer address (for example `http://localhost:5173` or `https://vandalizer.example.edu`), and click **Connect**.
3. Reload the Vandalizer tab. Chat offers the browser tools while the extension is connected. They appear under **Use your browser** on the Assistant page, where people or admins can switch them off.

Edge accepts the same unpacked folder (`edge://extensions`).

## Example Skill

Save this as a Skill in the Library and run it from chat:

> **Monthly award burn check**
>
> When to use: checking spending and remaining balance on one or more awards.
>
> For each award number the person gives:
> 1. Open https://finance.example.edu/awards, type the award number in the search field, and click Search.
> 2. Open the award, then its Financials tab. Record "Expenditures to date" and "Remaining balance" with record_value.
> 3. Open https://sponsor-portal.example.gov and find the award's drawdown total. Record it.
>
> If a page asks for a sign-in, stop and ask the person to sign in in the Vandalizer tab.
> Finish with one table: award, expenditures to date, remaining balance, drawdown total, and the page each figure came from. Use calculate for any differences. Do not report a figure you did not record.
