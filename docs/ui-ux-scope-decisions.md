# Vandalizer UI/UX scope decisions

Tracking issue: [GitHub issue #964](https://github.com/ui-insight/vandalizer/issues/964).

The user has approved **all A1–A14** in addition to the clarity, polish and existing-behavior repairs. Their instruction was: “Okay I actually think we should do all this.” The consolidated GitHub issue is the implementation tracking unit; no child issues are required.

## Approved additions

| ID | Approved addition | Scope | Status | Checklist references |
|---|---|---|---|---|
| A1 | Project search and sorting | New controls for finding/reordering the Projects list. The current list does not expose these. | Approved | PROJ-03 |
| A2 | Last-run outcome in automation list | New summary information on list cards, potentially requiring a data lookup; existing scheduled next-run text already exists and only needs presentation review. No new monitoring backend is proposed. | Approved | AUTO-03, AUTO-09 |
| A3 | Per-file upload retry | A new retry action for a failed upload, distinct from the existing chat-response retry. | Approved | UP-05 |
| A4 | Cancel an active upload | A new action that actually aborts an in-flight upload. Removing an existing attached file and cancelling an already-supported queued message are separate existing behaviors. | Approved | UP-06 |
| A5 | Open created artifact from agent completion | A new shortcut such as Open workflow on creation results. Existing source inspection, workflow progress/output and verification links are already present. | Approved | AGT-06 |
| A6 | Unsaved-draft discard confirmation | A new Keep editing / Discard prompt when closing a partially completed automation wizard. | Approved | WIZ-09 |
| A7 | Shorter validation wizard | Merge/reorder existing screens and put advanced settings behind an optional control. Computation stays the same, but the user's sequence changes. | Approved | VAL-04 |
| A8 | Separate primary Sources / Validation views | Introduce new primary tabs or navigation in KB detail instead of the existing stacked sections. | Approved | KB-06, VAL-02 |
| A9 | Guided first-task onboarding | A prescribed upload → question → inspect-evidence sequence beyond the existing upload/demo actions. | Approved | ONB-03 |
| A10 | Dedicated assistant launcher | A new launcher/control for opening contextual chat. Resizing existing panels, simplifying welcome content and using current navigation/collapse controls do not require this addition. | Approved | SYS-02 |
| A11 | Separate Save disabled / Create & enable buttons | Replace the current Enable immediately checkbox plus Create Automation button with two final actions. Creating enabled/disabled automations is already supported; the controls would change. | Approved | WIZ-08 |
| A12 | Read-only automation configuration recap | Show the selected trigger, folder/filters, action, output and activation together on the existing final wizard screen. No extra step, setting or execution behavior. | Approved | WIZ-07 |
| A13 | Source-health summary beside attached KB | Display existing ready/failed-source information beside the KB in chat. No refresh/retry control or new source-health service. | Approved | CKB-02 |
| A14 | Structured agent approval summary | Format the existing proposed action, target and supplied arguments as a readable summary before the existing confirmation. No new approval gate or tool behavior. | Approved | AGT-02 |

A12–A14 expose existing information. A1–A11 include new controls, information or workflow changes. Approval applies to the bounded additions above and the 169-item checklist; it does not authorize unrelated product expansion.

## Implementation boundaries

- Preserve existing operations and user data; add only the approved capabilities and supporting changes needed to make them work.
- Scheduled next-run information, selected-file count/clear actions, upload-processing feedback, source inspection and several tool result actions already exist. Improve or reuse them rather than duplicate them.
- Additional operational information must come from real state. Do not fabricate outcomes, progress, cost, timing or quality scores.
- Upload cancellation must describe its actual effect. Aborting a transfer does not imply that an already accepted server-side processing task was cancelled or rolled back.
- Combine A11 and A12 on the existing final automation screen: a configuration recap plus explicit Save disabled and Create & enable actions, without adding an unnecessary extra step.
- Test existing flows; a verification task is not blanket authorization to build other missing features.
- No unrelated backend rewrite, permission redesign, new integrations, model tuning or production deployment is included.
- Keep the issue self-contained. Local, uncommitted review files are not publicly accessible evidence links.
