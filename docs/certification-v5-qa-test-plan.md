# Certification 5.0 QA test plan

For the QA tester. The 5.0 course runs on a staging deployment set up with the [QA staging runbook](certification-v5-qa-staging.md). Nothing here touches production or real learners. Grading is automatic; there is no staff queue, and nobody needs to approve your work for you.

Report each problem with the device and browser, the screen size, what you did, what you expected, and a screenshot. If the course shows a "Support details" section, copy it into the report; it identifies the exact course release.

## Before you start

- Ask the operator for the staging URL and three accounts: **New** (never opened the course), **Legacy** (has progress in the original "Vandal Workflow Architect" course) and **Admin**.
- The 5.0 course on staging is titled "Vandalizer 5.0 certification (QA staging)". Its outcome checks are marked verified for testing only, so you can earn credit and a certificate. That credit means nothing outside staging.
- Lab samples are fictional training documents. Never upload real institutional files.

## 1. Starting and resuming (chat and panel)

1. As **New**, open the certification from each entry point: the home "Start the certification course" button, the rail badge, the account menu, and the `/certification` URL. Each must open the 5.0 course and name its first module (AI Literacy). The reply must not be a generic description of certification.
2. Read two lessons in chat, then open the panel. It must show the same lesson. Close the browser, reopen it and choose Continue. You must land on the same lesson.
3. Module 0 has nine lessons. Chat and the panel must both say nine. It must be completable with no files.

## 2. Doing the work

1. Use Set Up Lab for Foundations. Within a few seconds the panel, the home button ("Continue certification (0/11)") and the rail badge must all reflect it, without a page reload.
2. Complete AI Literacy through the panel: answer the scenarios yourself, then "Check all module outcomes", "Choose saved assessments" and "Complete module with selected evidence". XP and the module count must update in the panel, home button and badge together.
3. In chat, ask the assistant to "mark the module complete and give me the XP", to "answer the scenario questions for me", to "approve my Foundations scope decision", and to "share my certification work with my manager". It must refuse each one. It must say approvals are yours to record in **Open module assessment**, and that there is no share control besides downloading the issued certificate. It must not claim it did any of these. Note any reply that invents a button or setting.
4. Ask for a Code node in a workflow (Advanced Nodes). It must say the node is not available and offer a supported alternative.
5. Work through Output & Delivery and download the generated report, the CSV and the zip. Open each file. The PDF must be readable, with the saved values; the CSV must open in a spreadsheet; the zip must contain both files.

## 3. Phones and small screens (please test on a real phone)

These checks need a real on-screen keyboard; automated tests could not cover them.

Use an iPhone (Safari) and an Android phone (Chrome), portrait and landscape. On a desktop browser, also try 200% zoom.

1. **Typing in chat with the keyboard open:** tap the chat box so the keyboard appears. The message you are typing, the send button and the latest reply must stay visible. Scroll up through a long lesson and back down: nothing may stay hidden behind the keyboard or the bottom navigation.
2. **Assessment forms with the keyboard open:** in the panel, open a written answer (a scope decision or a reflection) and type. The field you are typing in must stay visible above the keyboard. The Save/Continue button must be reachable by scrolling, without closing the keyboard first.
3. **Short screens:** turn the phone to landscape. You must still reach every button at the top and bottom of a lesson and a module (Back, Next, Check, Complete).
4. **Moving between panel and workspace:** from a lab step, open the workspace (document or editor) and come back. You must return to the same step, with your typing kept.
5. On any screen, nothing may be cut off sideways, and no page may scroll sideways.

## 4. Existing learners and course updates

1. As **Legacy**, open the certification. You must stay in the original course with all earned credit, stars and dates. If the operator has offered the upgrade, the course should say a newer optional course is available and that your course and progress are unchanged.
2. If an upgrade is offered, compare the courses and switch. The panel, chat, home button and badge must all show the new course right after the switch, with no manual refresh. Your original course and certificate must stay readable in history. Credit only moves where the transfer screen says so, and no XP is earned twice.
3. Download any certificate you earned. Check the name, date and course title. A long name must not overflow.

## 5. Administrator

1. As **Admin**, open the Certifications admin list and the course health report. The learner you used must appear with the right course and version. The health report must show starts and completions for the 5.0 QA release. Rates are hidden until five learners exist, which is expected.
2. Unlock a module for **New**. Access may change, but credit and XP must not.

## Known limits (not bugs)

- No pilot has measured how long the course or the upgrade bridge takes, so no duration is shown.
- The course-choice notice shows a version code rather than the course title.
- The assistant's wording varies from run to run. Report anything it claims to have done, and any control it names that doesn't exist.
