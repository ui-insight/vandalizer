# Authorization Matrix

This document defines the intended authorization model for Vandalizer and records the current audit status of the main resource surfaces.

As of `2026-03-20`, this matrix has been systematically audited across all 28 router files and their service-layer delegates.

## Core Rules

- Personal resources:
  - visible only to the owning user
  - mutable only by the owning user
- Team-scoped resources:
  - visible to team members
  - mutable by the resource owner and team `owner` / `admin`
- Verified or global resources:
  - viewable to all authenticated users unless further limited by organization visibility
  - mutable only by the owner or explicitly privileged operators
- Platform admin:
  - does not automatically bypass all content-bearing resources unless the specific route/helper opts into `allow_admin=True`
- Organization-scoped visibility:
  - when a resource declares `organization_ids`, non-owners must belong to one of those orgs to view or manage it

## Team Scope Normalization

The codebase currently has mixed team identifier formats:

- some resources store team UUIDs
- some resources store Mongo ObjectId strings

The shared helper layer in [access_control.py](backend/app/services/access_control.py) now treats both as valid team scope identifiers for membership and role checks. New code should continue to use the shared helpers instead of hand-rolling team checks.

## Matrix

| Resource | Viewer | Manager / Mutator | Notes | Audit status |
| --- | --- | --- | --- | --- |
| Documents | owner; team member for team-shared docs | owner; team `owner` / `admin`; explicit admin-only routes may opt into platform-admin override | read includes download, status, chat/workflow selection. Retention-hold endpoints check `is_admin`. Classify endpoint uses `manage=True`. | Audited |
| Folders | owner; team member for team folders | owner; team `owner` / `admin`; explicit admin-only routes may opt into platform-admin override | All ops delegate to `folder_service` which calls `get_authorized_folder`. List returns own + team folders via `get_team_access_context`. | Audited |
| Files | via `get_authorized_document` in file_service | owner; team `owner` / `admin` | File upload, download, and deletion all resolve through document authorization. | Audited |
| Workflows | owner; team member for team workflows | owner; team `owner` / `admin` | All CRUD and execution delegated through `get_authorized_workflow`. Document selections pass through `_authorize_documents`. Steps/tasks resolve parent workflow for authz. | Audited |
| Workflow results | anyone who can view the parent workflow | no direct mutation path; download and polling inherit workflow view access | `session_id` and `batch_id` resolve through `_get_authorized_workflow_result` which checks `can_view_workflow` on the parent. SSE streaming re-checks on every poll. | Audited |
| Automations | owner; team member when `shared_with_team=true` and team matches | owner; team `owner` / `admin` for shared automations | All CRUD via `get_authorized_automation`. Trigger endpoint checks automation visibility, action target, and document authz. | Audited |
| Knowledge bases | owner; team member when shared; any authenticated user for verified KBs subject to org visibility | owner; team `owner` / `admin` for shared KBs; explicit admin routes may opt into platform-admin override | All endpoints via `get_authorized_knowledge_base` with org ancestry checks. Source ingestion authorizes documents. | Audited |
| Search sets | owner; global viewers; users who can reach the set through an authorized team or verified library item | owner; team `owner` / `admin` when the set is managed through a team library item | All endpoints use `_get_search_set_or_404` → `get_authorized_search_set`. Document selections authorized. Test cases check parent manage access. | Audited |
| Library libraries / folders / items | personal library owner; team members for team library; all users for verified library items subject to org filters | personal owner; team `owner` / `admin`; verified library is admin-managed | All ops via `get_authorized_library`, `get_authorized_library_folder`, `get_authorized_library_item`. | Audited |
| Spaces (legacy) | owning user only | owning user only | `space_service` filters by `Space.user == user.user_id`. Legacy compatibility surface. | Audited |
| Office intakes / work items | owning user only | owning user only | `_get_owned_intake` and `_get_owned_work_item` filter by `owner_user_id`. Workflow binding checked via `get_authorized_workflow`. | Audited |
| Verification requests / collections / catalog ops | submitter for their own requests; admin / examiner for queue, collections, and catalog import/export; any authenticated user for verified-item trial runs only when the item and selected inputs are visible | admin / examiner for review status changes, collections, and catalog import/export; submitter may only create requests for items they can already view | Submission target authorized. Queue/collections require examiner access. Trial runs re-authorize documents and org-scoped items. | Audited |
| Approvals | assigned reviewer; workflow owner; team `owner` / `admin` for the parent workflow; platform admin | same as viewer for approve / reject decisions | `_can_access_approval` checks assignment, then workflow manage access. Approve/reject re-check. | Audited |
| Chat conversations and attachments | owning user | owning user | Conversations filtered by `user_id`. Document/folder/KB selections authorized. Attachments filtered by `user_id`. | Audited |
| Admin / system config | platform admin; some views also allow team admins with scoped filters | platform admin unless route explicitly supports scoped team-admin mutation | All config routes use `_require_admin`. Analytics use `_require_admin_or_team_admin` with scoping. Quality routes require `_require_admin`. | Audited |
| Activity events | owning user | no direct mutation | All filtered by `user_id`. | Audited |
| Teams | team members for list/invite views | owner / admin for mutations | Membership checks on list/invite views; owner/admin checks on mutations. | Audited |
| Feedback | write-only | owning user | `user_id` from session. | Audited |
| Certification | owning user | owning user | Scoped to caller's `user_id`. | Audited |
| Organizations | admin for CRUD; user limited to own org | admin only | Admin checks on all CRUD; user limited to own org. | Audited |
| Browser automation | session owner | session owner | Session ownership checks; WebSocket JWT auth. | Audited |
| Config (user) | owning user | owning user | User config scoped to caller; automation stats scoped to visible workflows. | Audited |
| Audit log | platform admin | no mutation | Admin only. | Audited |
| Demo | public for apply/status | admin for management | Public apply/status; admin for management endpoints. | Audited |
| Graph webhooks | system-to-system | system-to-system | `clientState` validation. No user context. | Audited |

## Known Gaps

| ID | Severity | Description | Mitigation |
| --- | --- | --- | --- |
| GAP-1 | Low | `GET /documents/search` only returns user-owned docs, not team-shared docs. Over-restrictive, not a security issue. | Functional limitation only. |
| GAP-2 | Low | Verification test-file upload (`POST /upload-test-file`) has no per-user scoping. | Download requires examiner access, not exploitable by regular users. |
| GAP-3 | Low | Approval list post-filters all approvals through `_can_access_approval`, which issues a DB query per approval. | Correct but potentially slow at scale. Consider pre-filtering. |
| GAP-4 | Low | `POST /workflows/run-integrated` does not call `get_authorized_workflow` at the router level. | Authorization is still enforced by `svc.run_workflow` internally. Defense-in-depth fix recommended. |
| GAP-5 | Medium | `GET /workflows/steps/test/{task_id}` does not verify that the Celery task belongs to the calling user. | Task IDs are UUIDs (hard to guess), but no ownership check exists. A mapping from task_id to user_id would close this gap. |

## Route-Level Expectations

These expectations apply across routers and services:

- Any endpoint that accepts `uuid`, `doc_uuid`, `folder_uuid`, `workflow_id`, `automation_id`, `search_set_uuid`, `knowledge_base_uuid`, `session_id`, or `batch_id` must resolve the target through a shared authorization helper or an equivalent parent-resource check.
- Background or indirect execution paths must re-check authorization instead of assuming the caller already did so.
- Selection inputs inside larger actions are still object access:
  - chat document selections
  - workflow run document selections
  - knowledge-base document ingestion
  - automation linked actions

## Remaining Open Items

- Manual adversarial cross-user / cross-team testing across all audited routes
- Defense-in-depth fixes for GAP-4 and GAP-5
- Load testing for post-filter authorization patterns (GAP-3)

## Implementation Guidance

- Prefer shared authorization helpers in [access_control.py](backend/app/services/access_control.py).
- When a resource is nested under another resource, authorize the parent first and derive access from that parent.
- Do not trust caller-supplied team IDs, spaces, session IDs, batch IDs, or object UUIDs without verifying ownership or team membership.
- When adding a new shared/team feature, define:
  - who can view it
  - who can execute it
  - who can mutate it
  - whether organization visibility further limits it
