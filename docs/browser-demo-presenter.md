# Show the browser capability from Vandalizer chat

The demo is a normal Skill you add to your account. It reads real public university pages; it has no separate website, service, scripted chat mode or seeded account.

1. Start on the chat home screen. In **Read from your websites**, choose **Learn more** (or **Connect this site** if the extension is already installed). Follow the four steps: Download, Install, Connect, and Try a Skill. The app detects connection automatically and retires the suggestion. You can also dismiss it. The guide stays available through the composer's **Settings**, near the top of Assistant settings. Returning connected users see a compact **Your browser is ready** summary; choose **Try a Skill** to open the last step.
2. Click **Add Skill to Library**, review its instructions in the existing Library editor, and click **Create Skill**. Alternatively download [browser-demo.json](../frontend/public/skills/browser-demo.json), open **Library → New → Skill**, and choose **Upload file**. This is a regular Library Skill: choose it for one chat, or add it to Core Skills in Assistant settings. Keep “Use your browser” on and allowed by your administrator; setup explains if it is off.
3. Open **University research snapshot** in Library and choose **Run Skill**. In Vandalizer chat, send **Run the research snapshot**.
4. Allow `www.uidaho.edu` when the extension asks. Chat opens the real page in its working tab, reads the figures and calls `record_value` once per figure. Point to the read-only site indicator. Expand **figures recorded** to show each value, source link and capture time; expand **Activity** for individual browser steps.
5. Show the final table in chat: each figure has its own page link and the reporting period, or “Not stated”. The Skill keeps figures from different pages separate rather than treating them as comparable growth.

The Skill uses [Rankings and fast facts](https://www.uidaho.edu/about/rankings-facts) and [UIdaho’s economic impact](https://www.uidaho.edu/about/thinking-big/economic-impact). It names labels and sections rather than hardcoding figures, so a new run reads the live pages. If a figure or page is unavailable it reports that instead of inventing a result.

For a demo against your own signed-in portals, copy the Skill in Library and change the URLs, search labels and figures. If sign-in is needed, chat offers **Open working tab**. Sign in yourself, return to Vandalizer and choose **Continue after sign-in**. Never put a password into the Skill or chat. The public example does not require sign-in or intentionally attempt a write on a real site. Password and write refusals are covered by automated tests.

A redirect to an unapproved site is shown as **Site permission needed**, separately from a detected sign-in page. Chat has not read the unapproved page. Complete sign-in yourself if needed, return to the allowed site, then choose **Check page and continue**. If the new site is necessary, chat must request its permission before reading. The extension menu shows the connected Vandalizer address and allowed sites, with **Open Vandalizer** to return to chat and **Open working tab** when a working tab is available.

## Visual review evidence

The November 18 polish pass was reviewed in real Chrome with the installed unpacked extension. The chat screenshot uses an existing successful account Skill run; this pass did not run a new LLM conversation or a live sign-in/write-refusal scenario. Automated tests cover connection states, permission denial, recovery messages, blocked actions, recorded sources and grouping. Edge has not been verified by hand.

- [Connected setup summary](browser-setup-evidence/setup-connected-summary.png)
- [Install instructions](browser-setup-evidence/setup-install.png)
- [Grouped chat activity and recorded sources](browser-setup-evidence/chat-browser-sources.png)
- [Connected extension popup](browser-setup-evidence/connected-popup.png)
- [Connection success page](browser-setup-evidence/connection-ready.png)
- [Connection page with Chrome dark-mode emulation](browser-setup-evidence/connection-dark.png)
- [Site permission layout preview](browser-setup-evidence/site-permission-preview.png) — rendered extension page, without granting a new permission

## Updating the extension download

After editing `chrome-extension/`, run `python3 scripts/package_browser_extension.py`. The deterministic zip is checked in so frontend-only container builds include it; `--check` verifies it matches source. No extension dependencies or build step are needed.

`VITE_BROWSER_STORE_URL` is a build-time option for a future store listing. Keep the manifest public key/extension ID stable, or update `EXTENSION_ID` in `browserSetup.ts`. Public discovery exposes presence/version only and cannot run commands or grant access. The extension popup derives the site address from the active tab; final permission is granted on a persistent extension page so Chrome cannot close the action popup mid-connection.
