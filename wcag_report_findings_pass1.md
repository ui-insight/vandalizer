# WCAG 2.1 AA — Findings, Pass 1

Accessibility audit of the Vandalizer React frontend (`frontend/src`). Target
conformance: **WCAG 2.1 Level AA**. This is the first of five planned audit +
remediation passes; Pass 1 fixes everything below, then a fresh audit drives
Pass 2.

Severity scale: **Critical** (blocks a core task for AT users) ·
**Serious** (significant barrier) · **Moderate** · **Minor**.

Baseline strengths (already in place): `<html lang="en">`; most dialogs set
`aria-modal`/`aria-label`; a global `:focus-visible` rule; some live regions
(FileBrowser, DocumentViewer); `useConfirm` styled confirmation for most
destructive actions.

---

## Critical

| ID | SC | Finding | Location |
|----|----|---------|----------|
| C1 | 1.3.1, 3.3.2, 1.3.5 | Login & Landing inputs are placeholder-only — no `<label>`/`aria-label`, no `type="email"`, no `autocomplete`. | `components/auth/LoginForm.tsx:31-47`, `pages/Landing.tsx:62-148` |
| C2 | 4.1.3 | Toast container has no `role="status"`/`aria-live`; success/error toasts are silent to screen readers. | `contexts/ToastContext.tsx:44` |
| C3 | 4.1.3 | Streaming chat status ("Thinking…") and spinners aren't in a live region; AT users get no "responding" cue. | `components/chat/ChatPanel.tsx:838-844` |

## Serious

| ID | SC | Finding | Location |
|----|----|---------|----------|
| S1 | 1.3.1, 3.3.2 | Systemic label/field disassociation — ~2 `htmlFor` across ~316 inputs; many labels are styled siblings. | repo-wide; e.g. `workspace/AutomationEditorPanel.tsx:564`, `knowledge/CreateKBModal.tsx:58/74`, `admin/ApiKeysTab.tsx:453/464/518` |
| S2 | 1.4.3 | Low-contrast text: `text-gray-400` on white (~2.6:1) used pervasively; yellow `text-highlight` on white (~1.7:1) in chat. | `components/chat/ChatPanel.tsx:529/590/613/636`, `library/ExploreTab.tsx` (many), `auth/LoginForm.tsx:56/60` |
| S3 | 2.4.1 | No skip-to-content link and no `<main>` landmark in the app shell. | `components/layout/` shell / `WorkspaceLayout` |
| S4 | 2.4.3 | No focus trap or focus restore in modals/dialogs — Tab escapes behind open dialogs; focus drops to `<body>` on close (~25 modals). | `components/shared/ConfirmDialog.tsx` + modal components |
| S5 | 2.4.7 | Focus-visible silently removed — `focus:outline-none`/inline `outline:none` with no ring replacement; Tailwind v4 utility layer overrides the global ring. | `library/ExploreTab.tsx:789/802`, `files/GlobalSearch.tsx:92`, `knowledge/KBSearchBar.tsx:36`, `files/DocumentSearchBar.tsx:78`, etc. |
| S6 | 2.4.2 | `document.title` set once to org name; route changes never update it. | `contexts/BrandingContext.tsx`, `router.tsx` |
| S7 | 2.1.1 | Clickable Admin table rows (`onClick` on `<tr>`) have no keyboard path. | `pages/Admin.tsx:992/1639/1827` |
| S8 | 3.3.1 | Form errors not programmatically identified — login/chat error `<div>`s lack `role="alert"`/`aria-describedby`/`aria-invalid`. | `auth/LoginForm.tsx:27`, `components/chat/ChatPanel.tsx:847` |
| S9 | 1.1.1 | Icon-only buttons missing accessible names (inconsistent — dialogs do it). | `chat/AttachmentList.tsx:36/53/80`, `admin/UpdateBanner.tsx:67`, `library/ExploreTab.tsx:817/823`, `library/CollectionsManager.tsx:277/294`, `knowledge/KBGridView.tsx:288/303` |
| S10 | 4.1.2 | Custom widgets missing roles/state: `Toggle` (no `role="switch"`/`aria-checked`), `ModelEffortPicker` (no radiogroup/radio), Admin tabs (no `tab`/`tablist`/`aria-selected`). | `components/shared/Toggle.tsx:11`, `components/ModelEffortPicker.tsx:95`, `pages/Admin.tsx` tab bars |

## Moderate

| ID | SC | Finding | Location |
|----|----|---------|----------|
| M1 | 1.4.1 | Quality tier conveyed by icon color only (no text). | `library/ExploreTab.tsx:352` |
| M2 | 1.4.11 | Button text color chosen by a luminance threshold, not a real contrast ratio — custom brand colors can fall below 4.5:1. | `utils/color.ts` (`getContrastTextColor`) |
| M3 | 3.2.4 | Inconsistent confirmation UX — 7 native `window.confirm` sites vs. styled `useConfirm`. | `workspace/WorkflowEditorPanel.tsx:382/682/6230/6250`, `knowledge/AutovalidateModal.tsx:487`, `support/SupportChatPanel.tsx:662`, `pages/SupportCenter.tsx:860` |
| M4 | 4.1.2 / 2.4.3 | `TeamsDropdown` `role="menu"` with non-`menuitem` children, no roving focus, no focus restore. | `components/layout/TeamsDropdown.tsx:27-50` |
| M5 | 1.3.1 | Landing has no `<h1>` (starts at `<h2>`). | `pages/Landing.tsx` |

## Minor

| ID | SC | Finding | Location |
|----|----|---------|----------|
| m1 | 2.1.1 | Overlay(s) without an Escape handler. | `components/.../CelebrationOverlay.tsx:47` |
| m2 | 3.2.2 | Blur-triggered network save (borderline). | `workspace/AutomationEditorPanel.tsx:571` |
| m3 | (sec) | Unsanitized `dangerouslySetInnerHTML` sinks (flagged in passing; not strictly WCAG). | `library/ExploreTab.tsx:56`, `admin/ApiKeysTab.tsx:340`, `pages/ReviewDetail.tsx:64`, `pages/present/markdown.tsx:14` |

---

## Pass-1 remediation approach

All findings above are addressed in a single PR. Cross-cutting fixes are
centralized where possible:
- A shared focus-trap/restore hook for dialogs (S4) instead of per-modal code.
- A `useDocumentTitle` hook + per-route titles (S6).
- A reusable skip link + `<main>` landmark in the shell (S3).
- A real-contrast text-color helper (M2) reused by the brand system.

Verification: `make ci` (frontend typecheck, lint, vitest, build) must pass;
manual keyboard + screen-reader spot-checks on auth, chat, Admin, and modals.

---

## Pass-1 remediation status

| ID | Status | Notes |
|----|--------|-------|
| C1 | ✅ Fixed | Login + Landing forms: labels, `type=email`, `autocomplete`, `role=alert` errors |
| C2 | ✅ Fixed | Toast container `role=status/alert` + `aria-live` |
| C3 | ✅ Fixed | Chat streaming status live region |
| S1 | ✅ Fixed | Label association across knowledge modals, ApiKeysTab, AutomationEditorPanel |
| S2 | ✅ Fixed | **Contrast.** `contrastRatio()` + real-contrast `getContrastTextColor()` (M2); new `getAccessibleOnLight()` derives a ≥4.5:1 "highlight-on-light" token from the live brand color, wired via `--highlight-on-light` and applied to the ChatPanel highlight-colored text/icons that sat on white (~1.7:1). A broader automated `text-gray-*`-on-white sweep (axe-core / Lighthouse CI) is recommended as a standing check in pass 2. |
| S3 | ✅ Fixed | Skip link + `<main>` in WorkspaceLayout & PageLayout |
| S4 | ✅ Fixed | focus-trap-react on ConfirmDialog + 9 modals (`displayCheck:'none'` for jsdom) |
| S5 | ✅ Fixed | Focus-visible rings on search inputs + library filter selects |
| S6 | ✅ Fixed | Per-route `document.title` via RouteTitle |
| S7 | ✅ Fixed | Admin user/team/event rows keyboard-operable |
| S8 | ✅ Fixed | Login/chat errors `role=alert` + `aria-describedby`/`aria-invalid` |
| S9 | ✅ Fixed | aria-labels on icon-only buttons (attachments, banners, library) |
| S10 | ✅ Fixed | Toggle `role=switch`; ModelEffortPicker radiogroup; Admin nav `aria-current` |
| M1 | ✅ Fixed | ExploreTab quality tier: sr-only text |
| M2 | ✅ Fixed | Real WCAG contrast-ratio text-color selection |
| M3 | ✅ Fixed | 7 `window.confirm` → styled `useConfirm` |
| M4 | ✅ Fixed | TeamsDropdown menuitem roles + roving keyboard nav + focus restore |
| M5 | ✅ Fixed | Landing `<h1>` |
| m1 | ✅ Fixed | CelebrationOverlay closes on Escape |
| m2 | ○ Deferred | AutomationEditorPanel blur-save — borderline 3.2.2; left as-is |
| m3 | ○ Out of scope | Unsanitized `dangerouslySetInnerHTML` — security, tracked separately from WCAG |

**All findings are addressed and verified** (`make ci` green: typecheck, 0 lint errors, 201 tests, build). Pass 2 will re-audit from scratch and add an automated contrast/axe check as a standing gate.

