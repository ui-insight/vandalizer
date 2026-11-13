# Project workspace design note

Design for review; implementation in this PR is slice 1 only. Verified against
`origin/major/agentic-chat` at `58486cfa` and the plan on
`docs/project-workspace-plan` at `6fcfced1`. Use existing workspace tokens,
components, and light/dark behavior throughout.

## Header and widths

At desktop widths (>=1100px), use the plan's three rows: breadcrumb/title,
status, members, Share and Add file; a cited snapshot summary; then snapshot,
Calendar, Reminders and More actions. Wrap long titles and action groups without
page overflow. The right Assistant | Library column keeps its controls and its
existing `tab` URL parameter.

Below 1100px the activity rail auto-docks as today. Keep the same header content,
allowing buttons and summary to wrap; do not infer a different workspace mode
from the rail's highlight. At compact widths (<768px), retain breadcrumb,
status, Share, Add file (where authorized), and More. Truncate the summary to a
line with an accessible Details disclosure. Move snapshot, Calendar and
Reminders actions into More. Sheets fill the available width, have a labelled
title, trap focus, close with Escape, and restore focus to their trigger.

## More and section destinations

- Edit project: small dialog for title, description and status, reusing the
  existing update behavior and error messages.
- Project brief: separate sheet for chat context, read-only for viewers.
- Pinned tools: sheet reusing ProjectPinsSection and ProjectSkillsSection,
  preserving project selection when opening a tool and default Skill behavior.
- Share snapshot as Page: existing snapshot action; retain its availability and
  disabled/pending states rather than creating a second implementation.
- Duplicate project: existing duplication action and destination behavior.
- Leave project: existing confirmation, shown only with `can_leave`.
- Back to projects: the existing exit behavior followed by the Projects list.
- Compact only: Build/Rebuild snapshot, Calendar and Reminders as above.

The breadcrumb is the primary exit and More contains its secondary location.
This resolves the plan's contradictory “exactly one way out” wording as one exit
behavior in two specified navigation locations. The chat scope chip has no exit.

Manage → Overview moves into Edit and Brief; preserve the resource summary on
Overview. Manage → Pages becomes Pages. Manage → Tools becomes Pinned tools.
Manage → Sharing becomes the header Share sheet, reusing its members, roles,
invites, team sharing, make-personal and leave logic. Keep the modal as a shared
container while extracting these sections; remove its old navigation once all
entry points are migrated. Do not copy the sharing implementation.

## Tab states and roles

Each future tab uses a labelled panel with skeleton loading, a scoped empty
message, an error with Retry, and a no-access message on access loss (handle both 403 and the project API’s
access-obscuring 404). Do not
render cached private content after an authorization failure. Partial Overview
failures retain successful sections and offer section-specific retries.

| Tab | Loading | Empty | Error | No access |
| --- | --- | --- | --- | --- |
| Overview | Section skeletons | Explain which facts, files, Pages and saved inbox items were checked; offer authorized next steps | Retry failed sections; snapshot building polls as today | Project unavailable; return to Projects |
| Inbox | Row skeletons | No saved deadlines/materials; managers can Add deadline, viewers can ask chat | Retry without claiming nothing is due | No project items or actions; return to Projects |
| Files | Existing browser loading | Project folder has no files; authorized upload action | Existing browser retry | No browser, upload or document content |
| Pages | Existing PagesBrowser loading | No Pages shared with this project; authorized create/share actions | PagesBrowser retry | No Pages content or mutation actions |
| Activity | Run-row skeletons | No workflow or extraction runs recorded for this project | Retry and preserve pagination position | No events or run links |

Viewers retain today's available content, sources, personal Dismiss, Calendar
and Reminders. No new Files/tool entry points or mutations become available to
them merely because there are tabs. Show no Add file, Build, Add deadline, shared
Done/Keep, edit or pin controls. The plan proposes member inspection in Share, but today the modal hides the
member list from viewers (the API permits reading it). To honor the instruction
that viewers see nothing more, retain their current access summary without a
new member list unless explicitly approved. Validate actual
API capabilities before exposing any additional viewer content in later slices.

The tabs will use `ptab`, leaving `tab` untouched. Invalid `ptab` falls back to
Overview; a project `deadline` link selects Inbox and retains row focus and the
“no longer open here” message. Preserve inbox refresh-on-focus/60s polling and
snapshot-building polling. Use arrow-key tab navigation, a keyboard More menu,
and visible focus.

## Verification findings and slice 1

The six problem statements match the base. The snapshot has `out_of_date` as
a boolean, not a status value; preserve that model. Rail selection actually lives in
UtilityBar; WorkspaceLayout's `isChat` is a layout flag and must retain its
behavior. The sr-only heading should use the active project title.
ProjectWorkOverview has no production imports: remove it and its specific test
cases/styles; pins remain available in Manage → Tools.

The plan's proposed interim left-panel inbox would be hidden in the default
project view and inaccessible to viewers whose navigation is chat-only. Slice 1
instead mounts the existing RAInbox in a bounded, independently scrolling region
above the conversation, outside the empty state. It remains mounted after a
message, without opening or closing any columns. Slice 3 moves that same
component into Inbox. Home keeps its current empty-state inbox.

PR #1145 was inspected: it adds AddDeadlineForm and the project-only Add deadline
button within RAInbox. Leave that structure in place when merged; no form is
copied or added here. The current inbox exposes Done/Keep to viewers even though
the API requires manage access. Hide those controls within the scoped project
inbox; personal Dismiss and citations remain. #1145 will also need its Add deadline
button gated on edit permission when integrated.

## Product proposals — awaiting confirmation

1. Default to Overview, with an open, undismissed Inbox count and a direct inbox
   link. Deadline reminders override this to Inbox.
2. Keep Add file in the header for owners/editors, using the existing upload
   flow rooted in the project folder.
3. Defer Found but not added to its separate slice/ticket; rejected proposals
   are not persisted today.
4. Keep Templates global, linked from Pages without implying project scoping.
5. Keep a horizontally scrolling tab row on compact screens, with visible
   focus and the selected tab scrolled into view; the page itself must not
   scroll horizontally. This preserves tab semantics and discoverability.

## Slice 1 verification

- `make backend-static`: passed, including typing (556 files), lint, security
  and endpoint-map validation. No routes or frontend API calls changed.
- `cd backend && uv run pytest`: 9,660 passed, 2,152 skipped, 1,722 warnings.
  External-service integration tests retain their existing opt-in requirements.
- Node 24.22.2: `npx tsc -b` passed; `npx eslint src` passed with 12 existing
  warnings and no errors.
- Six focused slice-1 test files: 79 passed, including sending a project chat
  message without unmounting the inbox, role restrictions, source links,
  highlighting and preservation of desktop/compact column behavior.
- The unmodified full `npx vitest run` invocation completed with 3,040 passed
  and six failed (395 files). Five failures were five-second timeouts in
  Artifacts.versionLinks, ConfigTab, UsersTab, ConnectedWorkflow and
  OutputWorkflow. PagesBrowser.actions found two status messages during a
  refresh. None of those files were changed here. The base commit reproduced
  the PagesBrowser failure in an unconstrained three-file run (50 passed,
  one failed); all six affected files passed on the base with two workers
  (100 passed). These results show concurrency-sensitive failures, not a
  green default frontend gate.
- Screenshots use the real app with synthetic project/inbox API responses,
  without a live database or LLM. Chromium review at 1440×1000 and 390×844;
  compact document scroll width equals viewport width (390px). The bounded
  inbox scrolls independently to reach all row controls on a phone.
  [Desktop](screenshots/project-workspace-slice-1-desktop.png) ·
  [Compact](screenshots/project-workspace-slice-1-compact.png).
- PR #1145's diff was reviewed, but its unmerged Add deadline form was not
  executed. No live uploads, calendar download contents, sharing mutations,
  external reminders or LLM response were exercised in browser review.
  Their existing tests/implementations remain; header/tab migrations and
  `ptab` acceptance tests belong to later slices.
