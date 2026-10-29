# Pages

Implementation for [roadmap #1059](https://github.com/ui-insight/vandalizer/issues/1059). This first release hosts self-contained **static HTML/CSS pages**. It does not execute authored JavaScript, host server applications, load remote assets, or install Skill scripts.

## Creating and reviewing

- In chat, choose **Export → Save transcript as page** for a message or conversation. This preserves the same transcript, source references, and warnings as HTML export.
- Ask the Assistant to create an HTML report/page. `create_html_artifact` shows a sandboxed preview and uses the existing prior-turn approval gate before saving. `get_html_artifact` and `revise_html_artifact` support natural-language edits. The approval identity includes the exact proposed content hash and base revision; changing either requires another preview.
- In a completed workflow, choose **Save as page**. The workflow output settings also offer **Create a private page after each completed run**. Manual and passive runs use the same page service. Repeated saves for the same owner/run return the existing page. If that page was deleted, **Save as page** creates a new private page from the stored run output, with a new page ID and no inherited sharing. The deleted page and its links stay unavailable. Automatic delivery retries do not recreate deleted pages; they can reuse a replacement that was explicitly saved. Delivery failures are recorded on the run; its completed output remains available for inspection and manual saving.
- Open **Files → Pages**, **Library → Open saved pages**, or follow the page card. Search titles, sort by update time, creation time or title, and page through the complete accessible collection. The viewer provides revision selection, HTML editing, download, and sharing controls. Editing creates a new revision; stale concurrent edits return 409 and leave the unsaved editor text available to copy.

Project details include **Project pages**, also available in Files → Pages while a project is active. Pages created from project chat, its transcript exports, or workflow runs with a recorded project activity appear there automatically. Owners and editors can **Add existing page** to reference an accessible page. A project reference never grants access to the page: each reader still needs its owner/team permission, and public links remain separate. A private page may therefore be visible only to its creator even within a shared project.

Owners see **Open originating chat** or **Open originating workflow run** when a saved page has that provenance. Source endpoints enforce their own access checks. Origin metadata survives page edits, remains absent from public responses, and is not invented for older pages without a recorded source. Transcript-export provenance identifies the originating conversation; its rendered contents remain client-normalized rather than an authenticated database transcript.

Workflow pages contain the intended final output. HTML documents/fragments and fenced HTML are rendered as pages. Other text and structured output use the shared export renderer. Binary file-download payloads, including nested ones, are rejected; use the preceding text/HTML step. A caller may select an authorized completed step with the API's `step` query parameter. Workflow delivery is an output setting, not a new graph node.

## Clickable Pages

When interactivity is requested, the Assistant can include a linked table of contents, KPI cards that jump to their chart or table, and native expandable **Source notes** and **Calculated summary** sections. These use anchors with matching section IDs and `<details><summary>` disclosures, so they work without scripts in previews, saved Pages, and published versions. Essential figures and complete data tables stay visible. Revisions should preserve these controls and their destinations.

Web and email links use known source URLs or contact addresses. They open separately without access to the Page's opener or referrer; jump links stay within the Page. Publication does not grant readers access to private linked sources. JavaScript charts, live filtering, table sorting, forms, and remote assets remain unsupported.

## Ownership and links

New pages are owner-private. The owner can grant read access to one team they belong to; membership is checked on every private read. Only the owner can edit, publish, change access, or delete. Neither being a site administrator nor holding a workflow share token bypasses page ownership.

Private links use `/pages/{uuid}` and require authentication plus page access. Public links use `/a/{token}` and expose only the explicitly published revision. Publishing is a direct owner action in the viewer; neither chat tools nor workflow delivery can publish. Later edits stay unpublished until the owner chooses **Publish version**. Public responses contain the selected title/HTML, not private revision history, owner/team identifiers, or source-workspace metadata.

The main public link shows the version last published to it; **Publish updates** changes what existing recipients see at that link. To share an original and revised page side by side, open **Share**, choose **Version to publish**, then choose **Publish as separate link**. Repeat for another version. Each separate link stays pinned to that version, even when the main link changes or new drafts are saved. The Share dialog lists these links with open, copy, and remove controls. Public viewers see that version's number and saved date, with no access to unpublished versions or other version links.

**Remove public link** disables the main token; **Remove version N link** disables only that separate link. Other public links stay active. Republishing a removed link creates a new token, so old revoked links remain invalid. Deleting clears all revisions and revokes every public link, retaining only a tombstone to prevent delayed retries from recreating the page. Previously downloaded files or already loaded pages cannot be recalled. Sharing a page does not grant access to its source chat, documents, or workflow. Quotations included in the page itself are disclosed when that page is published.

## Printing

Use **Print / Save as PDF** in the viewer to open the selected version's print dialog in a separate tab. **Open full page** also includes a print button. Choose a printer or the browser's PDF destination in that dialog.

Delivered Pages include print colour preservation rules so CSS chart bars print with background graphics disabled. Existing saved versions and HTML downloads receive the same print styling without changing stored source or creating a revision. Browsers supporting [CSS page margin boxes](https://developer.chrome.com/blog/print-margins) (including Chrome 131+) include the selected revision's title, version number, and saved date in UTC on each printed sheet. Browser or printer preferences can still override colour handling.

Previews and downloads remain script-free. Full-page and print views permit only a nonce-authorized application print handler, with sandbox permission for the print dialog. Authored scripts, network requests, and same-origin privileges remain blocked.

## Rendering and storage

Page content is served with a restrictive CSP including `sandbox`, `script-src 'none'`, `connect-src 'none'`, `frame-src 'none'`, `form-action 'none'`, and `base-uri 'none'`. The viewer also uses a sandboxed iframe. Page delivery and interactive previews allow only link popups (`allow-popups allow-popups-to-escape-sandbox`); scripts, same-origin privileges, forms and top-level navigation remain blocked. Web/email anchors are normalized to open separately with `noopener noreferrer`. Raw HTML is reconstructed with an allowlist: scripts, event handlers, forms, embedded frames, SVG/MathML, remote images, and external stylesheet elements are removed. CSS may be inline; CSP blocks remote resources referenced by CSS. Small raster images can be embedded as data URLs. Warnings report removed unsupported content so owners can inspect the actual saved result.

Storage is the MongoDB `html_artifacts` collection, registered with the existing database initialization. One bounded document holds append-only revisions, ownership, source provenance, and publication pointers. Atomic compare-and-set appends prevent competing saves from overwriting one another. Each revision is limited to 256 KiB of rendered HTML; each page supports at most 25 revisions, staying below MongoDB's document-size limit. There are no external asset objects to back up in this release. Chat-created pages record the source conversation/turn and selected Skill UUID/version without copying Skill instructions. Workflow pages record the workflow, session, and selected step. Client-normalized transcript saves are labeled `chat_export`; they are not authenticated copies of database history.

## Deployment

- Deploy the API and frontend together and restart workflow workers for automatic page delivery.
- Keep existing same-origin `/api/` proxying and SPA fallback routes for `/pages/*` and `/a/*`. No extra domain is required for this static HTML release.
- Preserve API `Content-Security-Policy`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, and `X-Robots-Tag` headers. Do not add a blanket `X-Frame-Options: DENY` to API responses, and do not cache page content at a CDN or proxy.
- `ARTIFACT_PUBLIC_SHARING_ENABLED=false` disables new publishing **and all existing public link reads**. Private links continue to work. Default is `true`; owners must still explicitly publish each page.
- Include `html_artifacts` in normal MongoDB backups. Restore publication state deliberately, since restoring older backups also restores their access settings.
- Rollback can remove UI/worker integration and set public sharing off while leaving the additive collection intact. Existing library, chat, workflow, and certification records are not migrated or reset.

Browser verification uses the actual viewer and API with synthetic content and an in-memory database. It is not a production MongoDB, live-model, or deployed cluster smoke test.

## Certification boundary

Published course packages, learner progress, attempts, and credentials are unchanged. Before releasing updated certification content, teach and assess explicit Skill selection/versioning, reviewing saved pages, choosing access, pinned publication, revocation, and both chat/workflow output creation using the existing versioned course process. Static HTML must not be described as a JavaScript application runtime. New competencies need saved revision and execution evidence; existing completion cannot automatically award them.
