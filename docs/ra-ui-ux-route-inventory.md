# RA review route and role inventory

September 30, 2026. Source: `frontend/src/router.tsx`, page-level access checks, Admin tab definitions and workspace panels. This is a coverage inventory, not a declaration that every state passed. Evidence and remaining gates live in [the checklist](ra-ui-ux-upgrade-checklist.md) and [progress log](ra-ui-ux-implementation-progress.md).

All active user-facing surfaces target keyboard access and 320/390/768/1024/1440px layouts, including short screens. Wide document/data regions may scroll within a named, focusable container. Actual enlargement and assistive-technology checks remain separate gates. Role visibility in the UI is not backend authorization evidence.

## Routes and representative tasks

| Route | Intended access | Representative task / coverage |
| --- | --- | --- |
| `/landing`, `/login`, `/register` | Public | Understand an RA example; sign in/register; retain invite/return/error state. Login/register are entry aliases. |
| `/reset-password` | Public token holder | Recover access; invalid/expired token; failed request/retry. |
| `/invite` | Invited team member | Accept a direct team invitation; expired/revoked/already-used outcomes. |
| `/join` | Team join-link holder | Join the named team; invalid link and signed-out return. |
| `/join-project` | Project invite-link holder | Accept PI/viewer access; understand chat/read scope; expiry/removal. |
| `/` | Signed-in user; project viewers receive restricted scope | Chat, Files, Projects, Automations, Knowledge; composable Assistant/Library/tool panes. See workspace matrix below. |
| `/workflows/$id` | Signed-in user with item access | Legacy editor entry into an accessible workflow; missing/denied/shared item. |
| `/teams` | Signed-in user; management depends on team role | Switch teams, inspect members, invite, change roles, ownership/leave/delete. |
| `/account` | Signed-in user | Profile, account role, memory/preferences, SSO-managed fields and failed saves. |
| `/credentials` | Signed-in user with credential access; maintainer for changes | Name/configure/test a connection; retain secret; read-only view and dependent workflow failure. |
| `/reviews`, `/reviews/$uuid` | Assigned reviewer/requester/authorized team or system role, enforced by API | Find a pending decision; inspect original sources/output; edit/comment; approve/reject/expiry. |
| `/tuning` | Signed-in user with item access; item manager for application | Compare measured gains/regressions; apply/dismiss/restore/open; failed/running/no-change/live states. |
| `/verification` | Examiner; Examiners management additionally requires admin | Requests, Catalog, Coverage, Collections; populated decisions, claim/release and author feedback. |
| `/support` | Support agent | Triage, filters, assignment, internal/user-visible conversation, attachments/watchers, What's Working. Other users get a staff-access explanation and ordinary Support path. |
| `/admin` | Team owner/admin, staff or global admin, per-tab restrictions | Investigate adoption/failure and administer authorized resources. See tab matrix below. |
| `/organizations` | Signed-in user; management depends on page/API permissions | Locate organization hierarchy and understand membership/access. |
| `/automation` | Signed-in user | Legacy automation entry; inspect redirect/retained behavior before grading independently. |
| `/certification` | Signed-in user | Opens the learning panel in the workspace; task walkthrough/course/assessment and saved progress. |
| `/docs` | Public | RA quickstart, task help, technical docs, mobile navigation and return to app. |
| `/docs/present`, `/docs/present/$audience` | Public | Select audience, navigate deck, resume slide and written/spoken pitch. |
| `/demo`, `/demo/status/$uuid` | Public, trial capability dependent | Trial request and status; enabled/disabled and request failure. |
| `/demo/feedback`, `/demo/trial-end` | Public token holder, trial capability dependent | Feedback/trial completion; invalid/expired token; non-delivering submission QA. |
| `/demo/resend/$uuid` | Public trial record holder, capability dependent | Resend entry recovery without delivering messages to real users. |

## Workspace and shared surfaces

| Surface / major tabs | Roles and representative task |
| --- | --- |
| Chat: first session / returning home / conversation | Ordinary RA; restricted project viewer. Upload/sample → question → evidence → export/reuse; interrupted response/retry; optional tour. |
| Scope controls: documents / folders / KBs / project | Ordinary RA within authorized resources; outgoing IDs must agree with visible scope. Switching must not retain unnoticed sources. |
| Agent action preview / historical result | Authorized tool user. Approval/cancellation/pending/failure/completion must be distinct; one action, one effect. |
| Files / document viewer / processing recovery | Authorized document reader. PDF, scanned PDF, DOCX and supported sheets; original/extracted text, source highlights and missing content. |
| Projects / overview / Manage / pins | Owner/editor manage supported content; PI/viewer reads/chats within API limits. Switch context without losing drafts; invitations and removed membership. |
| Library: Mine / Team / Explore / folders / types | Ordinary RA, ownership and item capability dependent. Discover task; inspect/copy/save/edit; dense results and recoverable failures. |
| Workflow: Design / Input / Validate / Advanced / History | Reader/run user or manager according to API flags. Step/task hierarchy, fixed/selected/project inputs, approvals, output and recovery. |
| Extraction: fields / Results / Validate / History | Item reader/run user or manager. Multi-document value/evidence comparison, missing support, copy/export and retry. |
| Automation: overview / setup / run / history / outputs | Item user or manager. Trigger/input/action/destination recap; disabled versus enabled save; queued versus completed result. |
| Knowledge: Mine / Team / Explore; Sources / Validation | Reader/chat user or manager. Intake, partial/failed health, search/attention filters and source inspection. |
| KB Validation: questions / check / history / advanced retrieval | Manager or authorized evaluator. Representative references, actual test scope, results/evidence, optional tuning and apply/revert. |
| Learning: floating / left / right / bottom / fullscreen | Signed-in learner. Practical task first; optional course; lesson, assessment, unlock, interruption/resumption. |
| Notifications bell / notification settings | Signed-in user within notification scope. Unread/read, deep link to intended item, deleted/unavailable target, return. |
| Support widget | Signed-in user; staff gets appropriate ticket visibility | Describe problem, retain draft/files, failed submission/retry, reopen and reply. |
| Account menu / team switch / session expiration | Signed-in user; SSO/password constraints | Reach relevant role tools, switch correct team, preserve intended return after expiration. |

## Admin and examiner tabs

| Tab(s) | Minimum UI role / condition | Representative task |
| --- | --- | --- |
| Usage, Users, Workflows | Team owner/admin | Understand actual counts, filters/export, drilldowns and denied/error states. |
| Teams, Organizations, Knowledge Bases, Certifications | Staff | People/content overview, populated records, detail/edit and recovery. KB editing additionally requires global admin in this UI. |
| Quality, Optimizer, Compliance, Audit Log | Staff | Understand evidence/event limits; locate affected item; safe read/change recovery. |
| API Keys | Staff | Controlled key lifecycle; no production secret exposure. |
| Catalog, Config | Global admin | Controlled distribution and configuration review; authentication/model presentation; no production changes. |
| Demo | Staff plus `trial_system_enabled` | Trial operations in non-delivering fixtures. Hidden when feature disabled. |
| Email | Staff | Email analytics and failures using synthetic/non-delivering data. |
| Telemetry | Staff plus `telemetry_collector_enabled` | Fleet collector view. Hidden on other installations. |
| My sharing requests (`/verification` for non-examiners) | Signed-in author | Own submissions only; examiner feedback, reopen and resubmit guidance. |
| Shared items: Requests, Catalog, Coverage, Collections | Examiner | Sharing suitability, measured quality and baseline eligibility remain separate. |
| Shared items: Examiners | Examiner plus global admin | Controlled examiner management and rejected access. |

## Retired routes and conditional functionality

`/workflows` and `/chat` redirect into the workspace; `/library` redirects to its Library pane. `/audit` redirects to Admin. `/approvals` redirects to Reviews. `/office` and `/browser-automation` are retired shadow-route redirects, not active product surfaces. Their old features must not be counted as reviewed functionality.

Microsoft 365 controls depend on `m365_enabled`; unavailable/disabled integration paths require explicit distinction from an empty connected account. Trial and telemetry paths are conditional as listed above. An absent tab does not prove its enabled state works.

## Evidence boundaries

- Route inventory and role mapping are complete from source inspection. All routes/tabs above are now named in the review scope.
- Populated browser fixtures establish UI behavior only; independent account/API checks are required for enforcement, persistence and actual delivery/execution.
- User observation, screen-reader testing, actual 200% browser zoom, and final per-surface regrading remain open. The baseline scores are unchanged.
