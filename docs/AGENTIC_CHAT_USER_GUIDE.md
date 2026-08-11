# Agentic Chat — User Guide

*For research administrators and anyone new to Vandalizer 5.0.*

This guide walks through everything the chat can do for you. If you've used ChatGPT or Copilot, the interface will feel familiar — the difference is what the chat is allowed to do on your behalf, and how transparent it is about doing it.

---

## What makes this chat different

Vandalizer's agentic chat is built on the same conversational interface you already know, with three things generic AI chat can't give you:

1. **Validated answers.** Every extraction and workflow the chat runs comes with a quality score, accuracy %, and the number of test cases behind it. The agent can't see that number, so it can't talk it up — the badge comes straight from your stored validation runs.
2. **Cited sources.** Knowledge-base answers show the exact passages used. Click any passage to jump to the source document.
3. **Confirmation on writes.** Creating knowledge bases, running workflows, building automations, or promoting results into validated templates always previews first, then waits for your approval.

You can still ask the chat free-form questions. The difference shows up when the answer matters.

**You never have to use chat.** Every editor — workflows, extractions, knowledge bases, automations — is still there and still the precision surface. Chat is a faster way in, not a replacement.

---

## What you can ask the chat to do

The chat has 49 tools at its disposal. You don't need to know the tool names — describing what you want is enough.

### Finding things

| Ask… | The agent will… |
|---|---|
| *"What documents do I have about NSF proposals?"* | Search your workspace by title, or by content when a title search comes up empty |
| *"Show me the files in the Grants folder."* | List folders and documents |
| *"What knowledge bases are available to my team?"* | Return your accessible KBs with chunk counts and verification status |
| *"What extraction templates exist for NIH proposals?"* | List extraction sets with field counts, domains, and quality tiers |
| *"What workflows can I run?"* | List workflows with step counts and verification badges |

### Reading and summarizing

| Ask… | The agent will… |
|---|---|
| *"Summarize the NIH R01 proposal on my desk."* | Fetch the document text and summarize |
| *"Compare these 8 proposals on budget and scope."* | Analyze them in parallel and return a digest per document, without flooding the conversation with full text |
| *"What does our OSP handbook say about subaward budgets?"* | Query the relevant knowledge base and return cited passages |
| *"Find the deadline in the RFP."* | Search the document and extract the answer |

### Looking things up on the web

| Ask… | The agent will… |
|---|---|
| *"What's the current NIH salary cap?"* | Check your own documents first, then search the web if the answer isn't there — citing the source URL |
| *"Read this page: https://…"* | Fetch the page and answer questions about it |
| *"Add that page to my Funding KB."* | Chunk and index it so you can query it later with citations |

Your institution's own policy always outranks a search result — the agent is instructed to check your material first. If web search isn't available, your administrator hasn't configured a provider yet.

### Extracting structured data

| Ask… | The agent will… |
|---|---|
| *"Extract PI name, budget, and deadline from this proposal."* | Run the right extraction template and return a table with CSV/TSV export |
| *"Build an extraction template from this RFP."* | Read the document, propose fields, and create the template on your confirm |
| *"Run the NIH Compliance extraction on these 5 proposals."* | Execute extraction across a batch, returning a combined table with quality sidebar |
| *"Does this proposal follow our budget rules?"* | Run the template's cross-field rules and report each pass/fail with a reason |

Cross-field rules are *evaluated* from chat but *authored* in the extraction editor's Cross-field Rules section.

### Running and building workflows

| Ask… | The agent will… |
|---|---|
| *"Run the NIH compliance check on this proposal."* | Dispatch the verified workflow, stream step-by-step progress, and show output |
| *"What's the status of the workflow I just ran?"* | Poll and return current step, completion %, approval gates, or final output |
| *"Approve the review step."* | Resume a paused workflow — if you're an assigned reviewer or workflow manager |
| *"Build a workflow that extracts the budget, checks it against policy, then drafts a summary."* | Lay out the steps, preview them, and create a real workflow on your confirm |
| *"Run that on every file added to my Intake folder."* | Create an automation (disabled, so nothing fires before you review it) |

A workflow built in chat starts **unverified**. It's ready to run, but fine-tune it in the visual editor and validate it before relying on it for real decisions.

### Working in projects

| Ask… | The agent will… |
|---|---|
| *"Start a project for the Smith R01."* | Create a goal-scoped workspace — folder, knowledge base, pinned tools, and chat in one place |
| *"What's in this project?"* | List the project's documents |
| *"Run the intake workflow on everything in this project."* | Resolve the file set itself and run the pinned capability across all of it |
| *"Pin the compliance extraction to this project."* | Add a quick-access reference (nothing is moved or copied) |
| *"Mark this project submitted."* | Move it through its lifecycle: draft → active → submitted → awarded → closeout → archived |

Because every file added to a project is auto-indexed, project-wide chat works immediately — **there's no knowledge base to build or maintain.**

### Building knowledge bases

| Ask… | The agent will… |
|---|---|
| *"Create a knowledge base called 'OSP Policy 2026'."* | Preview the KB, then create on confirmation |
| *"Add these 10 handbook PDFs to the OSP KB."* | Chunk and index the documents into ChromaDB (confirmation required) |
| *"Ingest the NIH grants.gov page into the Funding KB."* | Fetch and index a URL (with optional crawl) |

If you'll be feeding documents in over time rather than indexing a fixed corpus, the agent will suggest a **project** instead.

### Building trust in your templates

| Ask… | The agent will… |
|---|---|
| *"List the test cases for my NSF extractor."* | Return the ground-truth set |
| *"Propose a test case from this proposal."* | Run extraction once and open the guided verification modal so you can confirm each value before saving |
| *"Validate the NSF extractor."* | Run extraction repeatedly against test cases, compute unified accuracy/consistency, update the quality tier |
| *"Can this template be more accurate?"* | Run autovalidate — sweeping candidate configs and reporting the winner |
| *"Any optimization suggestions?"* | List pending recommendations across your KBs, templates, and workflows |

Autovalidate **never changes anything until you apply it**, it tells you honestly when a candidate merely ties the baseline, and every apply is snapshotted so it can be reverted.

### Keeping the output

| Ask… | The agent will… |
|---|---|
| *"Save that summary to my Grants folder."* | Write it as a real document — browsable, downloadable, and reusable as workflow input |

### Learning the platform

| Ask… | The agent will… |
|---|---|
| *"What is a knowledge base?"* / *"Why not just use ChatGPT?"* | Explain the product itself |
| *"Start the certification course."* | Run the Vandal Workflow Architect program right in chat — teaching lessons, setting up practice documents, and grading against your real workspace |

Certification progress is shared with the Certification panel in the top nav, so work done in either place counts in both.

---

## What the results look like

Every tool call the agent makes is shown in real time:

- **Spinner + tool label** while the tool runs ("Searching documents for 'budget'", "Running extraction on 5 files"…).
- **Result summary** when it completes ("Found 12 matches", "Extracted 20 fields · 94% accuracy").
- **Rich content block** below the summary when appropriate — an extraction table with CSV/TSV export, a KB passage list with clickable sources, a workflow step tracker, a verification launcher, or a certification card.
- **Quality badge** inline when the result comes from a validated template.

For work that takes several steps, the agent keeps a **live checklist pinned above the conversation** so you can see what's done and what's left.

You can **keep typing while the agent works.** Your messages queue and get picked up in order — no need to wait for a long extraction to finish before adding a follow-up.

If a tool will write (create a KB, run a workflow, build an automation, save a document), the agent previews what it's about to do and **waits for you to confirm** before executing.

---

## Quality badges — what they mean

When a result carries a `QualityBadge`, it summarizes how much you should trust that answer at a glance. See [QUALITY_SIGNALS_EXPLAINED.md](./QUALITY_SIGNALS_EXPLAINED.md) for the full breakdown.

Shortcut version:

- **Excellent** (green, 90+) — Validated with many test cases and high recent accuracy. Safe to act on.
- **Good** (blue, 75–89) — Reliable; review before acting on high-stakes decisions.
- **Fair** (yellow, 50–74) — Use with care; consider adding test cases to raise the tier.
- **Poor** (red, <50) — Needs attention before you rely on it.

Hover the badge to see accuracy, consistency, test-case count, last validation date, and any active alerts.

---

## Troubleshooting

**"The agent didn't use the tool I expected."**
Describe the tool outcome, not the tool name. *"Run my NIH compliance workflow"* works better than *"invoke run_workflow."*

**"The agent asked me to confirm, but I don't see a confirm button."**
Some writes require two steps: a preview response followed by the agent running again once approved. If you see a preview, just reply *"go ahead"* or *"confirm."*

**"The chat fell back to generic mode."**
The agentic agent only activates when you're logged in and have a team context. If you're in a demo without a team, or an admin without team membership, you'll see plain chat. Switch to a team to get tool access back.

**"I don't see a quality badge."**
Not every extraction template has validation runs yet. Ask the agent to *"propose a test case from this document"* to start building ground truth, then *"run validation"* to generate the first score.

**"It says web search isn't available."**
Your administrator hasn't configured a search provider. Reading a URL you paste in directly works either way.

**"It couldn't read a link I sent."**
Login-gated pages (SharePoint, Google Docs, Confluence) return a login screen rather than content, and PDFs and other downloads aren't fetched. Upload those through the Files tab instead so they get OCR'd and indexed.

**"A long conversation seems to have forgotten earlier details."**
Very long conversations get compacted to stay within the model's context. Recent turns are kept verbatim; older read-only results may be dropped and re-fetched on demand. If something important scrolled far back, restate it or save it to a document.

---

## Next steps

- Ask the chat to *"start the certification course"* — Module 1 takes about 10 minutes and tours the agentic chat.
- Read [QUALITY_SIGNALS_EXPLAINED.md](./QUALITY_SIGNALS_EXPLAINED.md) for the full trust-signal explainer.
- Dev/admin teams: see [AGENTIC_CHAT_TOOLS_REFERENCE.md](./AGENTIC_CHAT_TOOLS_REFERENCE.md) for the tool catalog and auth rules, and [DEPLOY.md](../DEPLOY.md#agentic-chat) for configuration.
