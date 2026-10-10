
// ---------------------------------------------------------------------------
// Module definitions
//
// Lesson content here is also served to the in-chat certification flow via
// backend/certification-data/lessons.json. After editing lessons, rerun
// `node scripts/export-lessons.mjs` (the array must stay pure literals).
// ---------------------------------------------------------------------------

import type { ModuleDefinition } from '../../types/certification'

export const MODULES: ModuleDefinition[] = [
  {
    id: 'ai_literacy',
    number: 0,
    title: 'AI Literacy',
    subtitle: 'Understanding AI for Research Administration',
    description: "Welcome to the Vandal Workflow Architect certification. By the end of this program, you'll earn an official VWA credential recognizing your ability to design, validate, and deploy AI-powered workflows for research administration. This first module starts with the big picture — what AI is, why it has landed in research administration, and how this course helps you — before touching any tool. The course is self-paced, uses training examples and saves your reading place. Reading time and practical work vary; there is no measured fixed completion time.",
    objectives: [
      'See the big picture: what AI is, why it matters for research administration, and how this course helps',
      'Tell structured from unstructured data \u2014 the one distinction this whole course is built on',
      'Learn the key terms you\'ll encounter throughout this certification',
      'Reflect on your own experience and comfort level with AI tools',
    ],
    tips: [
      'There are no wrong answers on the self-assessment; it\'s for your own reflection',
      'The key terms in this module will come up repeatedly in later modules',
      'If you\'re skeptical about AI, that\'s healthy. This module is designed to give you an honest picture',
    ],
    lessons: [
      {
        id: 'ai_literacy.what-is-ai-and-why-is-it-in-your-office',
        revision: 2,
        title: 'What is AI, and why is it in your office?',
        objective: 'After this lesson, you\u2019ll be able to say in plain language what AI is, why it applies to research administration, and what this course will do for you.',
        content: "Before any tools or terminology, the big picture.\n\n**What AI is** — software that has learned patterns from enormous amounts of example text, well enough to do useful reading and writing tasks on new material. That’s it. Not a mind, not magic — a very capable pattern machine.\n\n**Why it’s suddenly everywhere** — in the last few years these systems got good enough at ordinary language that they can do real office work: read a 50-page proposal and pull out the PI, the budget, the dates; summarize a progress report; draft a routine email.\n\n**Why it matters for research administration** — your job is unusually document-heavy. Proposals, award notices, subawards, progress reports — most of the work is reading documents and moving what they say into spreadsheets, systems, and summaries. That’s exactly the work this technology is best at drafting for you. It will not make judgment calls, know your institution’s policies, or take responsibility — that stays yours.\n\n**How this course helps** — module by module, you’ll turn one real process at a time into an AI-assisted pipeline you control and verify. The course is self-paced and saves your reading place. Reading, source checks, repairs and assessed work take different amounts of time; no fixed module-completion time has been measured. Start with the course training examples and available supported tools.",
        variant: 'concept',
      },
      {
        id: 'ai_literacy.structured-vs-unstructured-data',
        revision: 2,
        title: 'Structured vs. unstructured data',
        objective: 'After this lesson, you\u2019ll be able to tell structured from unstructured data and explain why converting one to the other is the heart of this course.',
        content: "A proposal contains information in paragraphs, headings and tables. A structured result puts selected information into named fields, such as “Project title,” “Requested amount” and “Project period.” That makes comparison easier, but moving text into a field does not establish that the value is correct.\n\nChoose field names that describe exactly what you need. “Requested amount” and “Awarded amount” are different questions. A source may contain several amounts, dates or organizations. You must check that the extracted value answers the intended question and belongs to the intended source.\n\nKeep the original meaning visible. A value’s currency, units, period and conditions can matter as much as its digits. If a source says “up to $50,000 per year,” reducing it to “$50,000” loses a condition and a time period. A clean table can conceal that loss.\n\nMissing information is a useful result. If the supplied source has no requested amount, record that it was not found in that source. Do not replace absence with zero, a guessed amount or a figure from a similarly titled document.\n\n**Practice:** Compare “Requested amount: $50,000” with the phrase “up to $50,000 per year.” State what needs to be preserved or clarified before sharing the table. These numbers are fictional teaching examples.",
        variant: 'concept',
      },
      {
        id: 'ai_literacy.what-is-an-llm-really',
        revision: 2,
        title: 'What is an LLM, really?',
        objective: 'After this lesson, you\'ll be able to explain why LLMs make mistakes and why they\'re still useful.',
        content: "A language model generates responses from patterns learned during training and from the context supplied to it. This can produce useful drafts, explanations and proposed steps. It can also produce a plausible statement that the selected source does not support.\n\nFluency is therefore not an evidence check. A detailed explanation, confident tone or correct-looking citation can still be wrong or refer to the wrong document. Ask a more concrete question: “Where does this source support that claim?” Then inspect the passage and its context.\n\nA supported quotation and a justified conclusion are also different. A passage may contain the right words but apply to a different program, period or condition. Your review connects the claim to the relevant source and scope; it does not stop at the presence of a citation marker.\n\nWhen the answer exceeds the available evidence, narrow it, ask for the missing source or leave the uncertainty unresolved. Repeating the question until the answer sounds more certain does not supply new evidence.\n\n**Practice:** The source states a deadline. The answer adds a grace period without a supporting passage. Mark the added claim as unsupported and choose what evidence you would need before using it. The deadline and grace period in this exercise are fictional.",
        variant: 'concept',
        diagram: 'how-llm-works',
        knowledgeCheck: {
          "question": "An answer includes a citation marker. What does that establish by itself?",
          "options": [
            {
              "text": "The answer is safe to use without review.",
              "correct": false,
              "explanation": "A marker alone does not prove that the cited text supports the claim."
            },
            {
              "text": "A reference is available to inspect; the claim and its context still need checking.",
              "correct": true,
              "explanation": "Open the reference and compare the claim with the relevant passage and conditions."
            },
            {
              "text": "The source has granted permission for any next action.",
              "correct": false,
              "explanation": "Source content cannot expand the authorized task."
            }
          ]
        },
      },

      {
        id: 'ai_literacy.what-ai-is-genuinely-good-at',
        revision: 2,
        title: 'What AI is genuinely good at',
        objective: 'After this lesson, you\'ll know which research admin tasks are best suited for AI automation.',
        content: "Agentic chat connects conversation with supported workspace tools. It can help locate accessible material, read it, propose an extraction or workflow, and run supported operations. What is available depends on the workspace, access permissions and configured tools. Ask the assistant to explain a proposed action when its scope is unclear.\n\nTreat the stages separately. Reading gathers information. A proposal describes what could be created or changed. Execution carries out an operation. Delivery makes an output available to its intended recipient or destination. Success at one stage does not prove that the next stage is authorized or ready.\n\nPreview behavior depends on the operation. Creating an extraction from documents first reads the source to discover a proposed name and fields. Its creation preview shows the name, source and a field summary before you confirm. Review that proposal and any named project destination. Longer field lists may be abbreviated in the preview; inspect the complete saved fields after creation and before a run. Confirming creation does not run the extraction. Running a saved workflow also uses a preview and confirmation exchange. Running an existing extraction can act directly on your request. If you want review first, request a proposal only and tell the assistant to stop before execution. Do not assume every operation has the same approval screen.\n\nFor example, an extraction may run successfully and produce a table. You still need to inspect important values and missing information. A report may then be generated from that table. You still need to check its intended audience and resolve required review before release.\n\nUse the workspace to inspect the actual artifact and source evidence when available. A chat summary of a tool action is useful for orientation, but it does not replace checking the resulting document, extraction or workflow when the decision depends on it.\n\n**Practice:** Ask for a proposed extraction from an assigned training source, with no delivery. Identify what would need review before running it and what would need review afterward. If the source is not available yet, review these distinctions and return to this practice when the training source is available.",
        variant: 'concept',
      },
      {
        id: 'ai_literacy.what-ai-is-genuinely-bad-at',
        revision: 2,
        title: 'What AI is genuinely bad at',
        objective: 'After this lesson, you\'ll be able to identify AI limitations and avoid common pitfalls in research administration.',
        content: "Honesty about AI's limitations is essential for responsible use in research administration:\n\n• **Judgment calls requiring institutional knowledge** — AI doesn't know your university's internal policies, political dynamics, risk tolerance, or historical context.\n• **Catching its own mistakes** — An LLM cannot reliably self-check. If it extracts the wrong budget figure, it won't flag the error. That's your job.\n• **Math** — LLMs frequently make arithmetic errors. Never trust an LLM to add up budget line items. Use a checked calculator or explicitly recorded human arithmetic. Where code execution is available and authorized, inspect its rule and inputs too. A model explanation is not independent arithmetic evidence.\n• **Novel or unusual document formats** — If a document doesn't follow standard patterns (hand-written notes, unusual layouts, scanned images with poor OCR), extraction quality drops significantly.\n• **Replacing professional judgment on compliance** — AI can flag potential issues, but determining whether a proposal actually meets regulatory requirements requires your expertise.\n\nThe pattern: AI is a powerful first-pass tool. It does the reading; you do the thinking.",
        variant: 'insight',
        knowledgeCheck: {
          question: 'Which task is AI worst at?',
          options: [
            { text: 'Extracting PI names from grant proposals', correct: false, explanation: 'This is actually a strong suit for AI \u2014 it\'s pattern-based extraction from structured documents.' },
            { text: 'Summarizing progress reports', correct: false, explanation: 'Summarization is one of AI\'s strengths \u2014 it\'s good at condensing text.' },
            { text: 'Making judgment calls that require institutional knowledge', correct: true, explanation: 'Correct! AI doesn\'t know your institution\'s policies, politics, or historical context. That requires your expertise.' },
            { text: 'Processing 200 documents in the same format', correct: false, explanation: 'Batch processing with consistent format is ideal for AI \u2014 it handles repetition well.' },
          ],
        },
      },
      {
        id: 'ai_literacy.ai-for-research-administration',
        revision: 2,
        title: 'AI for research administration',
        objective: 'After this lesson, you\'ll be able to describe where AI fits in common research admin workflows and where it doesn\'t.',
        content: "An agent can help organize source material, propose an extraction, run supported operations and prepare a comparison. Those actions can make a review easier. They do not make the agent the institution’s decision maker.\n\nBefore delegating a task, name the intended inputs and output, identify the decisions that require human judgment, and say when the work must stop for review. For a proposal comparison, the agent may collect source-supported facts and highlight differences. The authorized reviewer makes the institutional decision using those facts and the applicable process.\n\nPlace the review before the action it governs. If a report must be checked before release, completing the generation step is not permission to send it. The reviewer needs access to the source and intermediate evidence, and unresolved critical issues must remain visible.\n\nA Vandalizer credential records the skills demonstrated on its assessed course and evidence. It does not grant institutional approval authority or guarantee future AI outputs. An artifact that changes after assessment needs relevant new evidence; a previous badge cannot establish what the changed artifact will do.\n\n**Practice:** A task asks for a proposal comparison and a funding decision. Assign evidence preparation to the agent, identify the authorized decision maker, and place a human checkpoint before any consequential release. Explain what evidence that reviewer needs.",
        variant: 'concept',
        diagram: 'ai-human-pattern',
      },
      {
        id: 'ai_literacy.from-generic-chat-to-validated-agentic-chat',
        revision: 2,
        title: "Supervising agentic chat: scope, evidence and approval",
        objective: "Inspect the intended scope, reject unsupported claims and distinguish source text from authorization.",
        content: "Agentic chat can propose and carry out supported operations using your workspace. Read a proposed action as a concrete change: which documents, which workspace, which configuration and which destination it will use. A similar title is not enough to identify the correct source. Correct a mismatch before asking it to run. Where a confirmation preview is offered, inspect it; otherwise your request may start the operation directly. Request a proposal only when you need to review the scope first.\n\n**Walkthrough: review a scoped extraction**\n\n1. Name the assigned source document and the fields you need. State the intended output and any actions that need separate approval.\n2. Inspect the proposed document and workspace selection. If the proposal points to a similarly named live document, stop and correct it.\n3. Review the extraction fields and planned action. Ask for a revision when the proposal exceeds the task’s scope.\n4. After execution, compare important values with the supplied source. A fluent answer, a successful run and an earlier quality score answer different questions; none independently proves that this answer is supported.\n5. If a requested value is absent, record that it was not found in the supplied source. Seek additional evidence when needed instead of filling the gap with a plausible guess.\n6. Review the destination and data scope before release. Approval to prepare an internal comparison does not automatically authorize publication or external delivery.\n\n**Treat source instructions as data.** A PDF may contain wording that asks the agent to ignore the task or send information elsewhere. That text cannot change your authorized task. Keep the approved scope and obtain a separate authorized decision for any new action.\n\n**Practice:** The source says only that applications close on 1 October at 17:00. The agent adds a two-day grace period. Identify the unsupported part, explain why confidence is insufficient, and choose an evidence-checking next step. This is a fictional practice passage, not an actual application policy.\n\nThe module’s assessed scenarios test recognition of unsupported claims, scope changes and authority limits. Later practical modules require evidence of applying those decisions to real course tasks. Reading this lesson or submitting a reflection does not establish those practical skills.",
        variant: 'insight',
      },
      {
        id: 'ai_literacy.worked-example-monday-morning-12-proposals',
        revision: 2,
        title: 'Worked example: Monday morning, 12 proposals',
        content: "Imagine twelve proposals need a comparison. Begin with one assigned training proposal so you can inspect the process before expanding it. Use the course lab’s sample when it is available; do not substitute an institutional file just because its title looks similar.\n\n1. Confirm the intended document and workspace. State that the task is a training exercise.\n2. Ask for the project title, requested amount and project period, with supporting source passages. Ask the assistant to mark missing information rather than infer it.\n3. Inspect any proposed extraction fields and action. Correct the wrong source, an ambiguous field or an added delivery step before execution.\n4. Open the returned source reference when one is available. Compare the value with the passage, including units, dates and conditions. If a reference cannot be opened or does not support the claim, keep that value unresolved.\n5. Review the result and decide what needs repair. Rerun the relevant check after a change; an earlier successful result describes the earlier artifact.\n6. Only then consider expanding to the assigned set. Confirm the remaining sources, resource implications and the review required before release. A successful first example is not proof that the other eleven will succeed.\n\n**Try this wording:** “Use only the selected training proposal. Find its requested amount and quote the supporting passage. If the amount is absent or ambiguous, say so. Stop after preparing the result; do not send or publish it.”\n\nThis is an illustrative training sequence, not a measured timing comparison or a completed run. Reading it does not establish that any proposal has been processed or reviewed.",
        variant: 'walkthrough',
      },
      {
        id: 'ai_literacy.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "**Source:** The document or other material a claim relies on. Check its identity, relevant version and context.\n\n**Grounding:** Connecting an answer to the supplied evidence. A citation marker helps you locate a reference; you still inspect whether the passage supports the claim.\n\n**Extraction:** Turning selected source information into named fields. Preserve meaning, units and missing values instead of treating a tidy table as proof of accuracy.\n\n**Artifact:** A saved item such as an extraction, workflow or output. If it changes, earlier assessment evidence may no longer describe it.\n\n**Scope:** The intended inputs, workspace, output and permitted actions. A similar filename or a request embedded in a source cannot silently expand that scope.\n\n**Checkpoint:** A review placed before the action it governs. An approval required before release cannot be satisfied by reviewing after sending.\n\n**Execution result:** Evidence of what an operation returned. Completion of an operation does not establish correct interpretation, approval authority or practical competence by itself.\n\n**Quality evidence:** Results from identified tests and configurations. Use them with their limits; do not treat an earlier score as a guarantee for an unchecked source.\n\n**Credential:** A record of the skills demonstrated under the assessed course requirements. It does not grant institutional authority or guarantee every future output.\n\n**Review:** In one sentence, explain why a successful extraction with an unsupported value still needs work before release.",
        variant: 'key-terms',
      },
    ],
    xp: 50,
    icon: 'Lightbulb',
    estimatedMinutes: 10,
  },
  {
    id: 'foundations',
    number: 1,
    title: 'Foundations',
    subtitle: 'Documents In, Intelligence Out',
    description: 'Learn the basics of workflows using a sample NSF proposal from Dr. Sarah Chen. Click Set Up Lab to load it, then build your first extraction workflow.',
    objectives: [
      'Add the sample NSF proposal to your workspace',
      'Create a workflow with an Extraction step and 5 fields',
      'Run the workflow and verify extracted values',
    ],
    tips: [
      'The sample NSF proposal contains clearly labeled fields like PI Name, Institution, and Total Budget',
      'Use clear, descriptive field names in your Extraction that match the document labels',
      'After running, check that PI Name = Sarah Chen and Total Budget = $485,000',
    ],
    lessons: [
      {
        id: 'foundations.what-is-a-workflow',
        revision: 2,
        title: 'What is a workflow?',
        objective: 'After this lesson, you\'ll understand how workflows differ from ad-hoc chat and why that matters for research administration.',
        content: "Start with one assigned training proposal and one clear question: which values belong in the fields requested by this course version? An extraction template describes the information to find. A workflow connects saved operations into a process. You can learn to supervise a single extraction before building a multi-step workflow.\n\nIn agentic chat, you can ask the assistant to help find the assigned document, propose a template and run an extraction. Those are separate actions. A proposal is not a saved template; a saved template is not a completed run; a completed run is not a verified result. Check which stage you actually reached.\n\nBegin with a planning request: “Use only the assigned training proposal. Propose the fields for this exercise, identify the selected document and workspace, and stop before creating or running anything.” Compare the response with the assignment. Correct an extra document, unclear field or wrong workspace before authorizing the next action.\n\nConfirmation behavior depends on the operation. Creating an extraction from documents discovers fields before its confirmation preview. Review the proposed name, selected source, field summary and any named project destination before confirming creation. Longer field lists may be abbreviated; inspect the complete saved template before execution. Running an existing extraction can execute directly. State the stop boundary explicitly instead of expecting every action to display an approval screen.\n\n**Practice:** The assistant proposes a workflow that also emails the result. Explain why that exceeds a task limited to extracting and checking five values. Narrow the proposal before proceeding.",
        variant: 'concept',
      },
      {
        id: 'foundations.what-you-ll-build',
        revision: 2,
        title: 'What you\'ll build',
        content: "Here's the end state for this module's lab exercise:\n\n• A workflow called something like \"Grant Proposal Extractor\"\n• An Extraction with at least 5 fields: PI Name, Total Budget, Sponsoring Agency, Project Period, Institution\n• A run result showing Dr. Sarah Chen extracted from the sample NSF proposal, with a budget of $485,000\n\nThese are the example targets, not evidence that a run has occurred. Your original course distinguishes its three-field base requirement from five- and eight-field enrichment; consult its saved challenge criteria. Review the actual assigned source and result, including currency, period and field meaning. Do not copy the expected name or amount from this lesson and call it an extracted result.",
        variant: 'walkthrough',
      },
      {
        id: 'foundations.the-document-pipeline',
        revision: 2,
        title: 'The document pipeline',
        objective: 'After this lesson, you\'ll understand what happens to a document between upload and extraction.',
        content: "Use **Set Up Lab** to load the assigned training document when the exercise is available. Confirm the document belongs to this assignment and the intended workspace. Similar filenames can refer to different uploads or versions; open the file and inspect its contents instead of choosing by name alone.\n\nDocument preparation and assessment are different steps. Uploading a file may start text processing, and a visible file is not necessarily ready for extraction. If the assistant reports that processing is still underway, wait for readiness. If preparation failed, investigate that failure instead of repeatedly requesting the same extraction.\n\nCheck a relevant paragraph and, if present, a budget table. Text conversion can lose reading order, columns or symbols. Compare an important amount and its label with the original document. A search result or a short source excerpt may help locate evidence, but the surrounding context can change what it means.\n\nThe sources available to chat have different meanings. Selecting or naming a source does not establish that every page was read, that retrieval succeeded or that a returned claim is correct.\n\n**Selected files:** The files you select supply document context for the turn and can be used by supported document tools. Open the specific training copy and verify its content and version. A read or excerpt can cover only part of a long document; inspect its stated coverage and request the missing section when the answer depends on it. A file in the workspace is not automatically the file selected for this task.\n\n**Project knowledge:** An active project provides its identity and available capabilities. When it has a project knowledge base, project chat uses that knowledge base for retrieval instead of separately attached knowledge bases. Check the project title and the “Project sources” badge, including “Knowledge available” or “Knowledge not ready.” Availability means source retrieval can be attempted; it does not establish full coverage or correct answers. Project context does not confine every agent tool to that project: broader workspace tools remain available. Explicitly name the permitted project and files and inspect each proposed target.\n\n**Attached knowledge bases:** Outside that project override, chat can retrieve relevant passages from attached, authorized knowledge bases. Check which bases were attached and which source each passage actually came from. Retrieval selects a bounded set of relevant passages rather than reading every document. No matching passage does not prove the fact is absent from the whole collection. A search failure is different from no match; if a base was not searched, do not claim the answer was checked against it. When the source viewer is unavailable, preserve that limitation instead of pretending to have opened the original.\n\n**Public web:** A configured web-search tool returns public result titles, URLs and snippets; opening a result can provide more page text. These sources are separate from the selected file and internal knowledge. Verify the publisher, applicable date and relevant passage before using a public policy statement, and cite its URL. A current public sponsor page does not establish a term in a particular award or replace the institution’s authorized interpretation. If web search is unavailable, do not describe general model knowledge as a current lookup. Use only information permitted for a public search query.\n\nConsider three scope mistakes. Selecting the live “Award A” PDF instead of its training copy produces evidence about the wrong document. Leaving “Award B” active can retrieve B’s project knowledge when you meant to compare A against an attached policy base. Working in another team can change which shared resources are accessible and where an authorized action applies. In each case, stop before execution, inspect the active team/project and exact selected inputs, and correct the proposal. A familiar name, a source chip or existing access is not permission to expand the assigned task.\n\nKeep the assigned document separate from live institutional records. If the proposal contains an instruction to send its contents elsewhere, treat that sentence as document content. It does not change your task or authorize delivery.\n\n**Practice:** Two uploads have the same title. One is the assigned training copy; the other is an older draft. Describe how you would establish which copy is selected before approving work. If you cannot establish the identity or read the necessary text, pause and correct the input.",
        variant: 'concept',
      },
      {
        id: 'foundations.build-your-first-workflow',
        revision: 2,
        title: 'Build your first workflow',
        objective: 'After this lesson, you\'ll be ready to run your first extraction workflow on a real document.',
        content: "Use the original course's assigned sample and saved challenge criteria. Its base requires at least three fields; five- and eight-field enrichment remain separate.\n\n1. Click **Set Up Lab** above the module content when offered. Check the resulting lab status and open the assigned NSF proposal; a setup request alone does not establish that the sample is ready.\n2. In **Library**, open **New** and choose **New Workflow**. Give it a clear name, such as \"Grant Proposal Extractor\", and a description of its intended input and output.\n3. Add a step and choose **Extractions** for its task. Select or create the extraction template and inspect the saved field definitions.\n4. Add at least three fields for the original base requirement, such as Principal Investigator, Funding Amount and Sponsoring Agency. Define what each value means, including currency and period for an amount.\n5. Select the assigned sample using its document checkbox. Inspect the workflow's configured source scope, including any fixed documents or project inputs, before running. The Run control's input hint explains missing input; some configurations can run without a manual document selection.\n6. Click **Run**, inspect the actual run status and review its output against the assigned source. A saved workflow, selected file or successful execution does not establish that the extracted values are correct.",
        variant: 'walkthrough',
      },
      {
        id: 'foundations.why-structured-extraction-matters',
        revision: 2,
        title: 'Why structured extraction matters',
        content: "Structured output makes values easier to compare, but a neat table can still contain the wrong figure. Check each required field against the assigned source. Use available source links or the document viewer, then read enough surrounding text to establish the value’s meaning. If a source link is unavailable, open the assigned document directly; do not invent a citation.\n\nSuppose a fictional proposal lists a total request of $485,000 and a first-year subtotal of $160,000. A Total Budget result of $160,000 has a real number from the document but answers the wrong question. A quality badge or confident explanation cannot resolve that mismatch.\n\nRepair the cause. If the field definition was ambiguous, clarify that it requires the total requested amount and its currency. If the wrong file was selected, correct the input. If the source text lost table structure, inspect document preparation. Then perform a new run when appropriate and compare its output with the source again.\n\nKeep the earlier result distinguishable from the corrected one. Changing a displayed answer or writing “fixed” in chat is not evidence that the revised configuration produced a correct output. A later module explores systematic validation; here, build the habit of checking the actual result you intend to use.\n\n**Practice:** Identify the field, supporting source passage, discrepancy and next action for the fictional budget mismatch. Explain what evidence would show that the repair worked.",
        variant: 'insight',
      },
      {
        id: 'foundations.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "**Assigned input:** the specific training document the exercise requires. Its identity matters even when other files have the same title.\n\n**Extraction template:** the saved field definitions used to ask structured questions of a document. A template is configuration; it does not prove any values were extracted.\n\n**Workflow:** a saved arrangement of operations. Workflows become useful when a task needs connected steps. Saving a workflow and completing an execution are separate events.\n\n**Proposal and review boundary:** a description of the intended scope and the point where you decide whether work may proceed. Ask explicitly for proposal-only help when you are still reviewing. Operation-specific confirmation does not replace that supervision.\n\n**Execution result:** the status and output of a particular run on particular inputs. Check that it belongs to the source and configuration you reviewed.\n\n**Source check:** your comparison of a returned value with its supporting passage, including units, dates and conditions. A link helps you inspect evidence; the link alone does not make the value correct.\n\n**Repair:** a correction followed by the evidence needed to establish its effect. Preserve the distinction between the original result and a later run.\n\nBefore moving on, explain the chain in your own words: what you approved, what actually ran, what source you checked and what you decided about the output. If a link is missing, identify the next check instead of filling the gap with the assistant’s assurance.\n\n### Controlled recovery examples\n\n**A tool reports failure:** In a training task, creating the extraction succeeded but the next run reports an error. Preserve the saved template and the error. Open the existing template and inspect any returned run result or status before deciding what failed. Use “Review recovery options” when offered to ask the assistant to inspect existing work and explain a repair. That request does not itself establish that the repair succeeded. Do not create another template merely because the later action failed.\n\n**The chat reply is interrupted:** You see a completed creation card followed by an unfinished run card when the connection drops or you stop the response. Partial output can remain visible, and an action already started may still finish. Read the original run’s status and saved results; for workflow runs, use the named existing run and its available status controls. Do not treat a missing reply as proof that execution never started. A generic retry resends the previous request and may repeat work; use a specific inspection request first: “Check the existing training run and report its saved status. Do not create or run anything again.” Stopping a response does not roll back completed actions.\n\n**Earlier context is unavailable:** After reopening chat, a context reset or compaction, or an expired session, the assistant may no longer have the exact earlier source selection and decisions. Reopen the existing conversation and saved artifacts, sign in again if required, and re-establish the active team, project, training document and course enrollment. Restate the bounded task and link the existing run or result. Ask for inspection before another operation. A summary is not the original evidence, and missing chat context does not mean saved work or course credit was erased. If the original run cannot be located, record its outcome as unresolved; do not invent a successful receipt or silently start a duplicate.\n\n**A batch is incomplete:** If two training documents have completed results and a third has unreadable text, keep the two results and compare them with their sources. Repair and verify the third input before a targeted new run. Retain the original failure and the new result, and report remaining exceptions. Check any external action separately before repeating it; a failed batch item cannot establish that all earlier effects were undone. The Batch Processing module develops this per-document recovery in detail.\n\n**Recovery practice:** In each example, name the saved evidence to inspect, the completed work to preserve and the specific condition that would justify a new operation. When status remains unknown, state that uncertainty rather than treating retry as verification.",
        variant: 'key-terms',
      },
    ],
    xp: 100,
    icon: 'BookOpen',
    estimatedMinutes: 15,
  },
  {
    id: 'process_mapping',
    number: 2,
    title: 'Thinking in Workflows',
    subtitle: 'See Your Work as Automatable Processes',
    description: 'Before you can build a workflow, you need to see your work differently. This module teaches you to recognize the repeatable processes hiding in your daily tasks, identify which parts are suitable for AI, and which parts need your expertise.',
    objectives: [
      'Recognize repeatable processes in your research administration work',
      'Identify which parts of a process are AI-suitable vs. human-judgment',
      'Apply the process decomposition framework to a real task from your work',
    ],
    tips: [
      'Think about the tasks you do every week that follow the same pattern',
      'The best workflow candidates are tasks where you spend most of your time reading and re-typing',
      'Don\'t try to automate everything \u2014 the goal is to automate the tedious parts so you can focus on the important parts',
    ],
    lessons: [
      {
        id: 'process_mapping.from-one-workflow-to-many',
        revision: 2,
        title: 'From one workflow to many',
        objective: 'After this lesson, you\'ll be able to identify repeatable processes in your daily work that are ready for automation.',
        content: "A task does not become better because it has more steps. Start with the result you need and the evidence that would make it usable. Then choose a method that fits the input, repetition and decisions involved.\n\nFor a one-off question about one document, a bounded chat request with source checking may be enough. If you repeatedly need the same fields from similar documents, a reusable extraction can make the field definitions explicit. If the result requires connected operations with defined inputs and outputs, a saved workflow may be useful.\n\nA **project** organizes an ongoing piece of work: for example, an award's amendments, reports, related knowledge and reusable tools. It can provide a stable home for repeated conversations and artifacts. It does not itself run an extraction or make every source ready for chat. Check the active project, selected sources and knowledge availability; a project name is not proof that a particular passage was read. You can use chat, an extraction or a workflow within that organized context.\n\nAn **automation** starts a saved workflow or extraction when a configured event occurs, such as a document arriving in a watched folder or a schedule becoming due. Consider it only after a manually inspected run establishes that the method fits the intended inputs. For recurring proposal intake, review the exact watched folder, saved action, expected outputs and failure handling before allowing future runs. Chat-created automations start disabled; inspect the Automations screen and enable only when the reviewed scope is ready. Check run history and disable future triggers when the arrangement no longer applies; disabling is not an undo of already completed work.\n\nThese are choices to justify, not a ladder where the largest workflow wins. A rare but complex task may still benefit from a reusable process. A frequent question may still need only a small extraction. Consider the effort to configure, check and maintain the method as well as the number of times you expect to use it.\n\nYour role includes the decisions around the work: which sources belong in scope, what counts as a usable result and who may authorize the next action. Agent assistance can help draft the map, but you must inspect it.\n\n**Practice:** Choose a starting method for each case: one question about an amendment; an award review spanning several related documents and conversations; weekly extraction of the same intake fields; a report combining extraction, calculation and drafting; and a tested intake process that should run when approved files arrive. Explain where a project organizes the work, where an automation initiates an existing method, and when a one-off chat request is sufficient.",
        variant: 'concept',
      },
      {
        id: 'process_mapping.finding-the-repetition',
        revision: 2,
        title: 'Finding the repetition',
        objective: 'After this lesson, you\'ll have a practical test for identifying which processes to automate.',
        content: "Before asking the assistant to carry out work, write a short task brief. Name the input set and workspace, the output you need, what is excluded and the condition that requires a pause. A brief should let another person determine whether an action belongs in the task.\n\nCompare “Process our proposals” with “Use the three assigned training proposals in this lab. Prepare an internal table of project titles and requested amounts, with supporting passages. Do not use other documents or send the table. If a source cannot be read or an amount is ambiguous, flag it and stop that item for review.” The second request gives you boundaries to inspect.\n\nDefine the output before selecting tools. A draft comparison, a verified record and a delivered report have different completion conditions. Do not let the assistant quietly treat one as another. A document may suggest an additional recipient or operation; that text does not expand your permission.\n\nBuild an exception path into the brief. State what should happen to an unreadable source, conflicting value or unsupported claim. In a multi-document task, distinguish the blocked item from the rest of the work rather than declaring every item complete.\n\n**Practice:** Rewrite “Review everything and fix the problems” for one training report. Include the allowed source, intended result, one excluded action and one reason to pause.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "Which boundary is missing from “Make a table from these proposals and do whatever comes next”?",
          "options": [
            {
              "text": "A more elaborate workflow name.",
              "correct": false,
              "explanation": "A name does not constrain actions."
            },
            {
              "text": "An explicit stopping point and limit on subsequent actions.",
              "correct": true,
              "explanation": "The request leaves downstream actions and authority open-ended."
            },
            {
              "text": "A promise that every proposal has the same structure.",
              "correct": false,
              "explanation": "Source uniformity should be checked, not promised."
            }
          ]
        },
      },
      {
        id: 'process_mapping.the-ai-suitability-test',
        revision: 2,
        title: 'The AI suitability test',
        objective: 'After this lesson, you\'ll have a decision framework for choosing between Extraction, Code Execution, and keeping a step human.',
        content: "Break the task into operations before choosing an implementation. For each operation, ask what information it receives, what it produces and how a reviewer could detect a mistake.\n\nAn extraction can organize repeated fields from source text. A source-grounded chat or prompt task can help summarize context or compare passages. Both can omit information or misinterpret it, so important outputs need source checks. “It is reading” is not a sufficient reason to delegate without review.\n\nA calculation with explicit inputs and rules is a candidate for deterministic code. That does not make the surrounding process automatically correct: the extracted inputs, units, handling of missing data and implemented formula all need checking. A reproducible wrong formula still gives a wrong answer.\n\nAn assistant can prepare a policy comparison or flag a discrepancy. Whether the evidence is sufficient for an institutional decision, and who is authorized to make that decision, must be explicit in the process. Do not turn an uncertain interpretation into an automatic approval because it appears in a table.\n\n**Practice:** For a budget review, separate finding amounts, summing approved categories, explaining a variance and authorizing release. Name the evidence and reviewer needed at each stage. If a proposed tool cannot produce a reviewable result, change the method or keep that operation manual.",
        variant: 'insight',
        diagram: 'ai-suitability',
      },
      {
        id: 'process_mapping.walkthrough-mapping-a-real-process',
        revision: 2,
        title: 'Walkthrough: Mapping a real process',
        content: "Use a training proposal to map an intake task before building it. A useful map identifies the source, operations, evidence, reviewer and next action. It also shows where work stops.\n\n1. **Input:** the assigned proposal in the training workspace. Check that its relevant text is readable.\n2. **Prepare:** extract the requested fields and identify potentially missing sections. Preserve source references and uncertainty instead of labeling the proposal compliant.\n3. **Check:** compare required values with their supporting passages. If a calculation is needed, verify the input values and rule as well as the total.\n4. **Review:** the designated reviewer inspects the evidence and discrepancies. An incomplete section or ambiguous requirement takes an exception path; the assistant must not invent missing information.\n5. **Decide:** the authorized person determines the next step. Preparing an internal summary does not authorize submission or contact with a recipient.\n6. **Release, if authorized:** inspect the exact artifact and destination before any separate delivery action. Record whether that delivery actually succeeded.\n\nA box labeled “human review” is not enough. Put it before the action that depends on it, identify who reviews and specify the evidence they receive. If the implementation cannot pause at that point, end the automated portion there and perform the next action separately.\n\n**Practice:** Move a review box that currently appears after external delivery to the correct place, and name the information the reviewer needs.",
        variant: 'walkthrough',
      },
      {
        id: 'process_mapping.common-processes-that-become-workflows',
        revision: 2,
        title: 'Common processes that become workflows',
        content: "Use common office tasks as candidates for analysis, not automatic recipes. The same task name can hide very different sources, outputs and authority requirements.\n\nFor proposal intake, repeated fixed fields may suit an extraction; an unusual amendment may need a bounded question with close source review. A progress-report comparison may need structured facts and a narrative explanation, with an identified reviewer for interpretation. A budget summary may add deterministic arithmetic, but its figures still need source support.\n\nFor each candidate, record the expected benefit and the cost of checking it. Include setup, exceptions and maintenance when a document format or requirement changes. Do not invent a percentage of work saved before observing actual runs. A process that produces fast drafts but expensive corrections may not improve the work overall.\n\nChoose one small candidate to test. Specify a representative source, a difficult case and a missing-information case. Decide what evidence would justify extending the process and what failure would stop the trial. A successful example supports that example; it does not prove that every future input will work.\n\n**Practice:** Compare two candidates from a fictional office: weekly extraction of five intake fields and a one-time interpretation of an unusual sponsor clause. Explain how their evidence and review needs differ. Use training examples without copying sensitive workplace documents into the exercise.",
        variant: 'concept',
      },
      {
        id: 'process_mapping.worked-example-mapping-progress-report-review',
        revision: 2,
        title: 'Worked example: mapping progress-report review',
        content: "Consider a fictional annual progress report. The task is to prepare an internal review brief, not submit a sponsor report. The allowed sources are the assigned report and the approved milestone list. The intended reviewer is the responsible program administrator.\n\n**Prepare:** identify reported accomplishments, publications and expenditures. Compare the claims with the stated milestones, retaining supporting passages and gaps. If arithmetic is useful, define its inputs and rule separately from any narrative interpretation.\n\n**Pause on exceptions:** an unreadable table, absent milestone or conflicting period remains unresolved. Do not import a value from another report because its title looks similar. The reviewer receives the discrepancy and the specific source that needs attention.\n\n**Review:** the program administrator checks important claims and decides which questions require follow-up with the investigator or fiscal reviewer. The assistant can draft questions; the map does not give it permission to send them.\n\n**Output:** an internal brief with source references, unresolved issues and a clear review status. A later decision may authorize a different artifact or delivery, but that is outside this task’s stopping point.\n\n**Practice:** Draft this map in your own words. Then critique an assistant proposal that ends with “submit to the sponsor portal.” Explain the scope change and revise the ending before any execution. Do not assume a drawn checkpoint is an implemented pause; verify the actual action sequence before using the design.",
        variant: 'walkthrough',
      },
      {
        id: 'process_mapping.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "**Input boundary:** the named documents, versions and workspace the task may use. A broad topic such as “all grants” is not a precise input set.\n\n**Operation:** a bounded action with an identifiable result, such as extracting a value, calculating a total or drafting a summary. Choose its implementation according to the information and checks it needs.\n\n**Evidence:** the source passages, configuration, intermediate results or execution status a reviewer uses to assess the output. A polished diagram is not execution evidence.\n\n**Checkpoint:** a decision placed before the action that depends on it. State the reviewer, evidence and permitted next step. If the product cannot enforce a pause there, separate the actions rather than assuming the diagram enforces it.\n\n**Exception path:** what happens when a required input or check is unavailable. Identify the blocked item, preserve useful completed work and name the decision needed to continue.\n\n**Handoff:** work passed to a named role with enough context to act. Preparing a handoff and actually sending it are different actions.\n\n**Stopping condition:** the point where the requested result is ready for its stated use, or where an unresolved issue prevents further work.\n\nBefore building, explain why your chosen method fits the repetition and output. Walk through a normal case and a failure case. Ask whether either can reach a consequential action without the required review. Revise that path before you create the workflow.",
        variant: 'key-terms',
      },
    ],
    xp: 100,
    icon: 'Search',
    estimatedMinutes: 15,
  },
  {
    id: 'workflow_design',
    number: 3,
    title: 'Workflow Design',
    subtitle: 'From Process Map to Pipeline Architecture',
    description: 'Now that you can decompose a process, learn how to translate it into a specific workflow architecture. Which task types fit which steps? How should data flow? Where do humans stay in the loop?',
    objectives: [
      'Map process steps to specific Vandalizer task types',
      'Understand the extract-reason-deliver pattern \u2014 and when Extraction is the wrong first step',
      'Design workflows that support human review, not replace it',
    ],
    tips: [
      'Start simple \u2014 a 2-3 step workflow that works is better than a 10-step workflow that doesn\'t',
      'Design your output for the person who will review it, not for the computer',
      'When in doubt about step granularity, split \u2014 it\'s easier to combine steps later than to debug one giant step',
    ],
    lessons: [
      {
        id: 'workflow_design.from-process-map-to-workflow-architecture',
        revision: 2,
        title: 'From process map to workflow architecture',
        objective: 'After this lesson, you\'ll be able to map each step in a process to a specific Vandalizer task type.',
        content: "In Module 2, you decomposed a process into steps and identified which are AI-suitable vs. which stay human. Now you'll map each AI-suitable step to a specific Vandalizer task type — turning your process map into a buildable architecture.\n\nThe mapping is straightforward:\n• \"Find specific fields in a document\" → Extraction task with an Extraction\n• \"Read a short or context-heavy document and answer a question about it\" → Prompt task with the document as its input (no Extraction first)\n• \"Analyze or summarize the extracted data\" → Prompt task\n• \"Compute, total, or apply rules\" → A permitted deterministic calculation with checked inputs, such as a calculator or authorized Code Execution task. Record an external calculation explicitly before a later model step relies on it\n• \"Check a document for specific sections or elements\" → Prompt task\n• \"Produce a formatted report or export\" → Document Renderer or Data Export\n• \"Compare this document to another\" → Add Document + Prompt task\n\nThe key insight: you're not starting from scratch asking \"what can this tool do?\" You're starting from your process and asking \"which tool handles this step?\"",
        variant: 'concept',
      },
      {
        id: 'workflow_design.the-extract-reason-deliver-pattern',
        revision: 2,
        title: 'The extract-reason-deliver pattern',
        objective: 'After this lesson, you\'ll understand the most reliable workflow pattern for research administration and why it works.',
        content: "Follow the data through the design before you run it. If a step receives only an extracted table, it cannot reliably interpret a clause omitted from that table. A final report cannot recover evidence that no earlier step retained or supplied.\n\nThe current chat builder wires the first document-consuming step to workflow documents and later document-consuming steps to the previous step’s output. In the editor, input-source choices include Step Input (the immediately preceding output), Workflow Documents and Selected Document. Inspect the configured source for each step; do not infer it from the step’s name.\n\nChoose extraction when defined fields serve the task. A focused prompt over relevant source text may fit a context-dependent question without a separate extraction. Neither route is inherently more accurate for every document. Test the chosen input and output on representative cases, including a case where the omitted context matters.\n\nInspect pinned documents as well as documents selected for the current run. A workflow can include fixed inputs, so “run on this file” does not necessarily describe the complete input set. Remove unintended sources or explain why a required reference belongs in scope.\n\n**Practice:** A comparison step receives only five extracted values, but its question depends on an amendment paragraph. Identify the missing input and propose a reviewable configuration change before running.",
        variant: 'concept',
        diagram: 'extract-reason-deliver',
        knowledgeCheck: {
          "question": "A later step must interpret a clause omitted from the extracted table it receives. What should change?",
          "options": [
            {
              "text": "Its input must include the relevant source context, or the task must be narrowed.",
              "correct": true,
              "explanation": "The needed evidence must reach the operation that uses it."
            },
            {
              "text": "Nothing; later steps automatically know all original documents.",
              "correct": false,
              "explanation": "Configured inputs determine available context; the step name does not."
            },
            {
              "text": "Only the report’s font size.",
              "correct": false,
              "explanation": "Presentation cannot supply missing evidence."
            }
          ]
        },
      },
      {
        id: 'workflow_design.designing-for-your-reviewer',
        revision: 2,
        title: 'Designing for your reviewer',
        objective: 'After this lesson, you\'ll be able to design workflow output that makes human review fast rather than cumbersome.',
        content: "Here's a truth about AI in research administration: someone will always review the output. Maybe it's you, maybe it's a compliance officer, maybe it's a PI. Your workflow should make that review easy and efficient.\n\nDesign principles for reviewable output:\n\n• **Show your sources** — When the workflow extracts a budget figure, the output should make it easy to verify against the source document.\n• **Flag uncertainty** — If a field couldn't be found or the value seems unusual, the output should say so.\n• **Structure for scanning** — Make the source values, unresolved issues and required decisions easy to find. Scanning helps locate review work; it does not establish that every value is correct.\n• **Separate data from analysis** — Show the raw extracted data first, then the analysis or recommendations.\n\nThe workflow's job is not to eliminate review. It's to make review fast and focused.",
        variant: 'insight',
      },
      {
        id: 'workflow_design.walkthrough-designing-a-compliance-review-pipeline',
        revision: 2,
        title: 'Walkthrough: Designing a compliance review pipeline',
        content: "There are different approval moments. Confirming creation permits the proposed workspace artifact to be created. Confirming a workflow run permits execution to start. A configured Approval step can pause an executing workflow for review before later steps continue. One does not substitute for the others.\n\nPlace the Approval step before the operation whose consequences require a decision. Configure the intended reviewer and clear instructions: what evidence to inspect, which discrepancies prevent approval and what the next step will do. Review timeout behavior too; a timeout action that approves automatically does not represent an explicit human decision.\n\nTest the boundary on training data. Confirm that the run reports a pending approval, the reviewer receives the relevant intermediate output and downstream work has not already occurred. Inspect what happens after approval and rejection. A gate drawn in a diagram or mentioned in a prompt is not proof of these behaviors.\n\nUse these three decisions with a concrete training run named “Subaward comparison — training,” paused at “Review source findings” before an internal memo step. These are examples, not requests to operate on a live run. An assigned reviewer or workflow manager must have permission to decide the actual review.\n\n**Approve:** The source findings match the assigned agreement, the missing effective date remains explicitly unresolved, and the later step only drafts an internal memo that preserves that uncertainty. Ask to approve this named paused run and step. Review the confirmation that says it will resume the workflow, then confirm only if that consequence is intended. Approval records a decision and requests resumption; inspect the actual run status and later output before calling it complete. If resumption fails after the decision was saved, inspect the recorded review instead of treating another click as a new authorization.\n\n**Reject:** The same paused run claims an effective date that the source does not establish, and its later memo would present that date as fact. Ask to reject this named run and step, recording the unsupported date as the reason. Inspect the rejection confirmation: this decision ends the run as failed rather than continuing it. Check the persisted review and run status. Rejection does not delete the findings or undo work completed before the pause.\n\n**Revise:** Before confirming a proposed run, you discover it names two documents when the assignment allows only the training agreement. Do not approve that proposal. Ask for only the assigned document and no execution yet; inspect the saved workflow’s fixed documents and the revised proposal before approving a new run. If a run has already executed or reached review, editing the workflow does not rewrite its recorded inputs or results. Preserve that history, resolve its pending decision, and prepare a separately inspected run only when repeating the work is appropriate.\n\nThe chat card’s “Cancel action” sends a cancellation request for the proposed action. It is not the same as rejecting a workflow’s pending review, stopping an already running job, or rolling back a completed change. Read the resulting status and inspect saved work before retrying.\n\nIf the required pause is not supported or cannot be verified for the design, end the automated portion before the consequential action and handle the next action separately. Preserve unresolved work instead of describing it as completed.\n\n**Practice:** A design formats a report, sends it and then asks for approval. Move the review before sending and specify the artifact, recipient and unresolved issues the reviewer must inspect.",
        variant: 'walkthrough',
      },
      {
        id: 'workflow_design.when-to-split-when-to-combine',
        revision: 2,
        title: 'When to split, when to combine',
        content: "Choose step boundaries for a reason. Split operations when an intermediate result needs inspection, a different kind of processing is required or a decision must occur before the next action. A separate step can make a mistake easier to locate, but more steps also add configuration and data connections to check.\n\nA small focused operation may belong in one step when its input, output and evidence remain clear. Do not automatically prepend extraction to a context-dependent question, and do not automatically combine extraction, interpretation and release into one prompt. Evaluate whether the chosen boundary makes the result easier to test and supervise.\n\nEach new connection has a contract: which fields or text are passed, what happens to missing values and how the next operation recognizes failure. If a formatter turns an error message into a polished report, the design has hidden a failure rather than handled it.\n\nTest one normal input and one failure case at the proposed boundary. Check that the failure remains visible and prevents any dependent action that requires success. Reusing an earlier intermediate result after editing its producing step needs a fresh check of compatibility.\n\n**Practice:** Explain whether extraction and arithmetic should be separate in a budget-summary design. Name the intermediate evidence you need and how missing input should affect the calculation.",
        variant: 'insight',
        diagram: 'step-granularity',
      },
      {
        id: 'workflow_design.worked-example-designing-subaward-intake',
        revision: 2,
        title: 'Worked example: designing subaward intake',
        content: "Consider a fictional subaward review. The assigned sources are a training agreement and the specified reference terms. The requested output is an internal deviation brief for the subaward officer. Updating a tracking system or contacting another institution is outside this design.\n\nFirst, identify the parties, amount, period and relevant terms with source support. Choose structured extraction for repeated fields, but retain the context needed to interpret exceptions. Do not assume a long agreement becomes safer to analyze simply because it was reduced to a few values.\n\nNext, compare the supplied terms with the specified reference. Make sure that comparison step actually receives both the agreement evidence and reference terms. Mark ambiguity as unresolved; the task is to prepare a comparison, not issue an institutional approval.\n\nThen format a brief that separates the source facts, possible deviations and questions for the reviewer. End before any external release. If the design later includes a release operation, add and verify the required approval boundary before it.\n\n**Practice:** Critique a proposal that compares extracted terms without supplying the reference document, then sends a “compliant” report automatically. Identify the missing data connection and the missing decision. Revise both before creation or execution.",
        variant: 'walkthrough',
      },
      {
        id: 'workflow_design.chat-driven-workflow-design-v5-0',
        revision: 2,
        title: 'Chat-driven workflow design (v5.0)',
        objective: 'After this lesson, you\'ll be able to design and dispatch workflows from conversation, using the agent as a design partner.',
        content: "In Vandalizer 5.0, you don't have to translate your process map into a workflow by yourself. The agent can help.\n\n**Design in chat.** Describe the process in plain English: *\"I need a 3-step workflow for subaward review. Step 1 extracts parties, amounts, and compliance terms. Step 2 analyzes key obligations. Step 3 formats a compliance summary.\"* The agent proposes an architecture. Check whether each task type fits its input and purpose, then inspect and refine the saved configuration in the editor.\n\n**Dispatch from chat.** Once built, you don't navigate to the workflow every time — you just ask: *\"Run the subaward review on this agreement.\"* Check the named workflow and intended input before confirming the run. Inspect its actual status and results. A configured Approval step can pause for review before later work; inspect the reviewer, placement and timeout settings rather than assuming every run has that boundary.\n\n**Build faster with propose-then-refine.** For extractions specifically, you can say *\"Propose an extraction set for NIH R01 proposals based on this document\"* and the agent analyzes the document, suggests fields, and creates the template on confirmation. Review the proposed fields and inspect the saved settings; no fixed time saving is established.\n\nThe trade-off is still the same as any AI output: the agent's proposal is a starting point, not the final design. Use it to skip boilerplate, then apply your expertise to the parts that matter.",
        variant: 'insight',
      },
      {
        id: 'workflow_design.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "These are the design decisions you'll face for every workflow you build. You've seen them applied in the compliance review walkthrough — use this as a reference when designing your own pipelines.\n\nStep granularity — How many steps should your workflow have? Each step should do one clear thing. If you can't describe a step's purpose in one sentence, split it.\n\nTask type selection — Choose the simplest task type that gets the job done. If you need structured data from a document, use Extraction — don't write a Prompt asking the LLM to produce JSON. If you need a judgement or a narrative about a short document, a Prompt reading the document itself is usually the simpler tool. Extraction is a choice, not a mandatory first step.\n\nData flow — Inspect the saved input source for each step and any task override. Step Input uses the previous output; Workflow Documents supplies the run's documents; a Selected Document supplies that configured source. Later steps do not automatically receive all original context. Keep required references available to the operation that needs them.\n\nHuman checkpoints — Place the required review before the action whose consequences depend on it. Reviewing a final internal draft may be appropriate; reviewing after a send cannot prevent that send. Configure and test a supported pause or keep the later action separate. A written request for approval is not itself a runtime gate.\n\nError tolerance — What happens if the LLM extracts a field incorrectly? Design your workflow so errors are visible in the output, not hidden. Show source data alongside conclusions.",
        variant: 'key-terms',
      },
    ],
    xp: 100,
    icon: 'Compass',
    estimatedMinutes: 15,
  },
  {
    id: 'extraction_engine',
    number: 4,
    title: 'Extraction Engine',
    subtitle: 'Master the Extraction Pipeline',
    description: 'Build a comprehensive 20+ field extraction using a sample NIH R01 proposal from Dr. James Park. The document has budget breakdowns, key personnel, and specific aims to extract.',
    objectives: [
      'Add the sample NIH R01 proposal to your workspace',
      'Create an Extraction with 15+ fields covering all document sections',
      'Extract each budget category as its own field, plus personnel, aims, and compliance fields',
    ],
    tips: [
      'The NIH R01 has clearly structured sections: budget, key personnel, specific aims, vertebrate animals',
      'Use the Allowed values setting on a field to constrain answers to a list (e.g., Human Subjects: Yes/No, Clinical Trial: Yes/No)',
      'Mark fields like Co-Investigator as optional since there may be multiple',
    ],
    lessons: [
      {
        id: 'extraction_engine.one-pass-vs-two-pass-extraction',
        revision: 2,
        title: 'One-pass vs. two-pass extraction',
        objective: 'After this lesson, you\'ll know when to use two-pass vs. consensus extraction and what quality tradeoff you\'re making.',
        diagram: 'extraction-output-example',
        content: "An extraction strategy controls how the engine attempts the task. It does not establish that the returned values are true. Start with the source, field meanings and a small set of checked examples; then compare the available configurations against those examples.\n\nOne-pass mode uses a configured extraction pass for each document and field group. Two-pass mode first produces a draft, then attempts refinement. Each pass can use its own configured model and reasoning settings. Do not assume both passes use the same model, or that a mode label describes every setting in the saved extraction.\n\nA second pass can help, but it can also retain or introduce an error. In the current engine, refinement failure can return the first-pass draft. A completed result therefore does not prove that two successful passes independently verified each value. Inspect the output and any available run information; source-check consequential values regardless of mode.\n\nField grouping, repetition, image handling and retries can affect the number of calls and resource use. Compare observed accuracy, unresolved values, time and usage on the same representative examples. Avoid promising a fixed cost ratio or choosing the most elaborate configuration without evidence.\n\n**Practice:** Two configurations return the same budget. Both selected the annual amount when the task requires the total project amount. Explain why changing the number of passes alone does not resolve the field-definition error.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "Both extraction modes return the wrong annual budget. What should you check first?",
          "options": [
            {
              "text": "Use more passes until the answers agree.",
              "correct": false,
              "explanation": "Agreement can preserve the same misunderstanding. Check the task and source before adding calls."
            },
            {
              "text": "Clarify the requested budget scope, then rerun and compare the result with the source.",
              "correct": true,
              "explanation": "The field definition must identify the intended amount. A new result needs its own source check."
            },
            {
              "text": "Accept the two-pass answer because refinement guarantees correctness.",
              "correct": false,
              "explanation": "Refinement can fail or repeat an error; the returned value still needs evidence."
            }
          ]
        },
      },
      {
        id: 'extraction_engine.configuring-fields-for-accuracy',
        revision: 2,
        title: 'Configuring fields for accuracy',
        objective: 'After this lesson, you\'ll be able to configure extraction fields that minimize hallucinations and missed values.',
        content: "A field needs a meaning that a reviewer can check. “Budget” could mean annual direct costs, total direct costs or total project costs including indirect costs. Name the intended amount, period and unit. “PI Name” distinguishes the investigator from a grants officer named elsewhere in the proposal.\n\nAllowed values constrain a category to an authored set. They help control output shape; they do not prove that the selected label matches the source. A model can choose an allowed but incorrect value. Inspect the underlying statement as well as the returned label, and check behavior on the actual configured route.\n\nOptionality describes whether the task permits a value to be absent. It is not a guarantee against invented answers. Conversely, a required field can still be missing or unsupported in the source. Keep that absence visible as a problem to resolve; do not force a plausible value merely to fill every cell. The structured extraction schema can represent null values, so a well-formed response can still be incomplete.\n\nFor a Yes/No question, missing evidence is not automatically No. Decide what counts as support for each category and how an absent statement will be represented. If the task permits an explicit unknown category, define its meaning. Otherwise preserve the unresolved value and explain the gap rather than silently changing the required categories.\n\n### What chat creates and what you inspect in the editor\n\nThe current document-based creation tool reads the selected source and discovers candidate field names before its confirmation preview. It can create a reusable template from that discovered proposal. This route does not accept your full field-by-field Optional and Allowed values configuration as an authored schema. Asking for those settings in prose is not proof they were stored. Review the proposed source, name and fields, then inspect the saved template.\n\nIn the extraction editor, open the field’s settings to edit its meaning and inspect **Optional** and **Allowed values**. Use that supported route to correct an ambiguous field, set the permitted absence behavior and define category choices. Reopen or reread the saved field after editing to establish what will actually run. Do not increase the field count to compensate for a missing setting.\n\nFor example, define “Full project requested amount, USD, including indirect costs” rather than “Budget,” and check which source amount answers it. For an animal-use category, use only the task’s permitted categories and keep missing support unresolved. An Optional setting, an allowed category or a syntactically valid value does not establish source truth. Run the saved revision and compare the returned value with the relevant passage; preserve both the earlier result and the checked repair.\n\n**Practice:** Rewrite “Animals” as a question about the assigned proposal’s vertebrate-animal use. Name the source statement that would establish Yes or No, and describe what you would record if neither is supported.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "A required compliance statement is absent. Which response preserves the evidence?",
          "options": [
            {
              "text": "Return No because the document did not say Yes.",
              "correct": false,
              "explanation": "Absence of a statement does not necessarily establish the negative category."
            },
            {
              "text": "Keep the value unresolved and identify the missing source support.",
              "correct": true,
              "explanation": "A required answer still needs evidence. Required does not authorize guessing."
            },
            {
              "text": "Mark the field optional and assume any returned answer is safe.",
              "correct": false,
              "explanation": "Optionality concerns permitted absence; it does not validate the model’s answer."
            }
          ]
        },
      },
      {
        id: 'extraction_engine.build-a-comprehensive-extraction',
        revision: 2,
        title: 'Build a comprehensive extraction',
        content: "Keep the original course's saved challenge requirements: its base asks for an extraction with at least 15 fields. Additional field-count enrichment does not replace source accuracy.\n\n1. Create or expand the assigned extraction to at least 15 relevant fields. Cover the requested sections without adding meaningless fields solely to increase the count.\n2. Use precise field names and extraction instructions to distinguish budget categories, periods and personnel roles. Arrange related fields together for readability; order alone does not guarantee a particular runtime grouping.\n3. For a genuinely categorical field, open its settings and enter the supported categories in **Allowed values**. Commit the edit and inspect the saved setting. A permitted category is not proof that the source supports the returned answer.\n4. Use **Optional** when absence is legitimate under the field's meaning. This setting affects validation treatment; it cannot prove an unresolved value is absent from the document. Multiple possible people do not by themselves make a personnel field optional.\n5. Run on the assigned readable source and inspect each relevant result and supporting passage. Preserve missing or ambiguous values explicitly.\n6. Repair the specific field definition or source problem, save the change and run again. Compare the new output with both the original failure and source before claiming improvement.",
        variant: 'walkthrough',
      },
      {
        id: 'extraction_engine.when-to-use-consensus-repetition',
        revision: 2,
        title: 'When to use consensus repetition',
        content: "Repetition compares multiple attempts at the same extraction. In the current engine, consensus starts with two attempts. If their normalized answers agree, it can return that result without a third attempt. A disagreement can trigger another attempt and field-level voting. Failure handling can also affect how many usable attempts remain.\n\nThis is not a promise of exactly three calls or a fixed three-times cost. Each attempt can itself use multiple passes and field groups. Inspect the effective configuration and observed usage when deciding whether the additional work is justified.\n\nAgreement is a signal about consistency, not independent confirmation of the source. Repeated attempts can share the same ambiguous instruction, miss the same paragraph or choose the same unsupported value. A voted answer still needs comparison with the document. For a consequential amount or compliance category, identify the supporting passage and resolve any conflict before accepting it.\n\nStart by fixing the source and field definition. Then compare repetition with a simpler configuration on representative examples, including missing information and conflicting amounts. Record which errors improved, which remained and what the extra work cost. Retain the option to leave a result unresolved rather than treating consensus as permission to release it.\n\n**Practice:** Two attempts agree on a plausible date that appears nowhere in the assigned source. Decide what evidence would be needed before accepting it.",
        variant: 'insight',
      },
      {
        id: 'extraction_engine.worked-example-fixing-a-weak-field-list',
        revision: 2,
        title: 'Worked example: fixing a weak field list',
        content: "Consider a practice case where “Budget” returns Year 1 direct costs, while the task requires the total for the full project including indirect costs. First inspect the source and establish what the returned amount actually represents. Do not treat a neat number or a matching currency symbol as proof of the requested meaning.\n\nRepair the definition to state the period and included cost categories. If the source does not explicitly provide the required total, do not describe an inferred sum as an extracted quotation. Record that limitation and use a separately checked calculation only when the task permits it. Keep the original field revision and result so the reason for the change remains visible.\n\nSave the revised extraction, inspect it, and run that revision on the same assigned source. Compare the new amount, unit and period with the source. Check the other required fields as well; a narrow repair does not establish that the rest of the output remains correct. Record remaining disagreements or missing values explicitly.\n\nThe useful evidence is the error you identified, the actual saved change, the linked new run and your source-based acceptance or further-repair decision. A setting change, an increased field count or a claim that quality improved is insufficient without that comparison. Do not invent a successful result for an illustrative repair.\n\n**Practice:** A new field returns a different budget after your edit. Describe the check that distinguishes a genuine correction from merely a different answer.",
        variant: 'walkthrough',
      },
      {
        id: 'extraction_engine.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "**Structured output:** A response constrained to an expected shape or set of categories. It can still contain null, incomplete or incorrect values. Validate meaning against the source after checking shape.\n\n**Reasoning settings:** Model and pass configuration that can affect how an extraction is attempted. Effective behavior depends on the selected model and route. Do not treat a thinking label as an accuracy score or as evidence that a person reviewed the output.\n\n**Field grouping:** The extraction engine can divide requested keys into groups when its chunking setting is enabled with a positive group size. It is not automatically triggered by every long field list, and it is different from splitting document text into retrieval chunks. Inspect the active setting and test interactions between related fields.\n\n**Consensus:** Comparison and voting across repeated attempts. Agreement does not replace source support. Observe actual call and usage behavior instead of assuming a fixed number of attempts.\n\n**Source reference:** A passage or location associated with a value. Check both that the passage belongs to the assigned source and that it supports the exact value and interpretation. The presence of a citation is not enough.\n\n**Verified test case:** In the chat verification flow, proposing a test case runs an extraction and opens a guided verification session. The test case is created after the learner finalizes that review. Opening a session or an assistant saying “looks right” does not itself establish verified expected values or certification credit.\n\n**Practice:** Explain the difference between an extraction result, a completed verification session and evidence that a certification outcome has been met.",
        variant: 'key-terms',
      },
    ],
    xp: 150,
    icon: 'FlaskConical',
    estimatedMinutes: 20,
  },
  {
    id: 'multi_step',
    number: 5,
    title: 'Multi-Step Workflows',
    subtitle: 'Chain Steps Together',
    description: 'Build a multi-step pipeline using a sample subaward agreement between University of Idaho and Boise State. Extract parties and terms, analyze obligations, then format a compliance summary.',
    objectives: [
      'Add the sample subaward agreement to your workspace',
      'Build a 3-step workflow: Extraction + Prompt + Formatter',
      'Verify the pipeline chains correctly from extraction to formatted report',
    ],
    tips: [
      'The subaward has two parties (UI and BSU), financial terms, deliverables, and compliance requirements',
      'Use the Prompt step to analyze obligations and flag key deadlines',
      'The Formatter step should produce a clean compliance summary from the analysis',
    ],
    lessons: [
      {
        id: 'multi_step.how-steps-chain-together',
        revision: 2,
        title: 'How steps chain together',
        objective: 'After this lesson, you\'ll understand how data flows between steps in a multi-step workflow.',
        diagram: 'workflow-result-example',
        content: "A workflow connects operations, but the diagram alone does not establish their input data. Inspect the saved input-source settings and the outputs of an actual run. A later step cannot safely rely on a clause that was omitted from the material it received.\n\nThe available source choices include Step Input (the immediately preceding output), Workflow Documents and Selected Document. The engine can combine configured sources into labeled sections; it does not automatically combine every earlier result or supply all files in your workspace. A simple chain commonly passes the previous output forward, while the document trigger supplies the workflow documents. Verify the saved choices instead of assuming that every workflow uses those defaults.\n\nInput normally belongs to the step. Tasks within that step receive the step’s payload, with advanced task overrides available for cases that need a different source. Keep those distinctions visible when tracing a design. An operation’s name is not proof of its configured input.\n\nFor each step, identify the source, the requested transformation and the output the next step needs. Then inspect those same boundaries in the saved run. Check document identity as well as the content: a plausible result from an unrelated source does not establish correct chaining.\n\n**Practice:** A deadline-analysis step receives only a terms table, but the reporting exception is in a paragraph omitted from that table. Identify the missing input before running the analysis.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "A deadline step needs a clause absent from its received table. What should you do?",
          "options": [
            {
              "text": "Assume the step can see every document uploaded to the workspace.",
              "correct": false,
              "explanation": "Workspace presence does not establish that the step received the source."
            },
            {
              "text": "Inspect and correct the configured inputs so the required clause is available, then verify the run.",
              "correct": true,
              "explanation": "Data must be supplied through the configured source choices and checked in execution."
            },
            {
              "text": "Rename the step to include the clause title.",
              "correct": false,
              "explanation": "A name does not change the data supplied to the step."
            }
          ]
        },
      },
      {
        id: 'multi_step.the-prompt-node-reasoning-over-data',
        revision: 2,
        title: 'The Prompt node: reasoning over data',
        objective: 'After this lesson, you\'ll know when to use an Extraction task vs. a Prompt task and why the distinction matters.',
        content: "A Prompt step interprets the context supplied to it. It can summarize terms, compare a value with a supplied rule or explain a discrepancy. It cannot establish an institutional policy, missing clause or authorization merely because its instruction asks for a confident answer.\n\nDescribe the task, relevant inputs, expected output and limits. For the subaward exercise, request an obligation list with the responsible party, triggering condition, deadline wording and supporting passage. Require uncertain dates or ambiguous responsibility to remain unresolved. If an exact date must be calculated, supply the applicable rule and starting event and check that calculation separately.\n\nA useful instruction distinguishes source statements from interpretations. For example: “Use only the supplied agreement and reference rule. Quote the term supporting each obligation. Label an inference, identify missing information, and do not invent our institution’s standard policy.” A citation must still be checked for both source identity and actual support.\n\nA Prompt can receive document context directly when that suits the task. Extraction is useful when defined fields preserve what the interpretation needs, but it is not mandatory before every prompt. Choose the route that keeps necessary context reviewable, and test a case where omitted context would change the answer.\n\n**Practice:** Replace “tell me if this agreement complies” with a bounded question and the exact evidence needed to answer it.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "The agreement states quarterly reporting but supplies no institutional comparison policy. What should the analysis say?",
          "options": [
            {
              "text": "Quarterly reporting is stricter than the institution’s normal schedule.",
              "correct": false,
              "explanation": "That comparison requires a supplied policy or other authorized reference."
            },
            {
              "text": "Report the supported obligation and identify that the comparison policy is missing.",
              "correct": true,
              "explanation": "The step can distinguish a source fact from a comparison it cannot establish."
            },
            {
              "text": "Choose a likely institutional standard from general knowledge.",
              "correct": false,
              "explanation": "A plausible policy is not evidence for this task."
            }
          ]
        },
      },
      {
        id: 'multi_step.build-a-3-step-analysis-workflow',
        revision: 2,
        title: 'Build a 3-step analysis workflow',
        content: "Build the original course's three-step workflow on its assigned subaward document. Keep its saved challenge and optional star requirements; the guidance below does not change them.\n\n1. Add three steps to a new workflow. For the first, choose **Extractions**, then select an extraction template with relevant parties, terms and amounts.\n2. For the second, choose **Prompts** and write bounded instructions to analyze those extracted facts. Require explicit uncertainty for obligations or deadlines the source does not establish.\n3. For the third, choose **Format** and write the desired report template. This is the Formatter operation named in the original course.\n4. Inspect each step's input settings and any task override. Connect the second step to the intended first-step result and the third to the intended analysis. Do not assume a step can recover source context that was omitted earlier.\n5. Select the assigned document, confirm the complete input scope and run the saved workflow.\n6. Review the recorded intermediate and final outputs against the source. Check that formatting preserves qualifications and does not turn an unresolved obligation into a confident instruction.",
        variant: 'walkthrough',
      },
      {
        id: 'multi_step.design-principle-separate-reading-from-reasoning',
        revision: 2,
        title: 'Design principle: separate reading from reasoning',
        content: "Separating source reading, interpretation and presentation can make an error easier to locate. It does not guarantee a better answer than a simpler route. Each extra boundary can lose context, change meaning or add resource use.\n\nUse a separate extraction when fixed fields are useful and preserve the evidence needed downstream. A short or context-dependent task may be better served by a focused Prompt over the relevant document. The important question is whether the chosen design makes its inputs, assumptions and results inspectable. Do not add steps only to match a diagram from another use case.\n\nDecide where a substantive check belongs. An intermediate table might need source verification before it becomes the basis for analysis. A recommendation might need a reviewer decision before an external action. A lesson telling you to inspect the table is not an implemented runtime pause; configure and test an approval boundary when continued execution must wait.\n\nCompare designs using representative cases, including missing context and conflicting terms. Record observed differences in accuracy, unresolved issues and resource use. If a simple route preserves the required evidence and meets the task, extra stages need a specific justification.\n\n**Practice:** Name one boundary that would help diagnose an error in your subaward task and one extra step that would add no useful check.",
        variant: 'insight',
      },
      {
        id: 'multi_step.worked-example-watching-data-flow-through-three-steps',
        revision: 2,
        title: 'Worked example: watching data flow through three steps',
        content: "Consider an illustrative subaward chain. The extraction returns parties, project period and the phrase “quarterly reports.” The Prompt then states a precise first-report date and says that the schedule is stricter than the institution’s standard. The Formatter presents both claims in a polished obligations table.\n\nTrace those claims backward. A reporting frequency alone may not establish a deadline without the starting event, due-date convention and applicable exception. The comparison with an institutional standard requires that reference policy. If those inputs were not supplied, the Prompt has gone beyond the available evidence. Formatting the claims does not make them better supported.\n\nRepair the relevant boundary. Preserve the exact reporting clause and any exception, supply an authorized reference rule when comparison is part of the task, and constrain the Prompt to distinguish supported terms from unresolved questions. Do not invent a missing rule just to complete the example. Inspect the saved change and rerun the assigned document.\n\nCompare the new intermediate analysis with the source before inspecting the final summary. Then verify that the Formatter retained the uncertainty and supporting context instead of turning a qualified statement into a definitive date or compliance conclusion. Record your decision to accept, revise or leave the result unresolved.\n\n**Practice:** Write the evidence you would need to establish the first reporting deadline, without calculating or inventing it from the frequency alone.",
        variant: 'walkthrough',
      },
      {
        id: 'multi_step.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "**Input source:** The saved context supplied to a step. Step Input means the immediately preceding output; Workflow Documents rereads the source. Inspect task overrides as well as the step configuration.\n\n**Intermediate output:** A saved result at a workflow boundary. It helps locate an omission or unsupported claim. An intact connection does not establish that the interpretation is correct.\n\n**Prompt and Formatter:** Model transformations of supplied context. Check facts, citations and uncertainty after each transformation, including any post-process prompt. A polished result is not independent source verification.\n\n**Connected execution:** One approved revision, assigned source, intermediate results and final output. A diagram or collection of unrelated runs cannot replace that evidence.\n\n**Recovery:** Inspect the saved run and successful outputs before repeating work. A lost chat reply does not establish that execution failed. Stop or cancellation is not rollback. Do not repeat completed external actions to obtain a cleaner run history.",
        variant: 'key-terms',
      },
    ],
    xp: 150,
    icon: 'Layers',
    estimatedMinutes: 20,
  },
  {
    id: 'advanced_nodes',
    number: 6,
    title: 'Advanced Nodes',
    subtitle: 'Parallel Tasks & Power Nodes',
    description: 'Process a sample budget justification document using an advanced node (the Deep Analysis node) to analyze the figures, plus parallel tasks for concurrent processing.',
    objectives: [
      'Add the sample budget justification to your workspace',
      'Use an advanced node (Deep Analysis, API, or Crawler) to analyze the budget',
      'Run 2+ tasks in parallel within a single step',
    ],
    tips: [
      'The budget has personnel costs, supplies, travel, and subaward line items that should sum to $542,800',
      'Use the Deep Analysis node to analyze the extracted figures and check whether the line items add up. It runs two LLM passes over the data, no URL or API key required',
      'Add a parallel Prompt task alongside the Deep Analysis node to generate a budget narrative',
    ],
    lessons: [
      {
        id: 'advanced_nodes.beyond-extraction-and-prompts',
        revision: 2,
        title: 'Beyond extraction and prompts',
        content: "Choose an operation by what it needs to establish, which inputs it receives and how you will verify its result. A workflow does not become more capable or reliable simply by including a node labeled advanced.\n\nDeep Analysis performs model-based analysis followed by synthesis. It can help organize findings from supplied context, but it is not a deterministic calculator or an independent source verifier. Its current implementation skips analysis when there is no input and can report that it found nothing relevant. Inspect warnings and the actual evidence; do not convert an empty or unsupported analysis into a confident conclusion.\n\nAn API operation communicates with an external service. A crawler or website operation fetches external content. These can be appropriate when the task genuinely needs that source or interaction, but they introduce destination, authorization and result-verification questions. A document-reading exercise does not require an external service merely to demonstrate an advanced node.\n\nTreat credentials as secrets, not teaching evidence. Do not paste API keys, passwords or tokens into chat, task prompts, lesson answers, screenshots or exported memos. Use only an existing authorized connection when an external operation is actually required. If the connection or permission is unavailable, stop that operation rather than borrowing credentials or claiming it succeeded.\n\nYour original course retains its advanced-node and parallel-task requirements. Use an available supported internal operation such as Deep Analysis for the document-based task; it does not require an external API key. Check exact arithmetic separately with an available deterministic or independently checked method. Code Execution is restricted and need not be enabled for this original lab. Follow the requirements displayed for your saved course version.\n\nAdditional document or knowledge-base context can help only when it is relevant, accessible and intentionally supplied. Review the source selection and retained citations. Use the operations available in the current editor and permitted for your account; a chat suggestion does not enable an unavailable capability.\n\n**Practice:** For a budget task, distinguish interpreting an ambiguous cost description from calculating an exact total. Name the evidence and operation each task needs. If an optional API connection is unavailable, explain the supported internal alternative and where its credentials must never be copied.",
        variant: 'concept',
      },
      {
        id: 'advanced_nodes.code-execution-custom-logic-in-your-pipeline',
        revision: 2,
        title: "Check calculations with explicit inputs and rules",
        objective: "Record the formula, units and result instead of accepting model assurance about arithmetic.",
        content: "A calculation needs more than a plausible number. Identify each input, its source, unit, period and meaning. Specify the formula and any rounding or inclusion rule before accepting the result. Adding annual direct costs to a full-project total can produce exact arithmetic with the wrong meaning.\n\nUse an available, permitted deterministic calculation route for the arithmetic, such as a checked calculator or calculation tool. Preserve the inputs, formula and result and verify them against the task. A model can help propose the calculation or explain a discrepancy, but a statement that it “checked the math” is not the calculation evidence itself.\n\nVandalizer’s Code Node is a restricted, administrator-controlled capability and is not offered in the standard palette. This lesson does not require learners to enable it or obtain broader permissions. Where code execution is already authorized, inspect the actual code and permitted inputs and test its behavior. Runtime restrictions and a timeout do not establish that the code is correct or appropriate.\n\nIf the assigned workflow cannot perform the needed calculation through an authorized route, record that limitation and keep the claimed check unresolved. Do not replace the missing calculation with a Deep Analysis opinion or fabricate a successful run. Interpretation and calculation can work together, but their evidence is different.\n\n**Practice:** Write a checkable expression for a total using named source amounts. State how you would handle a missing amount or a conflicting period before computing it.",
        variant: 'concept',
        knowledgeCheck: {"question":"When Code Execution is available and authorized, which task is better handled with deterministic code than a Prompt node?","options":[{"text":"Extracting structured fields from a grant proposal","correct":false,"explanation":"That's what Extraction tasks are for. Code Execution is for logic that requires precision, not pattern recognition."},{"text":"Summarizing a progress report into bullet points","correct":false,"explanation":"Summarization is a Prompt task — it's language work that LLMs do well."},{"text":"Adding up budget line items or computing percentages from extracted numbers","correct":true,"explanation":"Use an explicit calculation rule with checked inputs and inspect the result. A checked calculator or recorded human calculation is a supported alternative when code execution is unavailable."},{"text":"Comparing two documents and identifying differences","correct":false,"explanation":"Document comparison is a Prompt task — it involves language understanding, which is LLM territory."}]},
      },
      {
        id: 'advanced_nodes.running-tasks-in-parallel',
        revision: 2,
        title: 'Running tasks in parallel',
        content: "Tasks within a step can run concurrently. They normally receive the same step input; an explicit task override can select a different source. They do not automatically receive a sibling task’s newly produced answer. Inspect the configuration and combined output rather than assuming a dependency because tasks appear next to one another.\n\nParallel work fits independent operations. For example, a source-based narrative draft and a separate list of unresolved source questions may both use the same document. If the narrative must incorporate a completed calculation, however, it depends on that calculation and belongs after it or after a separate reconciliation step.\n\nThe current engine collects task results in their listed order and combines their outputs for the next step. Output shape can vary with what each task returns. Preserve clear labels and inspect that each downstream value, warning and citation is associated with the intended task. Position alone is a weak substitute for meaning.\n\nConsider effects as well as data. If one task sends or updates something while a sibling fails, the completed external effect may already exist. A failed step is not a guarantee that every sibling’s work was undone. Review what actually happened before retrying an operation with effects.\n\n**Practice:** One task checks a budget and another sends a memo stating the budget passed. Explain the dependency and where an actual approval boundary belongs.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "Can a send task run in parallel with the check whose successful result must authorize the send?",
          "options": [
            {
              "text": "Yes, because tasks in one step exchange their new answers automatically.",
              "correct": false,
              "explanation": "Sibling tasks receive their configured inputs and do not establish that dependency automatically."
            },
            {
              "text": "No; the send must wait for the required result and any applicable approval.",
              "correct": true,
              "explanation": "An action depending on a check needs a verified sequential boundary."
            },
            {
              "text": "Yes, because a sibling failure always undoes external actions.",
              "correct": false,
              "explanation": "A completed external effect may remain after another task fails."
            }
          ]
        },
      },
      {
        id: 'advanced_nodes.build-a-workflow-with-advanced-nodes',
        revision: 2,
        title: 'Build a workflow with advanced nodes',
        content: "1. Create a workflow with at least 3 steps.\n2. In one step, add a **Deep Analysis** task. Ask it to identify cost categories and unresolved source questions, using the document or a previous step's output. Check arithmetic separately with source-linked inputs, units, an explicit formula and a recorded calculator or human result; Deep Analysis is not that check.\n3. In the same step, add a second task (for example a Prompt task that writes a narrative summary) so two tasks run in parallel.\n4. Run the workflow and review how the parallel tasks' outputs are combined. Compare any numerical claim with your recorded calculation. A later memo can claim a checked total only after the calculation and its source inputs have been verified.\n5. (Optional) Swap the Deep Analysis node for an API Call or Crawler node to see other advanced node types.",
        variant: 'walkthrough',
      },
      {
        objective: "Keep interpretation, calculation and downstream acceptance distinct in a worked example.",
        id: 'advanced_nodes.worked-example-a-budget-check-with-parallel-tasks',
        revision: 2,
        title: "Separate a budget check from its narrative",
        content: "Consider an illustrative budget review with two independent drafts. One task identifies the cost categories and unresolved source questions. Another summarizes the stated purpose of the costs. Both use the assigned document. Their parallel placement is appropriate only while neither claims to rely on the other’s new result.\n\nA calculation is a separate evidence step. Use this fully fictional source excerpt for practice; it is not the assessed budget. All amounts are USD for the same one-month equipment purchase:\n\n- Laptop: 1,200.00\n- Monitor: 600.00\n- Accessories: 200.00\n- Printed total: 2,150.00\n\nThe rule is to add the three listed line items, without inventing tax, fees or missing categories. A calculator gives **1,200.00 + 600.00 + 200.00 = 2,000.00 USD**. The printed total exceeds that sum by **150.00 USD**. Preserve the inputs, addition rule, result and discrepancy. The arithmetic establishes a mismatch; it does not tell you whether the source omitted a charge or printed the wrong total. Keep that source question unresolved instead of silently changing a row. Do not substitute these teaching values for the actual assigned budget.\n\nDeep Analysis can first organize findings from the supplied context and then synthesize them into a report. Those are two model passes, not an independent arithmetic check. A second pass repeating 2,150.00 does not override the recorded calculation.\n\nAfter the source inputs and calculation are checked, a later synthesis can compare the checked total with the stated total and explain discrepancies. It should distinguish an arithmetic mismatch from an ambiguous cost category or missing amount. If the calculation is unresolved, the memo must preserve that uncertainty.\n\nInspect the combined output and the final memo. A narrative written before the check cannot honestly say that the check passed merely because it ran alongside the checking task. A release or update depending on the result must wait for that result and any required approval. Keep the original evidence when a repair or rerun is necessary.\n\n**Practice:** Identify the earliest point at which a memo could truthfully include “the checked total matches,” and list the evidence required at that point.",
        variant: 'walkthrough',
      },
      {
        id: 'advanced_nodes.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "Parallel Tasks — You've now run multiple tasks within a single step concurrently. Their results are collected and passed to the next step together. The benefit: independent operations (two extractions, or an extraction + API call) happen simultaneously instead of sequentially.\n\nCode Execution — An available, authorized route for applying an explicit calculation rule to checked inputs. Inspect the code and results. A checked calculator or explicitly recorded human arithmetic is also a valid separate calculation route; do not request elevated permissions merely to study a budget.\n\nAPI Call — Connects your workflow to external services. Supports GET, POST, PUT, and PATCH. You can pass authentication headers and use the previous step's output in the request body — enabling real-time lookups and integrations.\n\nDeep Analysis Node — Two-stage analysis: first passes through the data to identify patterns, then synthesizes findings into a coherent report. These are model passes. They can organize and interpret findings, but cannot replace an independently checked calculation.",
        variant: 'key-terms',
      },
    ],
    xp: 200,
    icon: 'Puzzle',
    estimatedMinutes: 25,
  },
  {
    id: 'output_delivery',
    number: 7,
    title: 'Output & Delivery',
    subtitle: 'Produce Real Deliverables',
    description: 'Process a sample Year-2 progress report and produce downloadable deliverables. Extract accomplishments, publications, and budget data, then export as a report or CSV.',
    objectives: [
      'Add the sample progress report to your workspace',
      'Create a workflow with an output node (Document Renderer, Data Export, etc.)',
      'Run the workflow and download the generated output file',
    ],
    tips: [
      'The progress report has publications, students trained, and budget expenditures to extract',
      'Document Renderer is great for producing a formatted summary report',
      'Data Export with CSV format works well for the budget expenditure data',
    ],
    lessons: [
      {
        id: 'output_delivery.from-analysis-to-deliverables',
        revision: 2,
        title: 'From analysis to deliverables',
        objective: 'After this lesson, you\'ll know which output node to use for different types of deliverables.',
        content: "So far, your workflows produce text output that you view in the app. But real research administration often requires deliverables: compliance reports to submit, data exports for spreadsheets, or document packages with multiple files.\n\nVandalizer's output nodes transform your workflow results into downloadable files:\n\n• **Document Renderer** — Generates a markdown or text file from your workflow output.\n• **Data Export** — Exports structured data as JSON or CSV.\n• **Include in deliverables** — Mark the intended output steps. Multiple included step outputs can be bundled as a ZIP; inspect the actual members and missing outputs. This uses the supported download path and does not require a Package Builder node.\n• **Form Filler** — Takes a template with placeholders and fills it with extracted data.",
        variant: 'concept',
        knowledgeCheck: {
          question: 'You need to export extracted data from 50 proposals into a spreadsheet. Which output node is the right choice?',
          options: [
            { text: 'Document Renderer \u2014 it produces a formatted text file from workflow output', correct: false, explanation: 'Document Renderer creates a readable document, not structured tabular data. It\'s better for reports you\'d read, not data you\'d analyze in Excel.' },
            { text: 'Package Builder \u2014 it bundles multiple files into a ZIP', correct: false, explanation: 'Package Builder is for collecting multiple output files together, not for producing spreadsheet-compatible data.' },
            { text: 'Data Export \u2014 it converts structured data to CSV or JSON', correct: true, explanation: 'Correct! Data Export with CSV format turns your extracted JSON into columns and rows that open directly in Excel or Google Sheets.' },
            { text: 'Form Filler \u2014 it fills placeholders in a template with extracted values', correct: false, explanation: 'Form Filler is for template-based documents (like filling out a standard form), not for exporting tabular data.' },
          ],
        },
      },
      {
        id: 'output_delivery.designing-end-to-end-deliverable-workflows',
        revision: 2,
        title: 'Designing end-to-end deliverable workflows',
        content: "Begin with the intended audience, destination and data scope. An internal working summary, a sponsor submission and a dataset for another system can require different content and authorization. A request to prepare one does not silently authorize all three.\n\nSpecify which source and reviewed result the artifact should represent, which details it should include or exclude, and who is allowed to receive it. Review those choices after inspecting the actual file. A proposed sharing target broader than the assigned destination needs correction before release, even if the analysis is accurate.\n\nA workflow may gather source content, interpret it and generate files, but file generation is not an approval decision. If a later operation sends or updates something, its dependency on review must be implemented and tested. A written instruction to obtain approval is not by itself a pause. For a download-only lab, inspect and retain the file; do not invent an external delivery step.\n\nUse an explicit release decision: accept the exact artifact for the named destination, revise it, or leave it unreleased. Preserve unresolved values and limitations in the artifact when they matter to the recipient. Do not treat an assistant’s message that a file is “ready” as your decision.\n\n**Practice:** The task requests an internal award-file summary, but the proposed next action targets a broad mailing list. Identify the scope change and the decision needed before any send.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "The file is correct, but the proposed destination is broader than the assigned internal handoff. What should happen?",
          "options": [
            {
              "text": "Release it because content correctness implies sharing permission.",
              "correct": false,
              "explanation": "Correct content does not establish authority for a broader audience."
            },
            {
              "text": "Correct the destination and explicitly review the artifact, audience and data scope before release.",
              "correct": true,
              "explanation": "The release decision applies to the exact artifact and intended destination."
            },
            {
              "text": "Let the assistant infer the appropriate recipients.",
              "correct": false,
              "explanation": "The assigned scope and an explicit decision must determine release authority."
            }
          ]
        },
      },
      {
        id: 'output_delivery.build-a-deliverable-workflow',
        revision: 2,
        title: 'Build a deliverable workflow',
        content: "Use the assigned progress report and the deliverable requirements for this course version. The evidence should link the saved workflow revision, source, reviewed result, generated files and your release decision.\n\n1. Define the required sections or data fields and the intended internal destination. Identify unresolved content that must remain visible.\n2. Inspect the saved workflow and its input sources. Supply structured rows to Data Export when a CSV is required and the reviewed text or data to Document Renderer.\n3. Choose an actual supported format and a clear filename. Configure Include in deliverables on the intended output steps; keep intermediate or unintended content out of the handoff.\n4. Run the reviewed revision on the assigned source. Inspect step results and warnings before downloading. A request for one format can still produce a different actual artifact when the input is unsuitable.\n5. Open each downloaded file. Check required content, values, units, source references and layout. For a bundle, inspect every member and confirm that the set is complete without extra unintended material.\n6. If anything is missing, unreadable or inconsistent, repair the relevant input or configuration and generate a new result. Preserve which run produced the inspected version.\n7. Record your decision for the exact files and destination. If the lab includes an authorized delivery action, inspect its receipt or destination state. If it only requires a local download, record that narrower outcome accurately.\n\n**Practice:** Explain the difference between a generated file, an inspected file and a confirmed delivery to the assigned destination.",
        variant: 'walkthrough',
      },
      {
        id: 'output_delivery.worked-example-one-report-in-two-deliverables-out',
        revision: 2,
        title: 'Worked example: one report in, two deliverables out',
        content: "Consider an illustrative progress-report handoff with two outputs: an internal narrative summary and a table of expenditures. The narrative serves a reader; the table serves reconciliation or later processing. Those purposes determine the required content and format.\n\nTrace the input to each output. A narrative paragraph is not automatically a structured expenditure table. If the workflow turns extracted rows into prose and passes only that prose forward, adding a Data Export task afterward does not recover the original rows. Preserve or supply the reviewed tabular data through a supported design and test that the export receives it. Do not assume sibling tasks receive different inputs merely because their output formats differ.\n\nOne concrete design is to extract the required rows, export those rows as CSV, then use a later Prompt explicitly configured to read the assigned Workflow Documents for the narrative. Render that narrative in a following step. The Prompt must not treat the preceding file-download payload as its source text. Inspect the saved source choice, and compare the narrative with the reviewed rows because it reads the document separately.\n\nMark the intended output steps for inclusion in the deliverables. The result-download path can bundle multiple marked step outputs into a ZIP. Package Builder is not offered in the standard palette; do not rely on that unavailable node to prove that the required files exist. Open the actual bundle and inspect its members.\n\nCheck the report and table against the same assigned source and run. Make sure their amounts, periods and uncertainty agree. Do not invent publication counts, progress delays or spending percentages to make the example appear complete. If the source lacks a comparison target, preserve that limitation.\n\n**Practice:** A polished report and a one-cell text export are downloaded together. Explain why the bundle is not yet the required two-deliverable result.",
        variant: 'walkthrough',
      },
      {
        id: 'output_delivery.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "Document Renderer — You've now generated downloadable files from workflow output. Document Renderer takes the previous step's text and wraps it into a file. Best for reports, summaries, and compliance checklists that people will read.\n\nData Export — Converts structured JSON data into CSV or JSON files. When using CSV, each extracted key becomes a column header. Best for data that will be loaded into spreadsheets, databases, or other systems.\n\nMultiple deliverables — Use the supported Include in deliverables setting to select outputs for download. Inspect the actual ZIP members against the intended output steps. A bundle does not prove that every expected file exists, is usable or is authorized for a recipient; no future Package Builder capability is promised here.\n\nForm Filler — Takes a template string with placeholder syntax and produces a filled-in version using your extracted data. Best when the output must follow a fixed format (like a standard institutional form).\n\nInclude in deliverables — A per-step toggle that marks the step's output as part of the downloadable result. Mark multiple steps to bundle their outputs as a ZIP. If no step is marked, the last step is used by default. Use it to control which steps are deliverables vs. intermediate processing steps.",
        variant: 'key-terms',
      },
    ],
    xp: 200,
    icon: 'FileOutput',
    estimatedMinutes: 20,
  },
  {
    id: 'validation_qa',
    number: 8,
    title: 'Validation & QA',
    subtitle: 'Ensure Quality at Scale',
    description: 'Add validation to your NSF proposal workflow from Module 1. Define quality checks that verify your extraction produces correct results, then run validation to measure accuracy.',
    objectives: [
      'Open your workflow from Module 1 (or create a new one for the NSF proposal)',
      'Create a validation plan with 2+ quality checks',
      'Run validation and review the results',
    ],
    tips: [
      'This module reuses the NSF proposal from Module 1 - no new documents needed',
      'Start with checks like "PI Name is not null" and "Total Budget is a valid number"',
      'Use auto-generated validation checks as a starting point, then customize',
    ],
    lessons: [
      {
        id: 'validation_qa.why-validation-matters',
        revision: 2,
        title: 'Why validation matters',
        objective: 'After this lesson, you\'ll understand why validation is essential before deploying a workflow for production use.',
        content: "A workflow can return well-formed output and still extract the wrong amount, omit a qualification or invent a deadline. Validation needs an explicit account of what correct output means for the intended use.\n\nCheck completeness, structure and meaning separately. A nonempty budget field establishes presence. A numeric format establishes shape. Neither establishes that the value is the full project budget rather than one year's request. That requires comparison with the relevant source and the field's definition.\n\nConsistency measures agreement across repeated results. A workflow that returns the same wrong value every time can be highly consistent. Extraction accuracy compares results with saved expected values; those expectations must first be checked against the source. An incorrect expected value can reward an incorrect extraction.\n\nWorkflow checks can use a model evaluator to judge saved output and supplied source context. Treat its explanations as reviewable judgments, not independent proof. Inspect decisive source passages, intermediate results and any unavailable or skipped checks. A technical inability to evaluate is not a demonstrated pass or a learner failure.\n\n**Practice:** A result is valid JSON and repeats the same budget three times. Identify what remains unknown before using that budget.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "A budget value is identical in three runs. What has that established?",
          "options": [
            {
              "text": "The budget is correct.",
              "correct": false,
              "explanation": "Agreement does not establish which source amount the field should contain."
            },
            {
              "text": "The observed runs agree; accuracy still needs a checked expected value and source.",
              "correct": true,
              "explanation": "Repeatability and source accuracy answer different questions."
            },
            {
              "text": "The current result needs no further review.",
              "correct": false,
              "explanation": "Structure and repetition do not prove meaning or suitability."
            }
          ]
        },
      },
      {
        id: 'validation_qa.building-effective-validation-plans',
        revision: 2,
        title: 'Building effective validation plans',
        objective: 'After this lesson, you\'ll be able to design a validation plan that catches the most important failure modes.',
        diagram: 'validation-plan-example',
        content: "Begin with the decisions the workflow supports and the errors that would matter. Turn those risks into specific checks with a stated input, expected behavior and evidence. \"The report looks good\" is too vague; \"the total uses the full project period and preserves the currency\" can expose a concrete error.\n\nUse representative inputs that differ in the ways the workflow will encounter: layout, terminology, length, missing fields and ambiguous values. Include a difficult case, an absent value and an ordinary case. Do not invent a value to fill a missing-field test. State the allowed missing or unresolved behavior explicitly.\n\nFor known-answer cases, verify expected values in the source before saving them. An automatically proposed answer is a draft. Include the relevant passage and interpretation, such as the difference between an annual amount and a total award. A required field can legitimately be unresolved when the source does not establish it; the workflow should expose that limitation.\n\nKeep some representative cases separate from the examples used to tune prompts. After a repair, test those held-out cases as well as the original failure. Repeatedly tuning against the same easy examples can improve their score without improving general use.\n\nA larger test count can improve coverage only if the cases exercise meaningful differences. The scoring system's sample-size adjustment is not a certificate that three cases cover your domain. Plan execution cost and repetitions around the uncertainty you need to investigate.\n\n**Practice:** Design one normal case, one ambiguous-amount case and one missing-value case. Explain the different failure each would detect.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "Which addition most improves a budget extractor test set?",
          "options": [
            {
              "text": "Three copies of the same easy document.",
              "correct": false,
              "explanation": "Duplicate cases add little evidence about different failure modes."
            },
            {
              "text": "Different layouts and an ambiguous annual-versus-total amount, with source-checked expectations.",
              "correct": true,
              "explanation": "Representative differences test the interpretation that matters."
            },
            {
              "text": "The model's latest outputs saved as expected values without review.",
              "correct": false,
              "explanation": "That can turn the same mistake into the supposed correct answer."
            }
          ]
        },
      },
      {
        id: 'validation_qa.set-up-validation-for-your-workflow',
        revision: 2,
        title: 'Set up validation for your workflow',
        content: "1. Open your workflow in the editor and go to the Validate tab.\n2. Add validation inputs — paste sample text or select documents.\n3. Create a validation plan with at least 2 quality checks.\n4. Run validation. The system executes your workflow and grades the results.\n5. Review the results: which checks passed, which failed, and why.\n6. Use improvement suggestions to iterate on your extraction.\n7. Check quality history to see how measured results change over time. Compare the tested inputs and configuration; a change in score does not by itself establish improvement.",
        variant: 'walkthrough',
      },
      {
        id: 'validation_qa.validation-as-a-safety-net',
        revision: 2,
        title: 'Validation as a safety net',
        objective: 'After this lesson, you\'ll understand when to re-run validation and why it should be set up before a workflow goes into production.',
        content: "A saved validation plan describes checks; it does not by itself enforce them on every future execution. A green historical score remains evidence about the measured inputs, saved results and conditions of that validation.\n\nRecheck after changing field meaning, source selection, prompts, workflow structure, extraction strategy or model configuration. A new document family may also require new cases even when the workflow is unchanged. Keep the old failure and run identity so a later improvement can be traced to an actual change.\n\nUse the first failing case to diagnose the problem. Inspect where the wrong value entered the chain and whether the test itself is justified. Do not weaken a correct check merely to restore a green score. If the expected answer was wrong, correct it with source evidence and record why the evaluation changed.\n\nRerun both the original failing case and other representative cases after the repair. Check that downstream reports retain uncertainty and that previously correct fields remain correct. Separate changes to the workflow from changes to the test set when explaining a score difference.\n\nQuality history, age indicators and regression alerts can direct attention to measured changes. Their presence depends on actual validation records and configured monitoring. An absence of alerts does not establish that every current result has been checked. Review the current run before relying on it.\n\n**Practice:** A score rises after two difficult cases are removed. Explain why that alone is not evidence of a better workflow.",
        variant: 'insight',
      },
      {
        id: 'validation_qa.worked-example-five-checks-and-a-failing-run',
        revision: 2,
        title: 'Worked example: five checks and a failing run',
        content: "Illustrative example: a validation plan for an NSF extractor and a failure it could expose.\n\n**The checks:**\n1. PI Name equals “Sarah Chen” (exact expected value — we know this document).\n2. Total Budget equals $485,000.\n3. Project Period contains two dates.\n4. Sponsoring Agency is one of: NSF, NIH, DOE, USDA.\n5. No required field is empty.\n\n**Run 1** — 5/5 pass. The score is recorded in quality history.\n\n**Two weeks later** someone “tidies” the field name “Total Budget” to just “Budget”. **Run 2** — check 2 fails: the extraction returned $178,000, the Year 1 amount. Without validation this silently ships to the tracking sheet; with it, the run is flagged the same day, quality history shows exactly when the score dropped, and the field definition needs investigation followed by a measured rerun.\n\nThe habit to copy: checks 1–2 pin known documents to known answers, 3–4 verify *shape* on any document, 5 catches silent blanks. These checks cover the cases and runs on which they actually execute; they do not guarantee every future result.",
        variant: 'walkthrough',
      },
      {
        id: 'validation_qa.trust-signals-quality-tiers-v5-0',
        revision: 2,
        title: "Read quality signals within their measured scope",
        objective: "Explain a score using its evidence, coverage, age and limitations.",
        content: "A quality badge summarizes stored validation evidence for an item. It is useful for finding evaluated templates and deciding what to inspect next. It does not certify that the answer currently displayed in chat is correct.\n\nA result can be Unscored or have no quality badge when the relevant score is unavailable. That is missing evaluation evidence, not a score of zero, a demonstrated failure or a pass. Check whether the intended artifact and configuration have usable validation records before making a quality claim.\n\nOpen the available quality details and inspect the underlying validation date, measured inputs, test/check count, repeated runs, model/configuration and failed or skipped checks. A score from a different revision or unrepresentative cases has limited relevance to your task. A stale-plan or regression warning needs investigation even if another historical number looks strong.\n\nExtraction scores combine measured accuracy and consistency, with cross-field results included when available. Sample-size adjustments can reduce a score supported by little data. Workflow scores use their own evaluated checks and results. Do not apply one fixed formula to every kind of item, or treat configured tier thresholds as universal guarantees.\n\nAccuracy means agreement with the saved expected values under the implemented comparison. Consistency means agreement among measured outputs. Neither proves that the expected values were independently correct or that untested document types will work. Review how the test set was established.\n\nAdding representative test cases improves coverage, but it can lower the measured score when those cases expose failures. More verification does not promise a higher score. Investigate the new failures and compare like-for-like cases before attributing a score change to a repair.\n\nThe displayed measurement should be traceable to stored validation records. Chat may describe those records or make other claims; compare the actual details rather than assuming the model either knows everything about the score or cannot see any of it. An assistant's assurance is not a substitute for the record.\n\n**Practice:** Explain a high score from a small, old test set to someone considering a new document type. State what the score supports and what still needs testing.",
        variant: 'insight',
      },
      {
        id: 'validation_qa.guided-verification-v5-0',
        revision: 2,
        title: "Verify and finalize useful test cases",
        objective: "Turn a proposed extraction into source-checked expected values without treating guesses as ground truth.",
        content: "Guided verification helps turn an extraction into a reusable test case. The proposal starts a review; it does not make the extracted values correct or save a completed test case by itself.\n\n1. Use the assigned extraction and document. Ask chat to propose a test case, then inspect the opened verification session and its actual source identity.\n2. Review every proposed field against the relevant document passage and the field's meaning. A nearby quote or highlight is a navigation aid, not proof that the value answers the field correctly.\n3. Approve a value only when supported. Correct a wrong value from the source. If you cannot establish an expected value, leave the uncertainty explicit or skip that field rather than guessing.\n4. Resolve all pending fields and finalize the session. Approved and corrected fields become expected values; skipped fields are omitted. Check the saved test case and its included fields.\n5. Run extraction validation with the intended saved cases and inspect the actual results. If fields were skipped, record that coverage gap and use a suitable additional case where the source establishes them.\n6. Investigate patterns of failure in the extraction definition or context. A model suggestion is a proposed repair; save, execute and measure it before claiming improvement.\n\nSaving another checked test case expands the evidence available for validation; it does not by itself improve the extraction or raise its score. A new case can reveal an error the earlier cases missed. Keep that case and diagnose the failure rather than removing it to restore a higher number.\n\nThis review is part of the learner's own source-checking work. It does not require a staff grading queue. Saving a test case or completing formative practice is also separate from demonstrating the module's assessed outcomes.\n\n**Practice:** A session contains four supported values and one unresolved value. Explain what will and will not be tested if the unresolved field is skipped.",
        variant: 'insight',
      },
      {
        id: 'validation_qa.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "**Validation plan:** saved checks that define expected behavior. A plan must match the current workflow and be applied to actual results; saving it does not validate every future run.\n\n**Expected value:** a source-checked answer for a particular case and field. Model-proposed values require review. A skipped or unconfirmed field is not verified ground truth.\n\n**Accuracy and consistency:** agreement with expectations and agreement across repeated outputs. Consistently wrong output remains wrong. Correct shape and nonempty fields are also distinct from correct meaning.\n\n**Representative coverage:** cases that exercise the relevant range of inputs and failures. A fixed number of cases or a high score cannot establish that all important cases are covered. Held-out cases help check whether a repair generalizes beyond the examples used to tune it.\n\n**Validation result and history:** recorded evaluations under particular conditions. Inspect which executions, models, inputs and plan were assessed. A stale plan, unavailable check or old execution limits what the result can establish.\n\n**Repair and regression check:** a documented change followed by new execution and evaluation of both the original failure and other representative cases. Preserve the earlier evidence and explain any test-set changes.\n\n**Practice:** Trace a meaningful failure to its source evidence, describe a repair and identify the retest that would establish whether it worked. Keep earlier results and explain one remaining coverage limitation. This reading exercise does not change the requirements displayed for your saved course.",
        variant: 'key-terms',
      },
    ],
    xp: 250,
    icon: 'ShieldCheck',
    estimatedMinutes: 20,
  },
  {
    id: 'batch_processing',
    number: 9,
    title: 'Batch Processing',
    subtitle: 'Process at Scale',
    description: 'Process three sample NSF proposals in batch mode. Each proposal is from a different PI (Lopez, Kim, Okafor) with different research areas and budgets.',
    objectives: [
      'Add 3 sample batch proposals to your workspace',
      'Run a workflow in batch mode against all 3 documents',
      'Verify all 3 complete successfully with correct PI names',
    ],
    tips: [
      'Use your extraction workflow from Module 1 or 2, or create a new one',
      'The three proposals have PIs: Dr. Maria Lopez, Dr. Robert Kim, Dr. Amara Okafor',
      'Check that all 3 documents complete successfully before marking done',
    ],
    lessons: [
      {
        id: 'batch_processing.single-vs-batch-execution',
        revision: 2,
        title: 'Single vs. batch execution',
        objective: 'After this lesson, you\'ll understand when and how to use batch mode for large-scale document processing.',
        content: "Batch mode queues a separate workflow execution for each selected document. Each execution has its own result and session identity, and the related results share a batch identity. Workers process queued jobs according to available capacity; do not assume documents finish sequentially or in selection order.\n\nBefore starting, record the intended document identities and inspect the workflow and source scope. Three results do not establish coverage of three assigned documents if one input was repeated and another omitted. A matching title is also weaker evidence than the identity of the actual input.\n\nAfter execution, reconcile the selected input list with the per-document results. Account for completed, failed, canceled and still-running items. The current aggregate status can be \"completed\" when all items are terminal even though some failed. Read the item inventory and counts together.\n\nA completed execution means processing reached its completion state; it does not establish that its values are correct or that the output is usable. Inspect required fields and relevant source evidence for each assigned certification document. Preserve missing or ambiguous values explicitly.\n\nBatch mode also does not automatically combine every result into one correct dataset or guarantee that a validation plan was applied. Inspect the actual exported files and validation evidence separately.\n\n**Practice:** A batch shows three terminal results, but two belong to the same source. Explain why the assigned three-document task is incomplete.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "A batch has three completed result rows. What establishes assigned coverage?",
          "options": [
            {
              "text": "The number three alone.",
              "correct": false,
              "explanation": "Counts can hide repeated inputs or missing assigned documents."
            },
            {
              "text": "Each distinct assigned input is linked to its actual per-document result in the intended batch.",
              "correct": true,
              "explanation": "Coverage depends on identities and results, not just counts."
            },
            {
              "text": "The assistant says the batch looks complete.",
              "correct": false,
              "explanation": "A summary cannot replace the input/result inventory."
            }
          ]
        },
      },
      {
        id: 'batch_processing.monitoring-and-debugging-batch-runs',
        revision: 2,
        title: 'Monitoring and debugging batch runs',
        content: "Start with the per-document inventory, then investigate exceptions. A failure may come from unreadable source text, an unavailable model, workflow configuration or an external service. Empty values in an otherwise completed result can also be a substantive quality problem.\n\nOpen the failed item's result and inspect the error, intermediate outputs and actual source text. A scanned PDF may need a usable text source or an appropriate ingestion repair. Uploading the same unreadable bytes again does not guarantee better text. Verify the repaired input before paying for another execution.\n\nKeep successful items and their outputs intact. For an identified recoverable failure, select only the intended item for a new run and preserve the link to the original failure, changed input or workflow and new result. Do not report the original failed run as though it succeeded.\n\nAn uncertain response is different from a confirmed failed action. Check existing run status before launching a duplicate. If a workflow sends or updates anything externally, a later failure or stop request does not prove the earlier action was undone. Establish its actual status before retrying that action.\n\nA batch download includes completed results and can omit failed or unfinished items. Compare the downloaded inventory with the expected inputs and retain an exception list. A usable partial export is still partial coverage.\n\n**Practice:** Two assigned proposals completed and the third has unreadable text. Describe what to preserve, what to repair and which input to select for the next run.",
        variant: 'concept',
        knowledgeCheck: {
          "question": "Two items completed and one failed after an uncertain external response. What comes next?",
          "options": [
            {
              "text": "Rerun all three to obtain a clean batch label.",
              "correct": false,
              "explanation": "That can repeat completed work and duplicate external effects."
            },
            {
              "text": "Preserve completed results, inspect the failed item and external status, then retry only justified work.",
              "correct": true,
              "explanation": "Recovery must account for both input scope and any actions already performed."
            },
            {
              "text": "Treat the failed item as completed because the batch is terminal.",
              "correct": false,
              "explanation": "Terminal status does not establish successful output."
            }
          ]
        },
      },
      {
        id: 'batch_processing.choosing-the-right-model-for-batch-work',
        revision: 2,
        title: 'Choosing the right model for batch work',
        content: "Model choice and workflow design affect cost, latency and output quality. Batch execution multiplies these tradeoffs across documents and repeated model stages. The cheapest or fastest pilot is not sufficient if it misses required fields or confuses source meaning.\n\nUse a small representative pilot before scaling. Include the document layouts and difficult fields that matter, inspect source-supported correctness and record execution time and available usage measurements. An easy single document can expose basic configuration errors but cannot establish reliable behavior across a diverse collection.\n\nInspect the model actually selected for the run and any saved task or step overrides. The workflow default and user default can influence execution when no explicit model is chosen; an override may use a different model for part of the workflow. Keep those settings consistent when comparing pilots, or explain exactly what changed.\n\nUse models and data routes permitted for the task. Check the source scope and destination before processing more documents. A speed or quality claim does not authorize a new provider or wider data access. Select from available configured options rather than assuming chat can enable one.\n\nChoose a batch size that permits useful review and recovery. If a pilot exposes a weak field, repair and retest it before scaling. State the measured tradeoff and remaining uncertainty rather than claiming an unmeasured percentage saving or universal best model.\n\n**Practice:** Compare a fast pilot with a wrong project period against a slower source-correct result. Name the evidence needed to choose or repair the configuration.",
        variant: 'insight',
      },
      {
        id: 'batch_processing.run-your-first-batch',
        revision: 2,
        title: 'Run your first batch',
        content: "Use the original course's three assigned sample proposals. Preserve its three-document requirement and inspect each distinct input and result.\n\n1. Prepare the assigned samples and test the workflow on a representative input before submitting the batch. A single success does not establish reliability across all documents.\n2. Select the three distinct assigned documents in the Library, then open the intended workflow. Check any fixed document or project scope so unrelated sources are not included.\n3. In the workflow's input controls, select **Run per document (3 runs)**. The control appears when more than one document is selected and uses the actual selected count. This is the per-document batch option described by this course.\n4. Click **Run** and retain the batch identity and intended input list. Queued jobs may finish in a different order.\n5. Inspect every item's status and reconcile its document identity with the assigned list. An aggregate **Batch Complete** can include failed items; terminal status alone does not establish accurate results.\n6. Review the returned PI names and other required values against each source. Preserve successful results and unresolved exceptions.\n7. For a failed item, inspect the saved error, repair and verify the input or configuration, then select only the affected document for a justified new run. Check prior effects before retrying. A single selected document uses a normal run; keep its result linked in your evidence to the original batch failure.",
        variant: 'walkthrough',
      },
      {
        id: 'batch_processing.worked-example-thirty-proposals-one-bad-scan',
        revision: 2,
        title: 'Worked example: thirty proposals, one bad scan',
        content: "Consider an illustrative thirty-proposal batch with twenty-nine completed executions and one failed item. The failed source is an image scan whose ingested text does not preserve the needed values. This is a teaching scenario, not a measured production run or a promised success rate.\n\nFirst preserve the twenty-nine results and review the required source-backed values. A completed status does not make them accurate. An export can include those completed outputs, but the inventory should clearly identify the omitted failed proposal and any other unresolved quality issue.\n\nFor the failed source, inspect the actual text available to the workflow. Obtain a suitable readable version or perform an allowed ingestion repair, then confirm the needed content is present. Re-uploading the same poor scan is only an attempted repair until the resulting text is checked. Preserve the relationship between the original and replacement source.\n\nSelect the repaired item alone for a new execution. Link the new result to the original failure and explain what changed. If the workflow had external effects, establish whether any already completed before deciding which action may safely repeat.\n\nIf the recovered output uses the submission date as the project period, that is another substantive failure even if the run completed. Correct the field definition, execute again and use the failure as a representative validation case. A small random spot check cannot establish every assigned output is correct.\n\n**Practice:** Describe the minimum evidence needed to say the omitted proposal has been recovered, and what remains outside that claim.",
        variant: 'walkthrough',
      },
      {
        id: 'batch_processing.glossary-review',
        revision: 2,
        title: 'Glossary & Review',
        content: "**Batch identity:** the link grouping a submitted set of per-document workflow executions. Preserve the intended input list as well as that identity; the label alone does not prove correct scope.\n\n**Per-document result:** the actual execution record for an input. Inspect its status, source identity, intermediate output and required values. Queued jobs need not finish in document order.\n\n**Coverage:** reconciliation of every assigned distinct input with its intended result. Counts, similar titles and repeated input rows cannot substitute for that mapping.\n\n**Terminal status:** an item has finished, failed or been canceled. A terminal batch can contain failures. A completed execution can still contain incorrect or unusable output.\n\n**Representative pilot:** a bounded trial that measures the quality and resource tradeoffs relevant to the larger task. Its usefulness depends on coverage of meaningful variations, not merely being the first document tried.\n\n**Targeted recovery:** a justified new execution for the affected input, linked to the original failure and checked repair. Preserve successful outputs and verify uncertain external actions before repeating them.\n\n**Review task:** Show the assigned input inventory, per-item source checks, unresolved exceptions and any recovery links. Explain the model and scope choice using pilot evidence. Formative practice does not award assessed batch credit.",
        variant: 'key-terms',
      },
    ],
    xp: 250,
    icon: 'Play',
    estimatedMinutes: 25,
  },
  {
    id: 'governance',
    number: 10,
    title: 'Collaboration & Governance',
    subtitle: 'Share and Standardize',
    description: 'Practice collaboration and governance for your Vandal Workflow Architect certification. Demonstrate that you can organize your work, share it with everyone through an examiner\'s check, and read what a shared entry\'s score, consistency and adoption actually tell you. Your VWA credential requires completion of every course module.',
    objectives: [
      'Share a workflow with everyone',
      'Use workflows across personal and team contexts',
      'No new documents needed - uses workflows you have already built',
    ],
    tips: [
      'Switch into a shared team if you want to practice collaboration flows',
      'Export workflows as .vandalizer.json files to share with teammates',
      'Verified workflows signal to your team that a workflow is production-ready',
    ],
    lessons: [
      {
        id: 'governance.organizing-for-reuse',
        revision: 2,
        title: 'Organizing for reuse',
        objective: 'After this lesson, you\'ll understand the three tiers of workflow organization and when to use each.',
        content: "As your team builds more workflows, organization becomes critical. Use personal work for drafting, then move the workflows your team should reuse into shared team libraries, and share the ones the whole institution could use with everyone.\n\nThink about organization in terms of ownership and audience:\n• **Personal work** — early drafts, experiments, and one-off variations.\n• **Team libraries** — shared workflows your group actively maintains.\n• **Everyone** — workflows an examiner has checked over and shared with everyone at your institution, with any available measured quality evidence to inspect. Missing scores are not a pass or a failure.",
        variant: 'concept',
      },
      {
        id: 'governance.sharing-with-everyone',
        revision: 2,
        title: 'Sharing with everyone',
        objective: 'After this lesson, you\'ll know what a "Checked" shared entry does and doesn\'t promise, and how to read one.',
        content: "Sharing with everyone has two halves. You ask to share a workflow; an examiner checks it over and accepts it. A **Checked** badge identifies review status. Inspect the available quality and usage details separately:\n\n1. **Score, when available** — how it did on its measured validation cases, and how many cases that was. Unscored or missing evidence does not establish a pass or a failure.\n2. **Consistency** — whether it gave the same answers across repeated runs.\n3. **Adoption** — how many people already use it.\n4. **When it was last checked** — monitoring re-runs the baseline and flags a drop.\n\nWhat it does *not* claim: that the output format fits your team, or that it is \"production-ready\" for your process. Those are your calls to make from the numbers — which is why the numbers, not the badge, are the point. A workflow at 84% that four colleagues rely on is a good candidate; a perfect score nobody uses tells you less.\n\nSharing is the part you control, and it's what completes this module. Examiner review happens on its own schedule — you'll get a notification when it lands.",
        variant: 'concept',
        knowledgeCheck: {
          question: 'What does a "Checked" shared entry actually tell you?',
          options: [
            { text: 'The workflow is locked and cannot be edited by other team members', correct: false, explanation: 'Checked is not a lock. Anyone can copy a shared item and edit their copy.' },
            { text: 'An examiner looked it over, and its score, consistency and adoption are shown so you can judge fit yourself', correct: true, explanation: 'Correct. Checked means someone looked at it and it was measured, not endorsed for every use. The numbers on the entry are what you decide from.' },
            { text: 'The workflow was created by an admin-level user', correct: false, explanation: 'Any team member can ask to share a workflow with everyone. An examiner looks it over and accepts it based on the workflow\'s quality, not the creator\'s role.' },
            { text: 'The workflow only uses LLM models approved by your institution', correct: false, explanation: 'Model approval is a separate concern. Checked is about the look-over and the measurements, not the model.' },
          ],
        },
      },
      {
        id: 'governance.sharing-workflows-across-teams',
        revision: 2,
        title: 'Sharing workflows across teams',
        content: "A useful handoff includes the saved artifact revision, intended task, owner, supported inputs, dependencies, model assumptions, validation evidence, known limits and required approval or release points. Identify the intended recipient and data scope before actually sharing anything.\n\nWithin an authorized team, confirm who can access and modify the underlying workflow and its source resources. A library bookmark alone is not proof that every dependency is accessible to the intended user. Keep ownership and change responsibility explicit.\n\nA Vandalizer workflow export can carry steps, task settings, prompts and embedded extraction definitions. It can also include text validation inputs and metadata about the exporter. Inspect the exported content before sending it; do not assume that an export contains only harmless structural information.\n\nPortability has limits. A selected document reference may need to be reselected after import, and a knowledge-base task can require a local knowledge base. An export does not automatically transfer all source files, access rights, configured models or a working integration. Read portability warnings and inspect the imported tasks.\n\nImport into an appropriate test context, resolve permitted local dependencies and run representative checks. Keep the original tested revision and the imported/adapted revision distinguishable. The old score is context for review, not proof that the new environment behaves identically.\n\n**Practice:** A colleague imports an extraction workflow but its document reference is empty. Explain the repair and evidence needed before use, without borrowing unrelated source access.",
        variant: 'concept',
      },
      {
        id: 'governance.establish-your-workflow-governance',
        revision: 3,
        title: 'Establish your workflow governance',
        content: "1. Pick a workflow that is ready to share beyond your personal work.\n2. Build or duplicate that workflow into the team context where others should reuse it.\n3. Make sure your workflow has a clear description.\n4. Inspect the available validation results from Module 8 and resolve relevant failures before sharing. The shared entry may have limited or missing quality evidence; a review badge does not certify a future result.\n5. Share the workflow with everyone (⋯ → Share with everyone). Then use the course check and completion actions to record the result under your saved requirements. A sharing request alone is not a completion receipt. Examiner review is separate, and certification does not wait for that review.\n6. If you export and import the workflow, inspect the exported content and portability warnings. Resolve authorized local dependencies and test the imported revision.\n7. Record what was actually submitted, which revision was tested and what remains unresolved. Successful import alone does not establish portability or readiness for wider use.",
        variant: 'walkthrough',
      },
      {
        id: 'governance.building-a-culture-of-reuse',
        revision: 2,
        title: 'Building a culture of reuse',
        content: "Reuse starts with a saved artifact whose intended use, source requirements and limitations are clear. Inspect its measured evidence and test an adapted revision before relying on it for a new task.\n\nThis module addresses governance and handoff. Completing it alone does not establish every skill in the course or issue the Vandal Workflow Architect credential. Your saved course progress must satisfy every required module under its own course rules, and the issued certificate records actual completion. Reading this closing lesson is not a completion receipt.\n\nA credential records the course requirements you demonstrated. It does not guarantee future answers, cover every document-heavy process or grant institutional approval authority. Keep source checking, relevant validation and authorized release decisions part of ongoing work.",
        variant: 'insight',
        knowledgeCheck: {
          question: 'Your workflow passes its validation plan from Module 8. A colleague asks whether that makes it "Checked". What\'s the difference?',
          options: [
            { text: 'They are the same thing \u2014 passing validation makes a workflow Checked', correct: false, explanation: 'Validation is a test you run on your own workflow. Checked only appears after you share it with everyone and an examiner accepts it.' },
            { text: 'Validation is your own test: its cases and the score it gets on them. Checked means you shared it with everyone and an examiner accepted it, and the shared entry shows that score to others', correct: true, explanation: 'Correct. Validation measures the workflow; Checked is what a shared entry carries once an examiner has looked it over. The score on a Checked entry comes from the validation cases.' },
            { text: 'Checked replaces validation \u2014 once an examiner accepts the workflow, its validation cases no longer matter', correct: false, explanation: 'The cases are where the score on a Checked entry comes from, and monitoring re-runs them to flag a drop. Checked does not retire them.' },
            { text: 'Checked means an examiner certified the workflow as production-ready for every team', correct: false, explanation: 'Checked makes no production-ready claim. It says the workflow was looked over and measured; whether it fits your process is your call, from the numbers.' },
          ],
        },
      },
      {
        id: 'governance.worked-example-one-workflow-two-offices',
        revision: 2,
        title: 'Worked example: one workflow, two offices',
        content: "The pre-award office builds “Subaward Intake” and it works well. The post-award office hears about it. What happens next decides whether this becomes shared infrastructure or a rumor.\n\n**Without governance** — someone emails a description, post-award rebuilds it from memory as “subaward_test_v2_FINAL”, the two copies drift, and six months later nobody knows which extracts the right indirect-cost field.\n\n**With the practices from this module** —\n1. The workflow is named to say what it does: “Subaward Intake — Terms & Deviations”, with a description naming its expected input.\n2. It’s shared to the team library — one copy, visible to both offices.\n3. It’s shared with everyone, and an examiner looks it over against a real agreement and accepts it — colleagues can inspect its available validation and usage evidence. Any missing measurement remains unknown.\n4. Post-award improves the deviation prompt — in the shared copy, so pre-award benefits the same day.\n\nThe rule of thumb it illustrates: share the workflow, not a description of it — and use the shared entry’s measured evidence, revision and intended scope to decide which copy to evaluate for your task. Adoption or a score alone cannot establish suitability.",
        variant: 'walkthrough',
      },
      {
        id: 'governance.glossary-review',
        revision: 3,
        title: 'Glossary & Review',
        content: "Personal work — Workflows and resources that only you can see and edit. The right place for experiments, drafts, and one-off variations. Graduate your best work to the team context when it's ready to share.\n\nValidation — Your own test of a workflow (Module 8): cases with expected answers, and the score it gets on them. It measures the workflow; on its own it doesn't make anything Checked.\n\nChecked — The badge on a shared entry. You've now asked to share a workflow with everyone; examiner acceptance records a review decision. Inspect any available score, test count, consistency and usage separately. Missing quality evidence is unknown, and neither review status nor a strong earlier score proves the current answer. The recorded review and any available measured validation remain separate evidence. Neither establishes that the item fits every team's process.\n\nExport (.vandalizer.json) — A portable file containing your workflow's complete definition: steps, tasks, field configurations, prompts. Supported import can require local source references, knowledge bases, models and other dependencies to be resolved. Inspect the export contents and portability warnings, then test the imported copy before relying on it.\n\nTeam — A group of users who share access to team workflows, libraries, and folders. Members have roles: owner, admin, or member. Shared workflows your team adopts become the standards you build on.",
        variant: 'key-terms',
      },
    ],
    xp: 300,
    icon: 'FolderGit2',
    estimatedMinutes: 15,
  },
]

// ---------------------------------------------------------------------------
