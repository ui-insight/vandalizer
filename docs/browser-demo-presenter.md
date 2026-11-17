# Show the browser capability from Vandalizer chat

The demo is a normal Skill you add to your account. It reads real public university pages; it has no separate website, service, scripted chat mode or seeded account.

1. Start on the chat home screen. In **Read from your websites**, choose **Learn more** (or **Connect this site** if the extension is already installed). Follow the four steps: Download, Install, Connect, and Try a Skill. The app detects connection automatically and retires the suggestion. You can also dismiss it. The guide stays available through the composer's **Settings**, near the top of Assistant settings.
2. Once connected, click **Add Skill to Library**, review its instructions in the existing Library editor, and click **Create Skill**. Alternatively download [browser-demo.json](../frontend/public/skills/browser-demo.json), open **Library → New → Skill**, and choose **Upload file**. This is a regular Library Skill: choose it for one chat, or add it to Core Skills in Assistant settings. Keep “Use your browser” on and allowed by your administrator; setup explains if it is off.
3. Open **University research snapshot** in Library and choose **Run Skill**. In Vandalizer chat, send **Run the research snapshot**.
4. Allow `www.uidaho.edu` when the extension asks. Chat opens the real page in its working tab, reads the figures and calls `record_value` once per figure. Point to the read-only site indicator and recorded source links.
5. Show the final table in chat: each figure has its own page link and the reporting period, or “Not stated”. The Skill keeps figures from different pages separate rather than treating them as comparable growth.

The Skill uses [Rankings and fast facts](https://www.uidaho.edu/about/rankings-facts) and [UIdaho’s economic impact](https://www.uidaho.edu/about/thinking-big/economic-impact). It names labels and sections rather than hardcoding figures, so a new run reads the live pages. If a figure or page is unavailable it reports that instead of inventing a result.

For a demo against your own signed-in portals, copy the Skill in Library and change the URLs, search labels and figures. If sign-in is needed, chat offers **Open working tab**. Sign in yourself, return to Vandalizer and choose **Continue after sign-in**. Never put a password into the Skill or chat. The public example does not require sign-in or intentionally attempt a write on a real site. Password and write refusals are covered by automated tests.

## Updating the extension download

After editing `chrome-extension/`, run `python3 scripts/package_browser_extension.py`. The deterministic zip is checked in so frontend-only container builds include it; `--check` verifies it matches source. No extension dependencies or build step are needed.

`VITE_BROWSER_STORE_URL` is a build-time option for a future store listing. Keep the manifest public key/extension ID stable, or update `EXTENSION_ID` in `browserSetup.ts`. Public discovery exposes presence/version only and cannot run commands or grant access. The extension popup derives the site address from the active tab; final permission is granted on a persistent extension page so Chrome cannot close the action popup mid-connection.
