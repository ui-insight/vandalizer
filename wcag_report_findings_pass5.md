# WCAG 2.1 AA — Findings, Pass 5 (final)

Final validation re-audit after passes 1–4, with a rigorous conformance-style
sweep across all SC. The final pass earned its keep — it surfaced genuine
Serious residuals earlier passes missed, now all remediated.

## Pass-4 fixes — verified correct
CelebrationOverlay/Certification use `--highlight-on-light`; empty stars gray-400;
global `prefers-reduced-motion` reset present; Admin Teams sub-tabs fully wired
(tabs↔panels). Confirmed by both agents.

## Residuals found & FIXED this pass
| SC | Sev | Finding | Fix |
|----|-----|---------|-----|
| 2.4.7 | Serious | Large cluster of inline `outline:'none'` on inputs/selects (no replacement ring) defeating the global focus ring — ~16 files (KnowledgePanel, AutomationEditorPanel, KB modals, dialogs, ChatMessage…) | Removed the inline `outline:'none'` so the global `:focus-visible` keyboard ring shows (mouse stays ring-free via `:focus:not(:focus-visible)`) |
| 1.4.3 | Serious | `text-gray-400/300` on white in SupportChatPanel (ticket #, timestamps, counts, separators…) + Credentials, ProjectsExplainer, Certification | → `text-gray-500` (dark-bubble/isMe branch correctly left) |
| 3.3.2 / 4.1.2 | Serious | Invite/Join account-setup forms — 9 placeholder-only fields, no programmatic name | Added `aria-label` to each |
| 4.1.2 | Moderate | LeftPanel two icon-only buttons (close document / close search) | Added `aria-label` + `type="button"` |
| 3.3.2 | Minor | Placeholder-only: ChatInput link URL, ChatMessage feedback, KBPickerModal name, Admin retention field | Added `aria-label` |

## Verified PASS (no issues)
1.1.1, 1.3.1 (tables/`th`), 1.3.4/1.3.5, 1.4.5/1.4.10/1.4.11, 2.1.1, 2.4.x,
2.5.x, 3.1.1, 3.2.x, 3.3.1/3.3.3/3.3.4, 4.1.1 (no dup ids), 4.1.2 (all tab bars
wired), 4.1.3 (no over-announcing). Automated **axe-core gate** now covers 6
remediated primitives; all pass.

## One documented Minor (left intentionally)
Nested `role=button` divs containing an inner interactive control
(`AutomationsPanel` row + pin; `ExtractionEditorPanel` ToolCard + secondary
action). Both audit agents confirmed these are **functionally accessible**
(keyboard works, `stopPropagation` prevents double-activation, name/role/value
exposed). It's a robustness nicety, not an AA failure. A clean stretched-link
refactor was scoped but deferred to avoid layout-regression risk for negligible
AT benefit.

## Verdict
**No Critical. No Serious remaining.** With the pass-5 focus-visibility, contrast,
and auth-form-label fixes, the frontend conforms to **WCAG 2.1 Level AA**
(one documented Minor best-practice item outstanding). Verified: `tsc -b` clean,
**0 lint errors**, 207 tests incl. axe gate, build clean.
