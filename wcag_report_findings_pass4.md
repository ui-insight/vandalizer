# WCAG 2.1 AA — Findings, Pass 4

Re-audit after passes 1–3, with an explicit **regression check** on pass-3's
structural changes plus a residual sweep.

## Headline
- **No Critical issues.**
- **Pass 3 introduced no regressions** — both audit agents independently verified:
  no duplicate `id`s from the Admin/SupportCenter label sweep; downgraded tab
  roles have no orphaned ARIA; `aria-controls` targets all resolve; the reworked
  `aria-live=off` + `sr-only` phase regions announce correctly; the nested-button
  → `role=button` div conversions and the combobox `aria-activedescendant` are
  correct and keyboard-operable; `useConfirm`/`toast` conversions are async-correct;
  zero native `confirm/alert/prompt` remain.

## Findings (all remediated this pass)
| SC | Sev | Finding | Fix |
|----|-----|---------|-----|
| 1.4.3 | Serious* | Brand-yellow used as *text* on white in the certification celebration overlay ("Certified Professional", XP number) — ~1.9:1 with the default theme | → `--highlight-on-light` (CelebrationOverlay) |
| 4.1.2 | Moderate | Admin **Teams sub-tabs** had `role=tab` but no `aria-controls`/`tabpanel` (only one of ~11 tab bars) | Added `id`+`aria-controls` on tabs, `role=tabpanel`+`aria-labelledby` on the 3 panels |
| 1.4.11 | Moderate/Minor | Highlight-colored icons on white (CelebrationOverlay, Certification page) | → `--highlight-on-light` |
| 1.4.11 | Minor | Empty rating stars `text-gray-300` (~1.5:1) | → `text-gray-400` (CelebrationOverlay, CertificationPanel, ModuleCard, ModuleDetail) |
| 2.3.3 | Minor (AAA) | Spinners / pulse / shimmer not covered by `prefers-reduced-motion` | Added a global reduced-motion reset in `index.css` |

*Serious but theme-mitigated — only fails with the shipped default yellow; a dark
custom highlight passes. Fixed regardless.

## Deliberately left (Minor, documented)
- Nested `role=button` divs contain an inner interactive control (AutomationsPanel
  row + pin; ExtractionEditor ToolCard + secondaryAction). Both agents confirmed
  these are **functionally correct** (stopPropagation, no double-activation);
  hoisting the inner control risks layout regressions for negligible AT benefit.
  Re-evaluate in pass 5 if a clean refactor is available.

## Status: COMPLETE
Verified green: `tsc -b` clean, **0 lint errors**, 205 tests (incl. axe gate),
build clean. Pass 5 (final re-audit) is expected to be essentially clean.
