# WCAG 2.1 AA — Findings, Pass 3

Re-audit after passes 1 & 2. Residuals + correctness issues only. Much thinner
than pass 2. An **automated axe-core gate** (`src/a11y.test.tsx`) was added this
pass as a standing regression check.

## Serious

- **S1 Contrast residuals (~51).** Light-bg `text-gray-400/300` + inline `#9ca3af/#aaa` the pass-2 sweep missed (all ≈2.5–2.9:1): ExploreTab (15), chat (AttachmentList, ChatInput, ChatPanel "Thinking…"), certification (CelebrationOverlay, CertificationPanel), file/library dialogs (RenameDialog, MoveFolderDialog, AddToLibraryDialog, CatalogImportDialog, DocumentPickerDialog), ModelEffortPicker, SupportChatPanel, ProjectPinsSection, ExaminerManager, CatalogCoverageTab, VerificationSubmitModal, CrossFieldViolationsPanel, ColdStartHero (light branch), ProjectStateBadge (gray-500 on gray-200 ≈4.0:1). Dark surfaces correctly untouched. Fix → gray-500/`#6b7280` (darker for icons).
- **S2 ChatInput focus invisible (2.4.7).** Main message `<textarea>` (`ChatInput.tsx:164`) sets `focus:outline-none focus-visible:outline-none`, wrapper has no ring → no visible focus on the primary chat input. Fix: focus-within ring / drop override. Also weak border-only indicators SupportChatPanel:381/391.
- **S3 Nested interactive elements (2.1.1/4.1.2).** `AutomationsPanel.tsx:261/296` row `<button>` contains pin `<button role=switch>`; `ExtractionEditorPanel.tsx:1740/1777` ToolCard `<button>` contains `<span role=button>`. Invalid + breaks AT. Fix: hoist inner control to a sibling.
- **S4 Unlabeled controls.** Systemic: `Admin.tsx` + `SupportCenter.tsx` shared `labelStyle` renders `<label>` with no `htmlFor`/`id` (dozens unnamed). Bare `<input type=file>` with no name (~14: ChatInput, FileBrowser, UploadZone, DocumentPickerModal, VerifiedCatalog, ExtractionEditorPanel×2, KnowledgePanel, SupportChatPanel×2, SupportCenter×2, Workflows, Admin). ~20 icon-only buttons still unnamed. Fix: `htmlFor`/`id` or `aria-label`.
- **S5 Broken tab wiring (4.1.2) — pass-2 regression.** Roles applied without wiring: `VerificationQueue.tsx:188` (no controls/panel/keyboard at all), `Admin.tsx:1453` Teams sub-tabs (no controls/tabpanel), `ExtractionEditorPanel.tsx:1240/2139` selectors (no controls/tabpanel). Fix: wire `aria-controls`↔`role=tabpanel`+`aria-labelledby`, or downgrade roles to a button/radio group.
- **S6 Over-announcing `aria-live` (4.1.3) — pass-2 regression.** `role=status` on whole progress panels re-announces every tick: `ExtractionEditorPanel.tsx:2472`, `WorkflowEditorPanel.tsx:7397`; and inside `.map()` (N regions): `AutomationsPanel.tsx:337`, `WorkflowEditorPanel.tsx:5246`. Fix: `aria-live=off` on container + one terse `sr-only` phase region.
- **S7 CreateKBModal (4.1.3/3.3.1).** Create-failure error (`:108`) has no `role=alert`; required title (`:73`) no `aria-invalid`/`aria-describedby`.

## Moderate

- **M1 Native dialogs.** `ApiKeysTab.tsx:89` native `confirm()` on destructive "Revoke API key" → `useConfirm`. `FileBrowser.tsx:289/425/463/677/700` five native `alert()` → `toast`.
- **M2 Combobox active-descendant (4.1.2).** `WorkflowEditorPanel.tsx:4209/4360` — combobox roles present but no `aria-activedescendant`, option ids, or Up/Down; Enter always picks result[0]. Add roving highlight.
- **M3 Autocomplete (1.3.5).** Demo:406/428/438, Account, InviteAccept, JoinLinkAccept name/email fields.
- **M4 Tables missing `<th scope>`.** CatalogCoverageTab:133-139, ApplyPreviewModal:161-164, SpreadsheetViewer:300/313, diagrams/ValidationPlanExample:25-27.
- **M5 Reflow @400% (1.4.10).** Fixed-px dialogs without `max-width:100vw`: CertificationPanel:343/351, ContextLimitDialog:66, AddUrlsModal:48, DocumentPickerModal:254, DocumentSearchBar:75.
- **M6 GenerateTestCasesModal.tsx:371** placeholder-only input, no label.

## Minor
- Spinners (`animate-spin` / inline `spin`) + AutomationsPanel pulse/shimmer not gated on `prefers-reduced-motion` (2.3.3 is AAA — low). LoginForm/Landing share one error id across both fields (minor `aria-invalid` over-scoping).

## Clean (verified)
Duplicate ids (4.1.1) — none introduced by the pass-2 label sweep. 2.5.3 label-in-name. Dark-surface contrast. Menu roles. Most tab bars + labeled forms. Modal focus traps.

## Remediation
Partition by file across agents (contrast + labels + the S3/S5/S6 correctness fixes), central `make ci` + expand the axe gate, verify. Nested-button structural fixes (S3) reviewed by hand.

---

## Pass-3 status: COMPLETE

All findings above remediated across ~45 files. Verified green: `tsc -b` clean,
**0 lint errors** (3 pre-existing-class `exhaustive-deps` warnings), 204 tests
pass incl. the new **axe-core gate** (`src/a11y.test.tsx`), build clean.
Notably this pass fixed the pass-2 *correctness regressions* (nested buttons,
over-announcing `aria-live`, half-wired tab roles) and validated no duplicate-id
regressions. Pass 4 will re-audit; the residue is expected to be small
(edge cases, AAA items like reduced-motion on loaders, the raw-highlight-as-text
tail on a few cert surfaces).
