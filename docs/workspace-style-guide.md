# Workspace styles

Task surfaces use the tokens in `frontend/src/styles/workspace-polish.css`. Files, Projects, Automations, Knowledge, Library and their editors share these values. Dark navigation and embedded document/tutorial illustrations retain their distinct roles.

## Text and color

Use `--workspace-font-meta` for secondary facts (12px at the default browser size), `--workspace-font-control` for controls (13px), and `--workspace-font-body` for task copy (14px). Card, section and page titles use the corresponding 16/18/20px tokens. These sizes use rem units so browser text preferences apply. Avoid shrinking metadata to make a row fit; wrap the text or let the row grow.

Use `--workspace-text` and `--workspace-muted` on `--workspace-surface` and `--workspace-canvas`. Status foreground/background pairs are `info`, `success`, `warning` and `danger`, with a `-surface` suffix for each background. Pair status color with text. Use the configured highlight for selected/primary controls, `--highlight-text-color` on a solid highlight and `--workspace-accent-ink` on soft accent surfaces.

## Geometry

Shared spacing tokens are `--workspace-space-2`, `-4`, `-6`, `-8`, `-12`, `-16`, `-20`, `-24` and `-32`. Use 4–8px inside a compact control, 8–12px between related controls, 16px around a task group and 24px around a dialog body where space permits. These are a scale, not fixed heights: long names and larger browser text must be able to grow.

Use `--workspace-radius-small` (6px) for controls, `-medium` (8px) for cards and `-large` (12px) for dialogs. Pills and circular icons retain their geometry. Neutral borders use `--workspace-border`; modal elevation uses `--workspace-shadow-dialog`. The standard control minimum is 36px and list-row minimum is 44px, with rows growing to fit their content.

## Verification

Run the production visual-review recipes after changing shared tokens. Check narrow and short screens, long names, menus, nested dialogs and source/tool navigation. Inspect screenshots directly as well as checking contrast and overflow; axe cannot detect every occlusion or poor layout. Preserve failed runs as diagnostics and only select completed, clean runs in the gallery.

## Actions

Use `shared/ActionButton` for task commands. Choose `primary` for the next or final task action, `secondary` for alternatives, `quiet` for low-emphasis or icon-only actions, and `destructive` for a deliberate removal confirmation. Pass an accessible name for an icon-only button. Keep a verb or pending-state label visible while busy; use `loading` for the shared spinner or `aria-busy` when the caller renders its own progress content.

Workspace controls and panel-aware portals share target-size and focus rules. Keep row actions reachable without hover. Use the visual-review harness's `smallControls` metric to find enabled controls below 24px; buttons normally use at least 36px. A clean metric does not replace checking for clipped or overlapping controls.
