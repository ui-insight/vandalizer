# Agentic Chat — User Guide

*For research administrators and anyone new to Vandalizer 5.0.*

This guide walks through everything the chat can do for you. If you've used ChatGPT or Copilot, the interface will feel familiar — the difference is what the chat is allowed to do on your behalf, and how transparent it is about doing it.

---

## What makes this chat different

Vandalizer's agentic chat is built on the same conversational interface you already know, with three things generic AI chat can't give you:

1. **Validated answers.** Every extraction and workflow the chat runs comes with a quality score, accuracy %, and the number of test cases behind it.
2. **Cited sources.** Knowledge-base answers show the exact passages used. Click any passage to jump to the source document.
3. **Confirmation on writes.** Creating knowledge bases, running workflows, or promoting results into validated templates always previews first, then waits for your approval.

You can still ask the chat free-form questions. The difference shows up when the answer matters.

---

## What you can ask the chat to do

The chat has 19 tools at its disposal. You don't need to know the tool names — describing what you want is enough.

### Finding things

| Ask… | The agent will… |
|---|---|
| *"What documents do I have about NSF proposals?"* | Search your workspace by keyword, folder, or extension |
| *"Show me the files in the Grants folder."* | List folders and documents |
| *"What knowledge bases are available to my team?"* | Return your accessible KBs with chunk counts and verification status |
| *"What extraction templates exist for NIH proposals?"* | List extraction sets with field counts, domains, and quality tiers |
| *"What workflows can I run?"* | List workflows with step counts and verification badges |

### Reading and summarizing

| Ask… | The agent will… |
|---|---|
| *"Summarize the NIH R01 proposal on my desk."* | Fetch the document text and summarize |
| *"What does our OSP handbook say about subaward budgets?"* | Query the relevant knowledge base and return cited passages |
| *"Find the deadline in the RFP."* | Search the document and extract the answer |

### Extracting structured data

| Ask… | The agent will… |
|---|---|
| *"Extract PI name, budget, and deadline from this proposal."* | Run the right extraction template (or propose a new one) and return a table |
| *"Propose an extraction set for NIH R01 proposals."* | Analyze sample documents and suggest fields (creation requires your confirmation) |
| *"Run the NIH Compliance extraction on these 5 proposals."* | Execute extraction across a batch, returning a combined table with quality sidebar |

### Running workflows

| Ask… | The agent will… |
|---|---|
| *"Run the NIH compliance check on this proposal."* | Dispatch the verified workflow, stream step-by-step progress, and show output |
| *"What's the status of the workflow I just ran?"* | Poll and return current step, completion %, any approval gates, or final output |

### Building knowledge bases

| Ask… | The agent will… |
|---|---|
| *"Create a knowledge base called 'OSP Policy 2026'."* | Preview the KB, then create on confirmation |
| *"Add these 10 handbook PDFs to the OSP KB."* | Chunk and index the documents into ChromaDB (confirmation required) |
| *"Ingest the NIH grants.gov page into the Funding KB."* | Fetch and index a URL (with optional crawl) |

### Building trust in your templates

| Ask… | The agent will… |
|---|---|
| *"List the test cases for my NSF extractor."* | Return the ground-truth set |
| *"Propose a test case from this proposal."* | Run extraction once and open the guided verification modal so you can confirm each value before saving |
| *"Validate the NSF extractor."* | Run extraction repeatedly against test cases, compute unified accuracy/consistency score, update the quality tier |

---

## What the results look like

Every tool call the agent makes is shown in real time:

- **Spinner + tool label** while the tool runs ("Searching documents for 'budget'", "Running extraction on 5 files"…).
- **Result summary** when it completes ("Found 12 matches", "Extracted 20 fields · 94% accuracy").
- **Rich content block** below the summary when appropriate — an extraction table with CSV/TSV export, a KB passage list with clickable sources, a workflow step tracker, or a verification launcher.
- **Quality badge** inline when the result comes from a validated template.

If a tool will write (create a KB, run a workflow, build a test case), the agent previews what it's about to do and **waits for you to confirm** before executing.

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
Some writes require two steps: a preview response followed by the agent running again with `confirmed=true`. If you see a preview, just reply *"go ahead"* or *"confirm."*

**"The chat fell back to generic mode."**
The agentic agent only activates when you're logged in and have a team context. If you're in a demo without a team, or an admin without team membership, you'll see plain chat. Switch to a team to get tool access back.

**"I don't see a quality badge."**
Not every extraction template has validation runs yet. Ask the agent to *"propose a test case from this document"* to start building ground truth, then *"run validation"* to generate the first score.

---

## Next steps

- Open the **Certification panel** (top nav) — Module 1 walks through the agentic chat in about 10 minutes.
- Read [QUALITY_SIGNALS_EXPLAINED.md](./QUALITY_SIGNALS_EXPLAINED.md) for the full trust-signal explainer.
- Dev/admin teams: see [AGENTIC_CHAT_TOOLS_REFERENCE.md](./AGENTIC_CHAT_TOOLS_REFERENCE.md) for the tool catalog and auth rules.
