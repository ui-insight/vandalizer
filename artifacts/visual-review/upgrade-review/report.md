# Vandalizer visual and UX review — final local acceptance

September 30, 2026 · [Issue #964](https://github.com/ui-insight/vandalizer/issues/964)

**169/169 checklist items implemented and reviewed locally.** All 13 reviewed areas meet the original minimum of 8/10 for UI and UX; mobile independently meets 8/8. These are judgments of the reviewed frontend and fixture-backed interactions, not live-service certification. Nothing has been pushed or deployed.

## Before and after

Independent Codex judgments after direct screenshot inspection and fixture-backed interaction checks, using the original 0–10 rubric. UI considers hierarchy, spacing, typography, consistency, contrast and layout. UX considers discoverability, progression, feedback, recovery and scope clarity. 8 means strong; 9–10 would require exceptional polish and evidence beyond this review. Checklist completion does not determine the grade.

| Area | Baseline UI/UX | Final UI/UX | Inspected evidence |
|---|---:|---:|---|
| File browser | 6/6 | 8/8 | [files](../2026-09-30-acceptance-baseline/files.png) |
| Projects | 6.5/6.5 | 8/8 | [projects](../2026-09-30-acceptance-baseline/projects.png) |
| Automations screen and editor | 6/6 | 8/8 | [automation-detail](../2026-09-30-acceptance-baseline/automation-detail.png) |
| Automation creation wizard | 7.5/5.5 | 8/8.5 | [wizard-5-activation](../2026-09-30-acceptance-baseline/wizard-5-activation.png) |
| Knowledge bases | 6/5.5 | 8/8 | [knowledge-detail](../2026-09-30-acceptance-baseline/knowledge-detail.png) |
| KB validation system | 6.5/6.5 | 8/8 | [validation-wizard-budget](../2026-09-30-acceptance-baseline/validation-wizard-budget.png) |
| Explore / shared catalog | 7/6.5 | 8/8 | [catalog-detail](../2026-09-30-acceptance-baseline/catalog-detail.png) |
| Library | 5.5/5.5 | 8/8.5 | [library-mobile](../2026-09-30-acceptance-baseline/library-mobile.png) |
| Chat workspace | 6.5/6 | 8/8 | [chat-home](../2026-09-30-acceptance-baseline/chat-home.png) |
| Basic chat onboarding | 7/6.5 | 8/8 | [chat-onboarding](../2026-09-30-acceptance-baseline/chat-onboarding.png) |
| Chat uploads | 6/3 | 8/8.5 | [chat-upload-error](../2026-09-30-acceptance-baseline/chat-upload-error.png) |
| Chat knowledge-base interactions | 7/7 | 8/8.5 | [chat-kb-answer](../2026-09-30-acceptance-baseline/chat-kb-answer.png) |
| Agentic chat UI | 7/6.5 | 8/8 | [chat-agent-error](../2026-09-30-acceptance-baseline/chat-agent-error.png) |

**Mobile: baseline 3 → final UI 8 / UX 8.** Navigation and pane switching preserve source/tool state at 320/390px. Dialog actions remain reachable at 320×480; larger lists scroll, and controls retain labels or accessible names. Two-pane work becomes explicit pane switching on phones. Very short screens require scrolling; this is not a claim of native mobile or assistive-device certification.

[Original rubric and findings](../2026-09-25/report.md) · [Complete checklist](../../../docs/ui-ux-upgrade-checklist.md) · [Dated implementation and verification log](../../../docs/ui-ux-implementation-progress.md) · [Per-area judgments](final-grades.json)

## Final repairs and verification

- Shared form labels distinguish required and optional entries. Field errors have linked descriptions and focus; server failures preserve valid drafts for retry.
- Text and icons identify recorded run status. Project/trust badges share geometry and semantic colors while availability and measured quality remain distinct.
- Shared pickers retain selections across search and retry, ignore stale responses, fit short screens, contain focus and isolate Escape. Knowledge creation keeps a stable header/footer. Destructive confirmation initially focuses the safe action.
- A screenshot audit caught doubled-text tab and header overlap that page-width/axe checks did not detect. Both editor resize observers now attach after loading, compact tabs are named, workflow tabs support arrow/Home/End navigation, and the header wraps or collapses labels without covering the logo. Direct reinspection confirmed the repair.
- File timestamps clear row actions; Library descriptions wrap; the Explore detail header uses neutral task styling. The empty supporting Assistant is compact while Files and Library/tool navigation retain the approved parallel-pane behavior.
- Upload announcements expose state changes separately from percentage bars. Validation announcements exclude elapsed seconds, tokens and trial streaming; status/phase changes remain polite and atomic. Reduced-motion loading states retain text.
- The final browser evidence includes the 55 original baseline states, viewport matrix, keyboard focus and menu/dialog actions, nested generation/picker Escape, short-form validation and retry, file-to-Library execution/error/retry/return at 200% equivalent zoom, and separately doubled text. Earlier selected evidence covers 120 Library items, 251 validation questions, long content, role/scope restrictions, resumption and failure recovery.
- Production build and TypeScript pass. Touched-file ESLint has zero errors; existing hook-dependency warnings are recorded in the implementation log. The full frontend suite has 1,199 passing tests across 176 passing files, with only the same three pre-existing Landing signup failures (one file). Focused regressions and announcement checks pass.

**Selected evidence:** 1306 distinct states across 3116 captures. Every selected capture has its image, accessible tree and axe output; latest selected states have zero axe violations and no horizontal page overflow. Manifests record source/fixture fingerprints and browser versions. Superseded diagnostic runs remain local and are excluded from acceptance.

## Resolved original findings

UX-01 upload scope is retained and asserted in outgoing requests. UX-02 responsive overflow and UX-04 Library clipping are repaired. UX-03 wizard Enter preserves and advances the draft. UX-05 active work receives primary hierarchy with a compact supporting Assistant. UX-06 source completeness and textual operational state are explicit. UX-07 accessible names, structure, contrast and keyboard checks pass in the reviewed surfaces. UX-08 activation has a complete review and explicit disabled/enabled choices. UX-09 validation has a shorter task-oriented path and bounded estimates. UX-10 approvals and progress are scoped to the operation, with retained artifacts and recovery.

## Limits and release handoff

- Browser APIs and model output are synthetic. No live broker, worker, model, retrieval or permission certification.
- 200% browser-zoom layout is simulated with half-size CSS viewports and device scale 2; doubled root text size is checked separately. Native browser zoom UI and screen-reader speech output were not exercised.
- Three pre-existing Landing signup tests fail; workspace-focused checks pass.
- Changes are local and require the coordinated release described in the implementation log. Nothing is pushed or deployed by this review.

## Per-area assessment

**File browser — UI 8, UX 8:** Readable names, dates and persistent row actions establish a clear hierarchy. Selection, upload scope and partial-operation retry are exercised; the source stays available beside Library tools. Dense file tables remain utilitarian, so this is strong rather than exceptional.

**Projects — UI 8, UX 8:** Clear project names, textual state, roles and counts make scope scannable. Search, creation, editing, empty states and retained failures have explicit next steps; long-title and viewer cases are covered by the project recovery evidence.

**Automations screen and editor — UI 8, UX 8:** Neutral cards and a trigger/input/action/output summary connect configuration to behavior. Saved-state, failed-save retry, history and exact-request reconnect are explicit. Configuration remains substantial, even with grouped settings.

**Automation creation wizard — UI 8, UX 8.5:** Required guidance, retained choices and a complete final review create a coherent sequence. Save disabled and Create & enable are distinct; nested pickers and short-screen actions are tested. API and scheduling details remain technical but optional to other trigger paths.

**Knowledge bases — UI 8, UX 8:** Availability, source coverage and measured quality are visibly separate. Source failures show a next action, while ownership, sharing and catalog transitions retain context. Source and validation controls remain information-dense but readable.

**KB validation system — UI 8, UX 8:** Questions, expected answers, comparison and budget review now form a bounded path. Sample limitations, unavailable cost estimates, explicit apply/revert and saved history prevent misleading conclusions. Advanced tuning still requires domain knowledge.

**Explore / shared catalog — UI 8, UX 8:** A neutral detail header leads into input/output suitability and dated validation evidence. Missing metadata is explicit. Save/retry/already-saved/Open states preserve browsing context; catalog usefulness still depends on contributor descriptions.

**Library — UI 8, UX 8.5:** Names and descriptions get usable width, with visible row actions and consistent scope/filter controls. Large lists, exact-item retry and the file-to-tool workflow are exercised. Desktop parallel panes and mobile state retention preserve the central task.

**Chat workspace — UI 8, UX 8:** Readable conversation and a stable composer are supported by source chips and contextual controls. The supporting Assistant is compact beside active work. Queueing, failed drafts, model selection and reading-position recovery are tested; the main home still offers several starting paths.

**Basic chat onboarding — UI 8, UX 8:** Conversation, upload and sample entry points are concrete. Source wording is bounded, the optional tour does not repeatedly reopen, and an upload-to-question-to-evidence journey is covered. The first screen retains secondary learning choices below its primary actions.

**Chat uploads — UI 8, UX 8.5:** Successful files remain attached through refresh and sibling failures. Persistent failure text, retry/cancel controls and visible ready state make recovery clear. Request assertions establish the intended document UUID; frontend evidence does not establish live ingestion.

**Chat knowledge-base interactions — UI 8, UX 8.5:** Full source scope, coverage and readable citation chips connect the question to inspectable evidence. Missing/failed sources, preview return and multiple-source requests are exercised. Citation correctness against a live retriever remains outside this visual review.

**Agentic chat UI — UI 8, UX 8:** Action-specific approval, operation-scoped status, retained partial results and artifact links make progress and recovery understandable. Failed/unconfirmed operations do not masquerade as success. Long output remains navigable; real agent execution is not certified.

## Evidence manifests

- [upgrade-final](../upgrade-final/manifest.json): 54 captures; source `dd97377f8d68b289a4bfa6fc142134425cc1bd303662f11e2ea1531a47ad3c01`; production; Chromium 148.0.7778.96.
- [upgrade-final-responsive](../upgrade-final-responsive/manifest.json): 42 captures; source `dd97377f8d68b289a4bfa6fc142134425cc1bd303662f11e2ea1531a47ad3c01`; production; Chromium 148.0.7778.96.
- [upgrade-final-recheck](../upgrade-final-recheck/manifest.json): 5 captures; source `304d137cccd76f6956e0ca368c694dce7adc6ca79e8fd432a9f11f7782875bf3`; production; Chromium 148.0.7778.96.
- [upgrade-final-detail-recheck](../upgrade-final-detail-recheck/manifest.json): 4 captures; source `06167a9590da5eb885507e212eefdd88b64fbea43556cb92205022c7ec9f2485`; production; Chromium 148.0.7778.96.
- [upgrade-followup-detail](../upgrade-followup-detail/manifest.json): 10 captures; source `98bde3d6bdbad939babaa660a75d5c470ce390fa4fa99a18f878d64743bf36e3`; production; Chromium 148.0.7778.96.
- [upgrade-followup-responsive](../upgrade-followup-responsive/manifest.json): 42 captures; source `98bde3d6bdbad939babaa660a75d5c470ce390fa4fa99a18f878d64743bf36e3`; production; Chromium 148.0.7778.96.
- [upgrade-polish-final-journeys](../upgrade-polish-final-journeys/manifest.json): 20 captures; source `9ab263840ad82724fa144c3beb66a8c16db8cd3a43f2530f5b61b6c75eb7c4ee`; production; Chromium 148.0.7778.96.
- [upgrade-polish-final-context](../upgrade-polish-final-context/manifest.json): 9 captures; source `9ab263840ad82724fa144c3beb66a8c16db8cd3a43f2530f5b61b6c75eb7c4ee`; production; Chromium 148.0.7778.96.
- [upgrade-folder-recheck](../upgrade-folder-recheck/manifest.json): 4 captures; source `5e854ebdf031d0fa2e1424949bf71dbd7f7248f0bbb2df85c6ac242700c46d5f`; production; Chromium 148.0.7778.96.
- [2026-09-26-recovery-verified](../2026-09-26-recovery-verified/manifest.json): 19 captures; source `3c00786581d88931b877b28c65d41aa2ad4a92e611fc8ee309eb15dec9b4ffa3`; production; Chromium 148.0.7778.96.
- [2026-09-26-recovery-layout-verified](../2026-09-26-recovery-layout-verified/manifest.json): 15 captures; source `3c00786581d88931b877b28c65d41aa2ad4a92e611fc8ee309eb15dec9b4ffa3`; production; Chromium 148.0.7778.96.
- [2026-09-28-wizard-flow-verified](../2026-09-28-wizard-flow-verified/manifest.json): 47 captures; source `9a42756239009c55d3d59e059e33d4452ea55e2b696f57b228f7e5f5f63a37cb`; production; Chromium 148.0.7778.96.
- [2026-09-28-wizard-api-verified](../2026-09-28-wizard-api-verified/manifest.json): 6 captures; source `9a42756239009c55d3d59e059e33d4452ea55e2b696f57b228f7e5f5f63a37cb`; production; Chromium 148.0.7778.96.
- [2026-09-28-wizard-mobile-final](../2026-09-28-wizard-mobile-final/manifest.json): 19 captures; source `be4c40d793ccabbd831e13cb533f6604ab2bd16d99be7ecb6af993c30bf83f8e`; production; Chromium 148.0.7778.96.
- [2026-09-28-history-verified](../2026-09-28-history-verified/manifest.json): 18 captures; source `691246b33adf6c00811fd024a89c91da63d67b31246959928584a5c31fbcddc5`; production; Chromium 148.0.7778.96.
- [2026-09-28-lifecycle-evidence](../2026-09-28-lifecycle-evidence/manifest.json): 26 captures; source `ccf31953e99a4257dc277b95973ba60f96cc790737fceafa1f99ab63eb91aaee`; production; Chromium 148.0.7778.96.
- [2026-09-28-resumption-final](../2026-09-28-resumption-final/manifest.json): 29 captures; source `1dc1511f27c2bca121dfed5144eb2e17ac867e58dc332d1d9c3ec7a43e13d6a3`; production; Chromium 148.0.7778.96.
- [2026-09-28-questions-final](../2026-09-28-questions-final/manifest.json): 23 captures; source `33696a54bf11c43a13127b84baf221dc9a32d93814e4e2be63242ae42909def9`; production; Chromium 148.0.7778.96.
- [2026-09-28-sources-release](../2026-09-28-sources-release/manifest.json): 35 captures; source `88784712f6ca5613e5562b741d603851dc533f0b440311c29b60091689662f1a`; production; Chromium 148.0.7778.96.
- [2026-09-28-uploads-evidence](../2026-09-28-uploads-evidence/manifest.json): 28 captures; source `88784712f6ca5613e5562b741d603851dc533f0b440311c29b60091689662f1a`; production; Chromium 148.0.7778.96.
- [2026-09-28-validation-scope](../2026-09-28-validation-scope/manifest.json): 6 captures; source `47b6255d507987555499ba43f1d4cef662cbba5543c71204b43a8691322c1eb4`; production; Chromium 148.0.7778.96.
- [2026-09-28-source-intake-final](../2026-09-28-source-intake-final/manifest.json): 24 captures; source `ccdd847c12e77c2248899f2defdd46ee0c52975de787607c134680e5d422f3dd`; production; Chromium 148.0.7778.96.
- [2026-09-28-catalog-filters-evidence](../2026-09-28-catalog-filters-evidence/manifest.json): 36 captures; source `221c0fac50789b334450a39bcea7b5c927200af55a4c1bb7b55a72054ede2e75`; production; Chromium 148.0.7778.96.
- [2026-09-28-catalog-evidence-review](../2026-09-28-catalog-evidence-review/manifest.json): 12 captures; source `0f510ea9363a67e62430ce5ca6a56a95ab94f8229599477faf8808d423d85304`; production; Chromium 148.0.7778.96.
- [2026-09-28-chat-navigation-evidence](../2026-09-28-chat-navigation-evidence/manifest.json): 33 captures; source `ca314d9152a391559bf3638c5b66be73042bfc5668971015eccf25da196dc867`; production; Chromium 148.0.7778.96.
- [2026-09-28-chat-scope-final](../2026-09-28-chat-scope-final/manifest.json): 18 captures; source `71171ed99d62616b58ffef0ead6ea65ea60b1dbdd8432d941609f4af478a1a9d`; production; Chromium 148.0.7778.96.
- [2026-09-28-file-library-evidence](../2026-09-28-file-library-evidence/manifest.json): 30 captures; source `7a42314934b1b90e86fb59a116253f54e851ec074509436c370b165d0c41368b`; production; Chromium 148.0.7778.96.
- [2026-09-28-projects-restored-layout](../2026-09-28-projects-restored-layout/manifest.json): 39 captures; source `dbfff5c474499b27dd914e221843a04bfb912042947b4511c356b97e4387ed92`; production; Chromium 148.0.7778.96.
- [2026-09-28-files-restored-layout](../2026-09-28-files-restored-layout/manifest.json): 33 captures; source `449342649e3042a4729bded577766c57e4f4a6e01a6384e91bd6517e0655e7cd`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-run-evidence](../2026-09-28-automation-run-evidence/manifest.json): 21 captures; source `23a01df2593e624f9ae9f8090d4774ed49d1df4a57c2a7ff0e56ae726e980f09`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-filters-final](../2026-09-28-automation-filters-final/manifest.json): 27 captures; source `6a74bcfc7d73502fb4a87f5ea0d58d2adb635911a72590d9d899cbe6ea106ee0`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-history-final](../2026-09-28-automation-history-final/manifest.json): 30 captures; source `8ea2fe6384d6c50797ff5b8f7caf29d29073307db0855bfc85c0bc57e4ae6895`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-summary-review](../2026-09-28-automation-summary-review/manifest.json): 21 captures; source `fd1ded4a22be6163e3601463bf721bf6fde27eb713813b285783bdcb18eb4376`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-filter-light](../2026-09-28-automation-filter-light/manifest.json): 27 captures; source `fd1ded4a22be6163e3601463bf721bf6fde27eb713813b285783bdcb18eb4376`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-save-review](../2026-09-28-automation-save-review/manifest.json): 18 captures; source `f5bb53d9dc8f8f1c44df0a4d9afee6372ec2a9c184070f88dc82719208545558`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-launch-evidence](../2026-09-28-automation-launch-evidence/manifest.json): 18 captures; source `62fb6064b0e4cae409f0fad9eb08576fa651b63a07d4717c64f29fd3379f44e8`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-run-reconnect](../2026-09-28-automation-run-reconnect/manifest.json): 21 captures; source `62fb6064b0e4cae409f0fad9eb08576fa651b63a07d4717c64f29fd3379f44e8`; production; Chromium 148.0.7778.96.
- [2026-09-28-library-recovery-evidence](../2026-09-28-library-recovery-evidence/manifest.json): 51 captures; source `d47f655df76cd82286c5283e6f89bc3c6706be0cf72c713387e6ee448e9dd0c6`; production; Chromium 148.0.7778.96.
- [2026-09-28-library-opening-evidence](../2026-09-28-library-opening-evidence/manifest.json): 21 captures; source `d47f655df76cd82286c5283e6f89bc3c6706be0cf72c713387e6ee448e9dd0c6`; production; Chromium 148.0.7778.96.
- [2026-09-28-file-library-regression](../2026-09-28-file-library-regression/manifest.json): 30 captures; source `6d0eba57af1b0af8f66e6bd427e6477a3b9bb330401dbf2199a3dedb739979ba`; production; Chromium 148.0.7778.96.
- [2026-09-29-knowledge-states-evidence](../2026-09-29-knowledge-states-evidence/manifest.json): 40 captures; source `d87b6c4df69d29f484bb98876c08893839157a8e7facce628813ee44a65bbb88`; production; Chromium 148.0.7778.96.
- [2026-09-29-knowledge-project-final](../2026-09-29-knowledge-project-final/manifest.json): 6 captures; source `db482784faf138c697a3a9f4c1e12a69f210c3e184da69d6da37db399f9829aa`; production; Chromium 148.0.7778.96.
- [2026-09-29-chat-composer-evidence](../2026-09-29-chat-composer-evidence/manifest.json): 26 captures; source `90c99a4a7969939d035ba81d66ecef0e593343dff01279f9219d35e503a159d5`; production; Chromium 148.0.7778.96.
- [2026-09-29-catalog-usage-final](../2026-09-29-catalog-usage-final/manifest.json): 30 captures; source `0e20919019d0e30019feaac40bce460afbf5a9200457aab0fd6e7e7724e5f2bb`; production; Chromium 148.0.7778.96.
- [2026-09-29-catalog-filter-regression](../2026-09-29-catalog-filter-regression/manifest.json): 36 captures; source `03d414db121fc5955f7641f27543b7928d2eca43ebddf2d632adf0271fb39dd7`; production; Chromium 148.0.7778.96.
- [2026-09-29-onboarding-tour-evidence](../2026-09-29-onboarding-tour-evidence/manifest.json): 30 captures; source `9d7c5e257da88c233b9bf0fa46df6acfff44e220b7719cd8e168137f95a7b00e`; production; Chromium 148.0.7778.96.
- [2026-09-29-agent-recovery-evidence](../2026-09-29-agent-recovery-evidence/manifest.json): 42 captures; source `5f95e759e077e2d106800ae4d4b2b67c8ae851cbb834c03c2bd1e02aad674dbe`; production; Chromium 148.0.7778.96.
- [2026-09-29-panel-preferences-final](../2026-09-29-panel-preferences-final/manifest.json): 13 captures; source `326e8376576d1a85f635d0dbbbdc41c633b6b089825e76765f239010c1e8ec36`; production; Chromium 148.0.7778.96.
- [2026-09-29-panel-file-library-regression](../2026-09-29-panel-file-library-regression/manifest.json): 30 captures; source `0589b6350acd79e4d8e99b5bb802d4a28e54ea295f0172542a1bebe754f96a3f`; production; Chromium 148.0.7778.96.
- [2026-09-30-validation-resumption-short](../2026-09-30-validation-resumption-short/manifest.json): 29 captures; source `19c339b27e1acf78528c3e53711c265777f0eae7a3eeea27c7a40b27b2064ac9`; production; Chromium 148.0.7778.96.
- [2026-09-30-validation-questions-short](../2026-09-30-validation-questions-short/manifest.json): 23 captures; source `19c339b27e1acf78528c3e53711c265777f0eae7a3eeea27c7a40b27b2064ac9`; production; Chromium 148.0.7778.96.
- [2026-09-30-validation-history-short](../2026-09-30-validation-history-short/manifest.json): 18 captures; source `19c339b27e1acf78528c3e53711c265777f0eae7a3eeea27c7a40b27b2064ac9`; production; Chromium 148.0.7778.96.
- [2026-09-30-validation-dialogs-final](../2026-09-30-validation-dialogs-final/manifest.json): 36 captures; source `ea93a730a60c7a33d73d6403a7e0b2330efb65e6a656c65585373f937a656775`; production; Chromium 148.0.7778.96.
- [2026-09-30-navigation-retention-complete](../2026-09-30-navigation-retention-complete/manifest.json): 35 captures; source `cff68c82f61d451ad833e36ac4f9f53fce39cb2147677ccda34e3403752840b4`; production; Chromium 148.0.7778.96.
- [2026-09-30-navigation-file-library-regression](../2026-09-30-navigation-file-library-regression/manifest.json): 30 captures; source `639371175d3fbb7087715bdd81ddf1afe8b78762f967c2cd53f09665e9ca5c5a`; production; Chromium 148.0.7778.96.
- [2026-09-30-navigation-project-final](../2026-09-30-navigation-project-final/manifest.json): 39 captures; source `66c562f7174dd1ec9afc46a46be8141cbba39e43588a74ec7a980580b8b6b220`; production; Chromium 148.0.7778.96.
- [2026-09-30-context-release](../2026-09-30-context-release/manifest.json): 30 captures; source `9e7fcd52703211626580619a4d08d2a892a861d39a43b254abe9ce00b806cc9d`; production; Chromium 148.0.7778.96.
- [2026-09-30-context-retention-final](../2026-09-30-context-retention-final/manifest.json): 35 captures; source `62bda97eaa998626e15b4fca70da378b3bed99d3bea64321c6a334a5447d58cf`; production; Chromium 148.0.7778.96.
- [2026-09-30-context-file-library-final](../2026-09-30-context-file-library-final/manifest.json): 30 captures; source `62bda97eaa998626e15b4fca70da378b3bed99d3bea64321c6a334a5447d58cf`; production; Chromium 148.0.7778.96.
- [2026-09-30-headers-evidence](../2026-09-30-headers-evidence/manifest.json): 27 captures; source `a05978b14868eeea4ead9ad59b050bf9adaba11988527923aac848fee637ad7d`; production; Chromium 148.0.7778.96.
- [2026-09-30-headers-retention](../2026-09-30-headers-retention/manifest.json): 35 captures; source `f06157b3de87e4413c97a793b1fe1559e9c38703e9c96578da18f845ea568e38`; production; Chromium 148.0.7778.96.
- [2026-09-30-headers-file-library](../2026-09-30-headers-file-library/manifest.json): 30 captures; source `f06157b3de87e4413c97a793b1fe1559e9c38703e9c96578da18f845ea568e38`; production; Chromium 148.0.7778.96.
- [2026-09-30-density-headers](../2026-09-30-density-headers/manifest.json): 27 captures; source `27b1de876a492d4736ea8999f7ac5ac75c1e9420ee6a3c34300fd39837500f5e`; production; Chromium 148.0.7778.96.
- [2026-09-30-density-composer-context](../2026-09-30-density-composer-context/manifest.json): 33 captures; source `1451ba4e8667734e42345399555f30649ee2e413c729e0729608718d59018641`; production; Chromium 148.0.7778.96.
- [2026-09-30-density-navigation-release](../2026-09-30-density-navigation-release/manifest.json): 35 captures; source `1451ba4e8667734e42345399555f30649ee2e413c729e0729608718d59018641`; production; Chromium 148.0.7778.96.
- [2026-09-30-density-file-library](../2026-09-30-density-file-library/manifest.json): 30 captures; source `27b1de876a492d4736ea8999f7ac5ac75c1e9420ee6a3c34300fd39837500f5e`; production; Chromium 148.0.7778.96.
- [2026-09-30-density-chat-reading](../2026-09-30-density-chat-reading/manifest.json): 33 captures; source `1451ba4e8667734e42345399555f30649ee2e413c729e0729608718d59018641`; production; Chromium 148.0.7778.96.
- [2026-09-30-theme-knowledge](../2026-09-30-theme-knowledge/manifest.json): 40 captures; source `aa62a997f2baee6fb0e6704893e3cc7fec1e6e8cf6dcab2dc17a6b448ee22b3b`; production; Chromium 148.0.7778.96.
- [2026-09-30-theme-validation-overlay](../2026-09-30-theme-validation-overlay/manifest.json): 29 captures; source `d09d83a3d8c12cfccc6cf8c1a73eb617c5a28507677f209c1855d32473141340`; production; Chromium 148.0.7778.96.
- [2026-09-30-theme-questions](../2026-09-30-theme-questions/manifest.json): 23 captures; source `eacacd0449856830976e713f2d591e01869b1381ebfe07b2efbfffba9e98bd7a`; production; Chromium 148.0.7778.96.
- [2026-09-30-theme-dialogs-final](../2026-09-30-theme-dialogs-final/manifest.json): 36 captures; source `77adf9df2da117e5a37f44d4b8c6f619a9d600a870c168d3a28bbe0138813f7a`; production; Chromium 148.0.7778.96.
- [2026-09-30-theme-history-final](../2026-09-30-theme-history-final/manifest.json): 18 captures; source `77adf9df2da117e5a37f44d4b8c6f619a9d600a870c168d3a28bbe0138813f7a`; production; Chromium 148.0.7778.96.
- [2026-09-30-theme-source-intake](../2026-09-30-theme-source-intake/manifest.json): 24 captures; source `2c9cdfaf2aa75523ac72d3457f8f112f1f70e6ef71236593f2e3c4545b3964f8`; production; Chromium 148.0.7778.96.
- [2026-09-30-theme-domains-verified](../2026-09-30-theme-domains-verified/manifest.json): 39 captures; source `5798a0e17f6e97033b6dfaf87129e6fb6821bc2cc5a2ce9dbf823b9e96746cb0`; production; Chromium 148.0.7778.96.
- [2026-09-30-theme-catalog-release](../2026-09-30-theme-catalog-release/manifest.json): 36 captures; source `6a0fa632f97a315a2a33b2a0d005f90407c7e16267570a901f6a541325cc138c`; production; Chromium 148.0.7778.96.
- [2026-09-30-theme-context-release](../2026-09-30-theme-context-release/manifest.json): 33 captures; source `6a0fa632f97a315a2a33b2a0d005f90407c7e16267570a901f6a541325cc138c`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-baseline](../2026-09-30-typography-baseline/manifest.json): 55 captures; source `e0d7f23bf87cca0ecc52917430329802fa322ea2cff980715e5f4af09f37364a`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-domains](../2026-09-30-typography-domains/manifest.json): 39 captures; source `e0d7f23bf87cca0ecc52917430329802fa322ea2cff980715e5f4af09f37364a`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-questions](../2026-09-30-typography-questions/manifest.json): 23 captures; source `e0d7f23bf87cca0ecc52917430329802fa322ea2cff980715e5f4af09f37364a`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-file-library](../2026-09-30-typography-file-library/manifest.json): 30 captures; source `ad0754212995717f142a89797cb7d2b5eaf734df90bc9fed3d1a17fecdfb274d`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-headers](../2026-09-30-typography-headers/manifest.json): 27 captures; source `ad0754212995717f142a89797cb7d2b5eaf734df90bc9fed3d1a17fecdfb274d`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-context](../2026-09-30-typography-context/manifest.json): 33 captures; source `ad0754212995717f142a89797cb7d2b5eaf734df90bc9fed3d1a17fecdfb274d`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-history](../2026-09-30-typography-history/manifest.json): 18 captures; source `ad0754212995717f142a89797cb7d2b5eaf734df90bc9fed3d1a17fecdfb274d`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-dialogs](../2026-09-30-typography-dialogs/manifest.json): 36 captures; source `636847e9847226ae8e533ed8da536fe19f4ab0c15fbf7f18e38244abe2da10b7`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-chat-reading-final](../2026-09-30-typography-chat-reading-final/manifest.json): 33 captures; source `b31ceef44fa2e359b68ff5f1be950388c99984191bcb17973a66ee3e00961b48`; production; Chromium 148.0.7778.96.
- [2026-09-30-typography-context-meter-final](../2026-09-30-typography-context-meter-final/manifest.json): 12 captures; source `b31ceef44fa2e359b68ff5f1be950388c99984191bcb17973a66ee3e00961b48`; production; Chromium 148.0.7778.96.
- [2026-09-30-spacing-responsive-final](../2026-09-30-spacing-responsive-final/manifest.json): 42 captures; source `1759d635ca2e89f9af413f905b72aafd93c3e59e8c666df4873731d7eca88624`; production; Chromium 148.0.7778.96.
- [2026-09-30-spacing-baseline](../2026-09-30-spacing-baseline/manifest.json): 55 captures; source `1759d635ca2e89f9af413f905b72aafd93c3e59e8c666df4873731d7eca88624`; production; Chromium 148.0.7778.96.
- [2026-09-30-spacing-domains](../2026-09-30-spacing-domains/manifest.json): 39 captures; source `1759d635ca2e89f9af413f905b72aafd93c3e59e8c666df4873731d7eca88624`; production; Chromium 148.0.7778.96.
- [2026-09-30-spacing-file-library](../2026-09-30-spacing-file-library/manifest.json): 30 captures; source `0c1e2cba43612fd33e01d51b2b500025b8405543a328f2914b439deee73d9dd7`; production; Chromium 148.0.7778.96.
- [2026-09-30-spacing-dialogs](../2026-09-30-spacing-dialogs/manifest.json): 36 captures; source `0c1e2cba43612fd33e01d51b2b500025b8405543a328f2914b439deee73d9dd7`; production; Chromium 148.0.7778.96.
- [2026-09-30-spacing-headers](../2026-09-30-spacing-headers/manifest.json): 27 captures; source `0c1e2cba43612fd33e01d51b2b500025b8405543a328f2914b439deee73d9dd7`; production; Chromium 148.0.7778.96.
- [2026-09-30-actions-baseline-release](../2026-09-30-actions-baseline-release/manifest.json): 55 captures; source `fd9d2d85192ce2c4604bf815e231dcc0270b3ce67f3ecc9b46ca5fd6917b1c39`; production; Chromium 148.0.7778.96.
- [2026-09-30-actions-file-library-final](../2026-09-30-actions-file-library-final/manifest.json): 30 captures; source `fd9d2d85192ce2c4604bf815e231dcc0270b3ce67f3ecc9b46ca5fd6917b1c39`; production; Chromium 148.0.7778.96.
- [2026-09-30-actions-source-intake-final](../2026-09-30-actions-source-intake-final/manifest.json): 24 captures; source `fd9d2d85192ce2c4604bf815e231dcc0270b3ce67f3ecc9b46ca5fd6917b1c39`; production; Chromium 148.0.7778.96.
- [2026-09-30-actions-dialogs-final](../2026-09-30-actions-dialogs-final/manifest.json): 36 captures; source `68780e51959b2bda7bb1443b6f90e21e37c6c5160072f98d8fe3189418e6438d`; production; Chromium 148.0.7778.96.
- [2026-09-30-actions-keyboard-release](../2026-09-30-actions-keyboard-release/manifest.json): 18 captures; source `6d8d0c1a8539114d4d924f49ee397819c53b1019c392bec59d6035085f78c3d8`; production; Chromium 148.0.7778.96.
- [2026-09-30-forms-source-intake-final](../2026-09-30-forms-source-intake-final/manifest.json): 24 captures; source `ee736b9fc2227e4fe2f77788b7b2a8c4bd07a9494c4c82d7e8e0349ce852ccd0`; production; Chromium 148.0.7778.96.
- [2026-09-30-forms-wizard-final](../2026-09-30-forms-wizard-final/manifest.json): 53 captures; source `ee736b9fc2227e4fe2f77788b7b2a8c4bd07a9494c4c82d7e8e0349ce852ccd0`; production; Chromium 148.0.7778.96.
- [2026-09-30-forms-catalog-recovery](../2026-09-30-forms-catalog-recovery/manifest.json): 19 captures; source `ee736b9fc2227e4fe2f77788b7b2a8c4bd07a9494c4c82d7e8e0349ce852ccd0`; production; Chromium 148.0.7778.96.
- [2026-09-30-acceptance-baseline](../2026-09-30-acceptance-baseline/manifest.json): 55 captures; source `bfdb7a460243c47da0c4aa609a0479e1c5e5aed8d6a0923cc9195ece6044ae7e`; production; Chromium 148.0.7778.96.
- [2026-09-30-acceptance-forms](../2026-09-30-acceptance-forms/manifest.json): 18 captures; source `bfdb7a460243c47da0c4aa609a0479e1c5e5aed8d6a0923cc9195ece6044ae7e`; production; Chromium 148.0.7778.96.
- [2026-09-30-acceptance-actions](../2026-09-30-acceptance-actions/manifest.json): 18 captures; source `bfdb7a460243c47da0c4aa609a0479e1c5e5aed8d6a0923cc9195ece6044ae7e`; production; Chromium 148.0.7778.96.
- [2026-09-30-domains-final](../2026-09-30-domains-final/manifest.json): 42 captures; source `bfdb7a460243c47da0c4aa609a0479e1c5e5aed8d6a0923cc9195ece6044ae7e`; production; Chromium 148.0.7778.96.
- [2026-09-30-text-final](../2026-09-30-text-final/manifest.json): 12 captures; source `bfdb7a460243c47da0c4aa609a0479e1c5e5aed8d6a0923cc9195ece6044ae7e`; production; Chromium 148.0.7778.96.
- [2026-09-30-zoom-final](../2026-09-30-zoom-final/manifest.json): 12 captures; source `bfdb7a460243c47da0c4aa609a0479e1c5e5aed8d6a0923cc9195ece6044ae7e`; production; Chromium 148.0.7778.96.
- [2026-09-30-acceptance-library](../2026-09-30-acceptance-library/manifest.json): 51 captures; source `136a3c728df3349d976ecf18610037028e0a18639d84838ffd43ce6af051a5b9`; production; Chromium 148.0.7778.96.
- [2026-09-30-acceptance-responsive](../2026-09-30-acceptance-responsive/manifest.json): 42 captures; source `136a3c728df3349d976ecf18610037028e0a18639d84838ffd43ce6af051a5b9`; production; Chromium 148.0.7778.96.
- [2026-09-30-accessibility-verified](../2026-09-30-accessibility-verified/manifest.json): 15 captures; source `1ed2d061fbd77c4ce2150af90f3b8d5f8ed921b5e1258e7362d9477249b70d6e`; production; Chromium 148.0.7778.96.
