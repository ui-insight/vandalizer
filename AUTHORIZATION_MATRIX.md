# Authorization Matrix

This document defines the intended authorization model for Vandalizer and records the current audit status of the main resource surfaces.

As of `2026-03-19`, this matrix is the canonical reference for deployment-hardening work. It is not the same as "fully audited": some surfaces below are still marked as partial or open.

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
| Documents | owner; team member for team-shared docs | owner; team `owner` / `admin`; explicit admin-only routes may opt into platform-admin override | read includes download, status, chat/workflow selection | In progress |
| Folders | owner; team member for team folders | owner; team `owner` / `admin`; explicit admin-only routes may opt into platform-admin override | includes breadcrumbs, rename, move, delete | In progress |
| Workflows | owner; team member for team workflows | owner; team `owner` / `admin` | run is treated as a view-level capability; edit/delete is manage-level | In progress |
| Workflow results | anyone who can view the parent workflow | no direct mutation path; download and polling inherit workflow view access | `session_id` and `batch_id` must never bypass workflow authorization | In progress |
| Automations | owner; team member when `shared_with_team=true` and team matches | owner; team `owner` / `admin` for shared automations | triggering is allowed only if the caller can view the automation and the linked action is also authorized | In progress |
| Knowledge bases | owner; team member when shared; any authenticated user for verified KBs subject to org visibility | owner; team `owner` / `admin` for shared KBs; explicit admin routes may opt into platform-admin override | source ingestion must also authorize the referenced documents | In progress |
| Search sets | owner; global viewers; users who can reach the set through an authorized team or verified library item | owner; team `owner` / `admin` when the set is managed through a team library item | search sets still do not store first-class team scope, so shared access is currently derived from library containment | In progress |
| Library libraries / folders / items | personal library owner; team members for team library; all users for verified library items subject to org filters | personal owner; team `owner` / `admin`; verified library is admin-managed | helper-based authorization now exists for library, folder, and item paths, but broader regression and adversarial coverage still need expansion | In progress |
| Spaces (legacy) | owning user only | owning user only | legacy compatibility surface; should not remain a tenant boundary or shared-workspace mechanism long-term | In progress |
| Office intakes / work items | owning user only | owning user only | manual triage/process must prove both intake ownership and work-item ownership/intake linkage; intake workflow binding must point at a workflow the owner can access | In progress |
| Verification requests / collections / catalog ops | submitter for their own requests; admin / examiner for queue, collections, and catalog import/export; any authenticated user for verified-item trial runs only when the item and selected inputs are visible | admin / examiner for review status changes, collections, and catalog import/export; submitter may only create requests for items they can already view | reviewer and catalog routes must not rely on frontend gating, and trial runs must re-authorize selected documents plus org-scoped verified items | In progress |
| Approvals | assigned reviewer; workflow owner; team `owner` / `admin` for the parent workflow; platform admin | same as viewer for approve / reject decisions | unassigned approvals must not become globally reviewable; access is derived from explicit assignment or manage access to the parent workflow | In progress |
| Chat conversations and attachments | owning user | owning user | document, folder, and KB selections inside chat must be authorized independently | In progress |
| Admin / system config | platform admin; some views also allow team admins with scoped filters | platform admin unless route explicitly supports scoped team-admin mutation | automation stats are now scoped to caller-visible workflows, and team-admin drill-down views now scope document counts to team-visible docs and redact platform-role flags; broader admin/analytics review is still open | Partial |

## Route-Level Expectations

These expectations apply across routers and services:

- Any endpoint that accepts `uuid`, `doc_uuid`, `folder_uuid`, `workflow_id`, `automation_id`, `search_set_uuid`, `knowledge_base_uuid`, `session_id`, or `batch_id` must resolve the target through a shared authorization helper or an equivalent parent-resource check.
- Background or indirect execution paths must re-check authorization instead of assuming the caller already did so.
- Selection inputs inside larger actions are still object access:
  - chat document selections
  - workflow run document selections
  - knowledge-base document ingestion
  - automation linked actions

## Current Audit Coverage

Covered or materially improved:

- documents, folders, and file-browser paths
- workflow CRUD plus workflow result polling/download
- workflow run/test document selection checks
- automation CRUD and API-trigger action checks
- knowledge-base view/manage access and document-ingestion checks
- chat document/folder/knowledge-base selection checks
- search-set CRUD, validation, and document-selection checks
- library, library folder, and library item helper-based authorization
- verified and team-library backed access for workflows and search sets
- verification queue, request visibility, collection mutation, catalog import/export, and trial-run document authorization
- approval visibility and decision authorization derived from explicit assignment or manage access to the parent workflow
- legacy spaces list/update/delete scoping to the owning user
- office intake and work-item route scoping, including intake-bound manual actions and authorized workflow binding
- automation stats scoping for caller-visible workflows
- team-admin analytics drill-down scoping for document counts and platform-role flag redaction

Still open or only partially covered:

- broader admin and analytics summary surfaces beyond the automation dashboard and updated team-admin drill-down routes
- remaining legacy `space`-based flows, especially automation/workflow metadata and stale product copy
- manual adversarial cross-user / cross-team testing across all audited routes

## Implementation Guidance

- Prefer shared authorization helpers in [access_control.py](backend/app/services/access_control.py).
- When a resource is nested under another resource, authorize the parent first and derive access from that parent.
- Do not trust caller-supplied team IDs, spaces, session IDs, batch IDs, or object UUIDs without verifying ownership or team membership.
- When adding a new shared/team feature, define:
  - who can view it
  - who can execute it
  - who can mutate it
  - whether organization visibility further limits it
