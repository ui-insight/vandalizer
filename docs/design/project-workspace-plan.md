# Unified Project Workspace: design and build plan

**Repo:** `ui-insight/vandalizer`. **Base branch:** `major/agentic-chat` (not `main`). Code references are to `origin/major/agentic-chat` @ `58486cfa`.
**Source:** an enhancement request ("a unified project workspace"), with a mockup and a screenshot of today's screen.
**Goal:** opening a project feels like entering that project's own workspace. One header, a small set of tabs, and chat on the side. Every current project feature stays reachable, and nothing moves to a place that hides it.

---

## 1. What "grade A" means here

The design is done when all of these hold:

1. **One place for project actions.** Every project action lives in the project header, its **More** menu, or a tab. Today they are spread over five places (§2).
2. **The inbox is always reachable.** The project's deadlines, required material and limits never depend on the chat being empty (§2, problem 1).
3. **Navigation says where you are.** The left rail highlights **Projects**, and a breadcrumb reads `Projects › <project title>`. Exactly one way out of the project.
4. **Chat is untouched.** The right-hand Assistant | Library column keeps all its current controls: model picker, Add, Skills, project scope chip, approval cards.
5. **No feature is lost.** Everything in the "Feature inventory" (§3) has a home in the new layout. Viewers (read-only role) still see what they can see today, and nothing they can't.
6. **The URL holds the state.** The tab and the open item live in the URL, so reminder links (`?deadline=`), Back/Forward and refresh all work.
7. **Works at every width.** Desktop (≥1100px), auto-docked rail (<1100px) and compact/mobile, with no horizontal scroll.
8. **Accessible.** A real `tablist` with arrow keys, the More menu as a `menu`, visible focus, focus returned after closing menus, and each tab panel labelled.
9. **Honest states.** Every tab has loading, empty, error-with-retry and no-access states. Empty states say what was checked, never just "nothing here".
10. **Tested.** Vitest coverage for routing, roles, each tab's states and the moved controls. The full backend and frontend suites pass locally. CI does **not** run on PRs into `major/agentic-chat`, so run the gates yourself (§9).

---

## 2. Today: the problems to solve

Confirmed in code:

| # | Problem | Where |
|---|---|---|
| 1 | **The project inbox shows only in the chat's empty state.** "Due and needed" is drawn inside `showContextualEmptyState`, gated on `messages.length === 0`. After the first message it's gone until **New chat**. | `frontend/src/components/chat/ChatPanel.tsx:847` (condition), `:1212` (`<RAInbox projectUuid=…>`) |
| 2 | **The rail highlights Chat inside a project,** although the URL is `?mode=projects`. | `frontend/src/components/workspace/WorkspaceLayout.tsx:120-121` (`isChat` includes `projects` + active project) |
| 3 | **Project actions in five places:** header (Open files, Manage project, Exit project), Award snapshot strip (Build snapshot, Share as Page), inbox card (Calendar, Reminders), Manage project dialog (Overview/Pages/Tools/Sharing), chat footer (a second Exit project). | `workspace/ProjectContextBar.tsx`, `projects/AwardSnapshotPanel.tsx`, `chat/RAInbox.tsx`, `workspace/ProjectManageModal.tsx:317`, `chat/ProjectChatBadge.tsx:49` |
| 4 | **Inbox rows repeat the project name** inside the project, and spend 3–4 lines per deadline (title, date, project link, one bordered chip per source). | `chat/RAInbox.tsx` (`InboxRow`: project link button + per-source buttons) |
| 5 | **Pinned tools have no visible entry point.** `ProjectWorkOverview` (Ask about project / Pinned tools) is mounted nowhere; only a test imports it. Pins are reachable only in Manage project → Tools. | `projects/ProjectWorkOverview.tsx`, `workspace/ProjectContextBar.test.tsx:4` |
| 6 | **Files, Pages and Templates are a left-panel toggle** (`?files=pages|templates`), separate from the project concept. | `workspace/LeftPanel.tsx:50-51, 298-302` |

---

## 3. Feature inventory (all must survive)

| Feature | Today | Data / API |
|---|---|---|
| Title, status (Active, …), description, project context ("brief") | Header and Manage → Overview | `useProject(uuid)` → `Project` (`types/project.ts:18`); context is used by chat |
| Status change, title/description edit | Manage → Overview | existing project update API in `ProjectManageModal` |
| Award snapshot: facts with page cites, budget years, deadlines (upcoming/overdue/done/needed), last run, Pages | Collapsible strip under header | `getAwardSnapshot(uuid)` → `AwardSnapshot` (`api/awardSnapshot.ts`) |
| Build / rebuild snapshot, Share snapshot as Page | Snapshot strip | same module |
| RA inbox: open items, Done, Dismiss, Keep (deleted source), Add to calendar, Show dismissed, per-item sources, **Add deadline** (PR #1145) | Chat empty state | `api/obligations.ts` (`getInbox(…, projectUuid)`, etc.) |
| Calendar file (project), Reminder settings link | Inbox card header | `downloadDeadlineCalendar({project})`, `/account#deadline-reminders` |
| Files: upload, folders, list, document viewer, split with chat | Left panel (Documents) | existing `LeftPanel` / file browser |
| Pages for this project | Left panel (Pages), Manage → Pages, snapshot | `PagesBrowser projectUuid=…` |
| Templates | Left panel (Templates) | `TemplatesBrowser` (not project-scoped) |
| Pinned tools: list, open with project selected, pin/unpin, default Skill | Manage → Tools | `useProjectPins`, `ProjectPinsSection`, `ProjectSkillsSection`; `/api/projects/{uuid}/pins`, `/default-skill` |
| Members, roles, invite link, share with team, make personal, leave | Manage → Sharing | `/api/projects/{uuid}/members`, `/invite-link(s)`, `/share-with-team`, `/make-personal`, `/leave` |
| Duplicate project | Projects list | `/api/projects/{uuid}/duplicate` |
| Exit project | Header **and** chat footer | `exitProject()` in `WorkspaceContext` |
| Project chat scope chip, Ask about this project, suggested actions | Chat | `ProjectChatBadge`, `ProjectSuggestedActions` |
| Reminder deep link `?deadline=<uuid>` focuses an inbox row | Home / project | `router.tsx:212`, `focusedObligationUuid` in `WorkspaceContext` |

---

## 4. Target layout

```
┌ Rail ┐┌───────────────────────────── Project header ─────────────────────────────┐
│Proj ●││ Projects › NIFA Subaward UI-OSU-2026-0412   [Active ▾]      (avatars) [Share] [+ Add file] │
│ Chat ││ USDA NIFA · UI → Oregon State · $95,550 · Mar 1, 2026 – Aug 31, 2027 · Award snapshot ›     │
│ Files││ [Build snapshot] [Calendar] [Reminders] [More ▾]                                           │
│ …    │├──────── Tabs ────────────────────────────────────┬──────── Chat column ──────────┤
│      ││ Overview · Inbox (6) · Files (1) · Pages · Activity│ Assistant | Library            │
│      ││                                                     │ (unchanged)                    │
│      ││  <tab panel>                                        │                                │
└──────┘└─────────────────────────────────────────────────────┴────────────────────────────────┘
```

### 4.1 Header (replaces `ProjectContextBar` + the `AwardSnapshotPanel` strip)

- **Row 1**
  - **Breadcrumb:** `Projects` (link, does `exitProject()` and opens the Projects list) `›` the title.
  - **Status:** a status badge. Owners and editors can change it from the badge's menu; viewers see a plain badge.
  - **Members:** up to 3 avatars from `/members`, plus a `+N` count.
  - **Share:** opens the existing Sharing content, moved out of the modal (§4.4).
  - **Add file:** the primary button. It uploads into the project's root folder, using the same upload as the Files panel. Hidden for viewers.
- **Row 2: summary line.** Built from the Award snapshot facts when a snapshot is `ready`: sponsor, parties, amount, period. Each part shows only if the snapshot states it, with no invented values. Ends with an **Award snapshot ›** link that opens the Overview tab's snapshot section.
  - **Snapshot `not_built`:** show the description, or "No snapshot yet · Build snapshot".
  - **`out_of_date`:** show a quiet "Snapshot out of date" marker.
- **Row 3: actions.**
  - **Build / Rebuild snapshot** (managers only).
  - **Calendar:** downloads the project's `.ics`. Disabled, with a tooltip, when the project has no dated deadlines.
  - **Reminders:** links to `/account#deadline-reminders`.
  - **More ▾** (a `menu`):
    - Edit title, description and status
    - Project brief (the `context` used by chat)
    - Pinned tools
    - Share snapshot as Page
    - Duplicate project
    - Leave project, only when `can_leave`
    - Back to projects
- **Remove** the second Exit project from `ProjectChatBadge` (keep the scope chip itself). The breadcrumb and "Back to projects" are the only exits.
- **Compact width:** rows 2–3 collapse. The summary is truncated to one line with a "Details" disclosure, and the row-3 actions move into **More**.

### 4.2 Tabs

The tab lives in the URL: `?mode=projects&project=<uuid>&ptab=overview|inbox|files|pages|activity`. The default is `overview`.

`ptab` is a **new** param; don't reuse `tab`, which is the right column's Assistant | Library. Add it to `validateSearch` in `router.tsx`.

**Overview** (read-only digest; every item links to its home tab)
- **Coming up:** the next 3–5 open deadlines, from `snapshot.deadlines.upcoming` and `overdue`, or from `getInbox(false, uuid)` when there's no snapshot.
  - Each row: date · title · source page link · relative time ("in 34 days", amber when ≤14, red when overdue).
  - Calculated deadlines show "how calculated" (`deadline_calculation.formula`).
- **Needed and limits:** required material and limits (in-conflict limits first), from `snapshot.deadlines.needed` or the inbox.
- **Key facts:** the snapshot facts with page citations. Unsupported values are marked as now. Include budget years and the "not found in documents" list.
- **Recent files:** the 5 newest project documents.
- **Recent Pages:** `snapshot.pages`.
- **Last run:** `snapshot.last_run`.
- The full Award snapshot stays available here (it replaces the collapsible strip). Reuse `AwardSnapshotPanel` content, not its strip chrome.

**Inbox ( count )**
- Move `RAInbox projectUuid=…` here, out of `ChatPanel`'s empty state. **Fixes problem 1.**
- Keep all actions: Done, Dismiss, Keep/Dismiss for deleted sources, Add to calendar, Show dismissed, Add deadline.
- Inside a project, **drop the per-row project link** (problem 4). Collapse sources into one line: `Source: subaward.pdf p. 1 · +2`, expandable. Target ≤2 lines per row.
- `?deadline=<uuid>` inside a project opens this tab and focuses the row; this works today on Home.
- The count badge is the number of open, undismissed items.
- **Optional, needs backend: "Found but not added (N) · See why".** The proposals chat or the workflow refused, with their reasons and an **Add by hand** shortcut that pre-fills the Add deadline form. Refused proposals are **not persisted today**; see §6.

**Files ( count )**
- The project's file browser, upload and folders, i.e. the left panel's Documents view scoped to the project.
- Opening a document keeps today's behaviour: the viewer opens beside chat (`chatSplitOpen`).
- Templates stays in the global Files area; it isn't project-scoped. Link to it from **Pages** ("Start from a template").

**Pages**
- `PagesBrowser projectUuid=… canManage=…`, which is already project-aware.
- "Share snapshot as Page" also appears here.

**Activity**
- A newest-first list of the project's workflow and extraction runs: title, status, who, when, and a link to the run.
- **Data exists, endpoint doesn't:** `ActivityEvent` (`backend/app/models/activity.py`) has `project_uuid`, and `award_snapshot._activity()` already queries it for `last_run`.
- **New endpoint:** `GET /api/projects/{uuid}/activity?limit=&before=`, authorized like the other project routes (`get_authorized_project`), paginated.
- Optional later: inbox events (added, done, superseded by an amendment), from obligation timestamps.

**Tools.** Not a tab. Pinned tools live under **More → Pinned tools**, and as a "Pinned tools" card on Overview when any exist. That revives what `ProjectWorkOverview` was meant to do. Delete `ProjectWorkOverview` and its test once this replaces it.

### 4.3 Chat column

Unchanged: Assistant | Library, the composer and all its controls.

- The "Ask about this project" empty state stays. It no longer contains the inbox; replace it with a one-line "N items due or needed · Open inbox" link that switches to the Inbox tab.
- `ProjectSuggestedActions` stays.

### 4.4 Manage project dialog

- Fold its sections into the new layout:
  - **Overview** (description, status, brief, resources) → More → Edit, and More → Project brief, as small dialogs or a side sheet.
  - **Pages** → the Pages tab.
  - **Tools** → More → Pinned tools: a sheet reusing `ProjectPinsSection` and `ProjectSkillsSection`.
  - **Sharing** → the header's Share: a sheet reusing the sharing section.
- Then remove `ProjectManageModal`, or keep it only as the container for those sheets. Don't leave two ways to edit the same thing.

### 4.5 Rail and navigation

- `WorkspaceLayout.tsx:120-121`: inside a project, highlight **Projects**, not Chat. Check every place that reads `isChat` for layout (collapse rules, `workspaceHeading`, compact panel switcher). The layout behaviour (chat column visible) must not change; only the highlight and heading do. Split the "chat column visible" flag from the "rail item highlighted" flag.
- The sr-only `h1` becomes the project title.

---

## 5. Roles and states

| Role | Sees | Hidden or disabled |
|---|---|---|
| owner / editor | everything | none |
| viewer ("Read only") | header (no Add file, no Build snapshot, status badge not editable), all tabs read-only, Calendar, Reminders, Share (view members only) | Add file, Build/Rebuild, Add deadline, Done (shared), Edit, Brief edit, Pins edit. Dismiss stays: it's personal. |

Each tab needs these states:
- **Loading:** a skeleton.
- **Empty:** says what was checked ("No deadlines saved to this project yet. Ask chat to find them in your documents, or Add deadline.").
- **Error:** a message with Retry.
- **No access:** 403, which can happen after being removed while viewing.

Existing behaviour to keep:
- The inbox's 60s refresh and refresh-on-focus.
- The snapshot's `building` polling.
- The reminder deep link's "no longer open here" message.

---

## 6. Backend work

Only the Activity tab needs backend work; the optional inbox row is a separate ticket.

1. **Activity tab:** `GET /api/projects/{project_uuid}/activity`.
   - Returns runs from `ActivityEvent` filtered by `project_uuid`, newest first: `{type, title, status, user display name, started_at, finished_at, link target}`.
   - Paginated (`limit` ≤ 50, `before` cursor), and project-access-checked.
   - Add `getProjectActivity` in `frontend/src/api/projects.ts`.
   - Run `make endpoint-map` and check both orphan lists in `scripts/ui_endpoint_map.md`. `make backend-static` gates this.
2. **Optional, separate ticket: "Found but not added".**
   - Today `propose_obligations` (chat) and the workflow intake step return rejected items with reasons, but nothing stores them.
   - Needs a small `ObligationProposalRejection` record (project, title, reason, source, who, when, from chat or workflow), written by `obligation_service.propose` callers, plus `GET /api/obligations/rejected?project_uuid=`.
   - Product decision needed: how long they live, and whether Dismiss clears them.

No other API changes. Everything else reuses existing endpoints (§3).

---

## 7. Build plan (PR-sized slices)

Each slice is one PR into `major/agentic-chat` and is shippable alone.

1. **Quick fixes** (no new layout; can ship first)
   - **Inbox:** move it out of the chat's empty state into a persistent spot (interim: a Due and needed view in the left panel next to Documents/Pages). Drop the per-row project link inside a project.
   - **Rail:** highlight Projects while inside a project (split the flags, §4.5).
   - **Exit project:** remove the duplicate from `ProjectChatBadge`.
   - **Pinned tools:** delete the dead `ProjectWorkOverview`, or mount its pinned-tools entry.
2. **Header:** the new `ProjectHeader` replaces `ProjectContextBar` and the snapshot strip.
   - Breadcrumb, status, members, Share, Add file, summary line, Build snapshot, Calendar, Reminders, More menu.
   - The Manage project sections move into sheets opened from More and Share.
3. **Tabs:** `ProjectTabs` plus `?ptab=`, with Overview, Inbox, Files and Pages. The inbox's interim home from slice 1 moves here. The chat empty state gets the "Open inbox" link.
4. **Activity:** the backend endpoint and the tab.
5. **Optional:** "Found but not added" (backend record, endpoint, Inbox row).

Suggested new components, in `frontend/src/components/projects/`:
- `ProjectHeader.tsx`
- `ProjectMoreMenu.tsx`
- `ProjectTabs.tsx`
- `ProjectOverviewTab.tsx`
- `ProjectInboxTab.tsx` (wraps `RAInbox`)
- `ProjectFilesTab.tsx`
- `ProjectPagesTab.tsx`
- `ProjectActivityTab.tsx`

Reuse existing components rather than copying them.

---

## 8. Acceptance tests

Vitest unless noted.

- **Navigation and URL**
  - Inside a project, the rail's Projects item has `aria-current`; Chat doesn't.
  - The breadcrumb `Projects` link exits the project and shows the list.
  - `?ptab=` round-trips: switching tabs updates the URL, and loading a URL opens that tab. An invalid value falls back to Overview.
  - `?deadline=<uuid>` inside a project opens the Inbox tab and focuses the row.
- **Inbox**
  - Still visible after sending a chat message (regression test for problem 1).
  - Inbox rows inside a project have no project link.
  - Viewers: no Add file, Build snapshot, Add deadline or Done. Dismiss works.
- **More menu**
  - Every item works, and focus returns to the More button on close.
  - Arrow keys move through the tabs (`tablist`).
- **Feature inventory:** each row in §3 has a test that the control exists and calls the same API as before.
- **Activity** (backend pytest): the endpoint returns only this project's events, is ordered and paginated, and gives 404 for no access.
- **Responsive:** at compact width, the header actions move into More, and nothing scrolls horizontally (a visual check on dev, with screenshots in the PR).

---

## 9. Repo rules (from `CLAUDE.md` and the team's ticket workflow)

- Branch per slice off `origin/major/agentic-chat`; PR with `--base major/agentic-chat`.
- **Every PR adds a `CHANGELOG.md` entry under `[Unreleased]`.**
- CI does not run on that branch, so run locally, in full, before asking for review:
  - `make backend-static`, which includes the endpoint map check
  - `cd backend && uv run pytest`
  - `cd frontend && npx tsc -b && npx eslint src && npx vitest run`
  - Node 24, not 26; `uv` for Python, never `pip`.
- When adding or changing a route or a `frontend/src/api/*.ts` call, run `make endpoint-map` and read both orphan lists.
- Prod runs v4.11 from `main`; this work is agentic-chat only, so no data migration.

---

## 10. Open questions for product

1. Should **Overview** or **Inbox** be the default tab? (Plan: Overview, with the inbox count visible in the tab label.)
2. Does **Add file** belong in the header, or only in the Files tab? (Plan: header, since it's the most common action.)
3. Should "Found but not added" (§6.2) be built now or later?
4. Should Templates stay global, or become project-aware?
5. On compact screens, should the tabs become a select menu or stay as a scrolling tab row?

## 11. Not in scope

- Chat behaviour, models, Skills, approvals.
- The Home (all-projects) inbox. It keeps its current place on Home; only the per-project inbox moves.
- Projects list page redesign.
- Visual theme changes (the mockup's dark theme was illustrative only; use the app's existing tokens and light/dark support).
