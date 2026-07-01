# WCAG 2.1 AA — Findings, Pass 2

Re-audit of `frontend/src` **after pass-1 remediation**. Pass-1-fixed items are
excluded; this is what remains or was missed. Pass 2 is materially larger than
pass 1 — the earlier audit sampled; this one went deep into the workspace
editors, library, knowledge, and admin surfaces.

Severity: **Critical / Serious / Moderate / Minor**.

Highest-leverage insight: several findings collapse to a handful of **shared
components** — fixing those cascades across the app.

---

## Cross-cutting / shared fixes (do these first — each cascades)

| # | Fix | Impact |
|---|-----|--------|
| X1 | **Global focus ring** `index.css:34` uses raw `--highlight-color` (yellow ≈1.9:1 on white) → switch to `--highlight-on-light` / add offset halo | 1.4.11, every keyboard user, ~1 line |
| X2 | **4 shared status components** get `role=status/alert`/`aria-live`: `OptimizationProgressCard`, `RunBanners`, `QualityTimeline`, `WizardLoadingStep` | 4.1.3, cascades to extraction/workflow/KB panels |
| X3 | **2 shared table-header components** get `scope`/`aria-sort`: `Admin SortableTh`, `KnowledgeBasesTab Th` | 1.3.1 across ~12 tables |
| X4 | **Shared accessible IconButton / close button** | 1.1.1 across ~70 icon-only buttons |
| X5 | **`--highlight-on-light` token** (built in pass 1) applied to remaining raw-highlight text/icon-on-light (~15 files) | 1.4.3 / 1.4.11 |

## Perceivable (1.x)

- **1.4.11 focus ring** — X1 (Serious, systemic).
- **1.4.3 gray-on-light sweep (Serious, hundreds).** `text-gray-400/300` (≈2.6:1/1.9:1) and inline `#9ca3af/#aaa/#bbb` on white/gray-50. Confirmed light-bg clusters: WorkflowEditorPanel (~90 inline), AutomationEditorPanel, certification/* light panels, library (VerificationSubmitModal, CatalogCoverageTab, VerifiedCatalog, CollectionsManager), pages (Credentials, Account, TeamSettings, Workflows, Automation, Admin), chat (ChatMessage, ChatInput, ContextLimitDialog, WelcomeExperience), files (DocumentViewer, SpreadsheetViewer, GlobalSearch), workspace (Project*, ItemPicker, CredentialQuickCreate), survey/*. **Skip dark-bg files** (Landing, Demo, Docs, present/*, auth pages, LoginForm, dark knowledge modals). Fix: gray-400/300→gray-500/600; inline `#9ca3af`→`#6b7280`.
- **1.4.3/1.4.11 raw highlight on light (Serious).** FileRow, DocumentPickerModal, ApiKeysTab, certification (JourneyMap/ModuleDetail/CelebrationOverlay/CertificationPanel), AttachmentList, ProjectContextBar, ActivityRail, DocumentViewer → `--highlight-on-light` (text) / darken-thicken (icons).
- **1.1.1 icon-only buttons (~70, Serious) + ~64 title-only (Minor)** — X4. Pervasive `<X>` closes in WorkflowEditorPanel (~14), ExtractionEditorPanel, Admin, TeamSettings, KnowledgePanel, LibraryTab, dialogs.
- **1.3.1 tables no `<th scope>` (Serious)** — X3 + ~12 tables.
- **1.3.1 unlabeled fields** — see 3.3.2 below (shared bucket).
- **1.4.4/1.4.10/1.4.13** — no blocking issues (Minor: a couple fixed-px).

## Operable (2.x)

- **2.4.3 focus trap — ~24 modals pass 1 missed (Serious).** ApplyPreviewModal, 3× TrialExplainerModal, FeedbackPromptCard, Deck, AddToLibraryDialog, ShareWithTeamDialog, VerificationSubmitModal, CatalogImportDialog, RetroactiveBaselineDialog, ExaminerValidationDrawer, SaveWorkflowOutputDialog, CredentialQuickCreateModal, ItemPickerModal, ProjectManageModal, AutovalidateModal, DocumentPickerModal, GenerateTestQueriesModal, KBSourceInspectorModal, GenerateTestCasesModal, ContextLimitDialog, TraceDrawer, SupportChatPanel, ExploreTab filter panel, ChatInput popover. Fix: `<FocusTrap>` + Escape + `role=dialog/aria-modal` (pass-1 pattern, `displayCheck:'none'`).
- **2.4.7 focus rings (Serious):** SupportChatPanel:1060, Account:278, ProjectManageModal:318.
- **2.1.1 keyboard:** drag-reorder `ExtractionEditorPanel:1219` has no keyboard alt (Serious); backdrop-only-close dialogs lacking Escape (Medium).
- **2.4.1 landmarks/skip (Moderate):** present/*, Reviews, ReviewDetail, Organizations, WorkflowEditor, Demo, InviteAccept, Docs (no skip).
- **2.4.6 headings (Moderate):** no `<h1>` — Account, TeamSettings, Credentials, Automation, Organizations, WorkflowEditor, Workspace.

## Understandable + Robust (3.x / 4.x)

- **4.1.3 un-announced status (Critical/Serious).** X2 shared components + primary run/validation progress (ExtractionEditorPanel:2336, WorkflowEditorPanel:7239, Certification:856, Admin save/test/playground) + dozens of per-panel loading/empty/count regions. Fix: `role=status aria-live`; errors `role=alert`; `aria-busy` on in-flight buttons; `aria-hidden` decorative spinners.
- **3.3.2 labels (Serious, largest bucket).** Credentials, CredentialQuickCreateModal, Account, TeamSettings, ResetPassword, Demo, ProjectManageModal (placeholder-only); workspace editors — WorkflowEditorPanel (~57), ExtractionEditorPanel, AutomationCreationWizard, KnowledgePanel, CrossFieldRulesSection, SaveWorkflowOutputDialog; all library/knowledge/files search inputs + filter/sort selects; SurveyFieldRenderer. Fix: `htmlFor`/`id` or `aria-label`.
- **4.1.2 widgets (Serious).** ~11 button-cluster tab bars → ARIA tabs (ExtractionEditorPanel, WorkflowEditorPanel, KnowledgePanel, AutomationsPanel, VerificationQueue); disclosures/accordions → `aria-expanded` + real buttons; sortable headers → `aria-sort` (FileList, KnowledgeBasesTab); radio-card groups → `role=radiogroup/radio`; non-shared toggles → `role=switch`/reuse `Toggle`; comboboxes/menus → `aria-haspopup/expanded`, `combobox/listbox`.
- **3.2.4 / 4.1.3 native dialogs (Serious).** `KBTestQueriesTab:109` `window.confirm` → `useConfirm`; **16 `alert()`** (ApiKeysTab, FileBrowser ×5, KBTestQueriesTab, CatalogImportDialog, VerifiedCatalog, Admin ×8) → `toast()`.
- **3.3.1 error identification (Moderate).** Loose error text not associated — SaveWorkflowOutputDialog, CrossFieldRulesSection, AutomationCreationWizard, ExtractionEditorPanel, WorkflowEditorPanel, KnowledgePanel, KBPickerModal, VerificationSubmitModal. Fix: `role=alert` + `aria-invalid`/`aria-describedby`.
- **3.1.1 lang** — PASS. **3.3.4** — largely satisfied (only the one native confirm).

---

## Remediation plan (batched; shared fixes first)

1. **Shared cascades** — X1 focus ring, X2 four status components, X3 two `<Th>` components, X4 IconButton, X5 highlight-on-light. (Biggest impact-to-effort.)
2. **Contrast sweep** — bulk gray-400/300→500/600 + inline `#9ca3af`→`#6b7280` on confirmed-light files.
3. **Modal focus-trap sweep** — ~24 modals, mechanical (pass-1 pattern).
4. **Forms labeling** — credential/account/team/demo forms, then the workspace editors.
5. **Widget roles** — tab bars → ARIA tabs; disclosures; sortable headers; radio cards; toggles.
6. **Status live regions** — per-panel, after the shared components.
7. **Landmarks/`<h1>`** on standalone pages; native `alert()`/`confirm` → toast/useConfirm.
8. Verify (`make ci`) throughout; parallelize independent files.

Scale: ~60+ files, hundreds of edits — larger than pass 1. Recommend executing in the batch order above with `make ci` gating each batch.

---

## Pass-2 status: COMPLETE

All findings above remediated across ~88 files. Verified green: `tsc -b` clean,
**0 lint errors**, 201 tests pass, build clean. Executed via the shared
cascades (focus ring, status components, table headers) + a per-area agent
fleet (each owning distinct files), with central `make ci` verification and a
cleanup pass for files the sweep missed (workspace/KnowledgePanel,
AutovalidateWizard, CompareRunsView, ProgressRow). Pass 3 will re-audit from
scratch and add an automated axe/Lighthouse contrast gate.
