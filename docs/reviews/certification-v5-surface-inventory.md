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

## Branding decision (October 14, 2026)

The legacy course keeps the "Vandal Workflow Architect" name; a v5 credential shows its own course title and
assessed outcomes (`28dce32a`). Applied:

- The certificate PDF for an outcome-based credential uses the course title as its headline and reads "has
  demonstrated the assessed outcomes of"; legacy certificates are unchanged.
- The activity rail shows the enrolled course title when the course has a credential scope.
- Versioned completion notices and email render from the issued record (`completion_notices`); the legacy
  notification, `certification_complete_email` and the drip copy are legacy-only and keep the brand.

Left as is by that decision: the unversioned course's "official VWA credential" wording, the legacy tier themes
in the frontend fallback, the presentation deck's description of the built-in course, and the byte-pinned legacy
rubric's unused title map.
