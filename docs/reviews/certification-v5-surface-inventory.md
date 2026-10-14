# Certification course surfaces and the definition each reads

Inventory for C8-DEF-06, taken October 14, 2026 on `major/agentic-chat`. **(a)** means the learner's pinned
versioned package (`current_operation().package`, or `course?.modules` from the course definition endpoint).
**(b)** means the unversioned course: `certification_service` constants, which since `4f0981f8` come from the
preserved legacy rubric and `certification-data/panel-modules.json`; the drip list, which takes its titles from
them; and the frontend `modules.ts` fallback, which is pinned to the same panel data by a test.
**H** means hardcoded text.

| Surface | Where | Reads | Hardcoded course facts |
|---|---|---|---|
| Chat home call to action | `frontend/src/components/chat/HomeExperience.tsx`, `frontend/src/lib/certificationChat.ts` | a, then b | none since the module count falls back to the course list |
| `[ACTION:start-cert]` link | `backend/app/services/llm_service.py`, `frontend/src/components/chat/actionRoute.ts` | H | "Start the Certification Program" |
| `/certification` deep link | `frontend/src/router.tsx`, `CertificationPanelContext.tsx` | a | none |
| Activity rail badge | `frontend/src/components/workspace/ActivityRail.tsx` | b levels and H | "Vandal Workflow Architect", "Get Certified" |
| Learning panel | `frontend/src/components/certification/CertificationPanel.tsx` | a, then b | none |
| Chat lesson reader and module lessons | `ChatLessonReader.tsx`, `ChatModuleLessons.tsx` | a when enrolled, otherwise b | none |
| Chat certification cards | `frontend/src/components/chat/CertificationCards.tsx` | a (tool payload) | brand title as fallback heading |
| Chat tools | `backend/app/services/chat_tools.py` | a, otherwise b | none |
| Help prompt | `backend/app/services/llm_service.py` | H, version-neutral | now points to the panel entry points that exist |
| Celebration and certified banner | `CelebrationOverlay.tsx`, `CertifiedBanner.tsx` | a | brand and institution as fallback |
| Certificate PDF | `backend/app/services/certificate_pdf.py`, `backend/app/routers/certification.py` | a (credential snapshot), otherwise b | brand title; the unversioned module count now comes from the course |
| In-app notifications | `certification_service.py` (legacy), `certification_versions/completion_notices.py` | H / a | brand title in the legacy notice |
| Emails | `email_service.py`, `engagement_service.py`, `completion_notices.render_email` | H / b / a | drip titles from the course; descriptions are email copy |
| Administrator views | `backend/app/routers/admin.py`, `certification_versions/readers.py`, `support_snapshot.py`, `frontend/src/components/admin/Certifications*` | a, unversioned learners b | none |

`frontend/src/pages/Certification.tsx` is not routed or imported and is not a learner surface.

## Contradictions resolved

- Service fallback title "Governance" and drip titles "Foundations: Your First Extraction" and "Process Mapping"
  disagreed with the course; titles now come from the course data (`4f0981f8`).
- The help prompt sent learners to a Certification page reached from the teams dropdown, which no longer
  exists; it now names the chat action and the activity-rail button.
- The Workflow Design drip email described multi-step workflow building (the next module's topic); it now
  matches the module's subtitle.
- Two hardcoded module counts of eleven now derive from the course module list.

## Open, needing a product decision

- The unversioned course text promises "an official VWA credential"; the v5 contract promises a narrower
  supervision competence. Released legacy wording is preserved.
- The certificate, activity rail, legacy notification and completion email always say "Vandal Workflow
  Architect", whatever the course title of a v5 credential.
- Legacy tier themes in the frontend fallback differ from the v5 tiers (fallback only).
- The presentation deck describes the course as "from your first upload to building validated workflows".
- The preserved legacy rubric's unused title map still says "Governance"; it is byte-pinned to its release
  and is no longer read.
