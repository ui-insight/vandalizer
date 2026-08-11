# Vandal Workflow Architect Certification

## Name

**Vandal Workflow Architect** — abbreviated as **VWA**. "Architect" signals mastery over design, not just usage, and pairs with the University of Idaho Vandals identity. The certificate itself: **Vandal Workflow Architect Certification**.

> **Note:** this document is the original program design. The curriculum and philosophy below still hold, but the delivery mechanism changed in v5.0 — certification now runs primarily **inside the agentic chat**. The "Interface Presentation" and "Training Format" sections have been updated to match what shipped; the module content that follows is unchanged.

## Interface Presentation

The certification is accessible from two places, sharing **one progress store** (`certification_service`) so work done in either counts in both:

1. **Agentic chat (primary)** — the user asks to *"start the certification course"* and the whole program runs in the conversation. Seven chat tools cover progress, module exercises, lesson delivery, lab provisioning, grading, completion, and reflective self-assessments.
2. **Certification panel** — a floating panel reachable from the top nav, with a progress indicator (e.g., "3/11 modules complete"). Live cert writes from chat refresh the panel and its rail badge.

The chat home surfaces a CTA directly: *"Start the certification course"* for new users, *"Continue certification (n/11)"* for returning ones.

Once earned, the certification shows as a badge on the user's avatar/profile visible to team members, and optionally in the workflow editor header ("Designed by [Name], VWA").

## Training Format

Interactive, guided walkthroughs inside the actual product — not videos, not a separate LMS. Each module follows this pattern:

1. **Lessons, taught one at a time** — the agent delivers each lesson as a card, frames it rather than reciting it, and asks any knowledge-check question before moving on
2. **Lab provisioning** — `provision_certification_lab` uploads the module's practice PDFs into a **Certification Lab** folder in the user's own workspace (reused on repeat calls, so it's safe to re-run). A split view puts the file browser beside the chat. Reflective modules have no documents
3. **Guided task** — the user builds something real. The agent can do the doable parts *with* them, and it still counts, because grading runs against real workspace artifacts
4. **Grading** — `check_certification_module` runs the module's **deterministic validator** over what actually exists (templates, workflows, runs, test cases) and returns each check pass/fail. The model narrates; it never grades. `complete_certification_module` re-runs the validator before awarding XP
5. **Completion unlock** — the next module becomes available

Three reflective modules (`ai_literacy`, `process_mapping`, `workflow_design`) are completed by answering reflection questions in the user's own words rather than by building artifacts. The agent is forbidden from inventing or padding those answers.

Estimated time: ~3-4 hours total across all modules. Users can stop and resume anytime. Progress persists, and the conversation survives editor round trips mid-module.

## Training Modules

### Module 1: Foundations — Documents In, Intelligence Out

- What a workflow is and when to use one vs. ad-hoc chat
- The document pipeline: upload → text extraction → ChromaDB ingestion
- Creating your first workflow with a single Extraction step
- Understanding Extractions and extract keys
- **Exercise:** Build a one-step workflow that extracts 3 fields from a sample grant proposal

### Module 2: The Extraction Engine

- One-pass vs. two-pass extraction strategies and when each shines
- Field configuration: enum values, optional fields, field descriptions
- Structured output vs. JSON fallback — what happens under the hood
- Chunking for large field sets
- Consensus repetition for high-stakes extractions
- **Exercise:** Configure a two-pass extraction with 15+ fields, compare accuracy against one-pass on the same document

### Module 3: Building Multi-Step Workflows

- Adding steps and understanding the DAG execution model
- Chaining outputs: how one step's output becomes the next step's input
- Input source configuration: `step_input` vs. `select_document` vs. `workflow_documents`
- The Prompt node: asking the LLM to reason over extracted data
- The Format node: transforming structured data into readable output
- **Exercise:** Build a 3-step workflow: Extract → Prompt (summarize findings) → Format (create a report)

### Module 4: Parallel Tasks and Advanced Nodes

- Running multiple tasks within a single step (parallel execution)
- Code Execution node: writing safe Python transforms
- API Call node: integrating external data sources
- Add Document / Add Website nodes: enriching workflows with external context
- The Deep Analysis node: two-pass analysis and synthesis
- **Exercise:** Build a workflow that extracts data, enriches it with a web API call, and runs a Python transform to normalize the results

### Module 5: Output and Delivery

- Document Renderer: generating downloadable reports
- Data Export: JSON and CSV output
- Package Builder: creating ZIP archives with multiple outputs
- Form Filler: populating templates with extracted data
- Designing workflows that produce ready-to-submit deliverables
- **Exercise:** Build a workflow that extracts grant metadata and outputs a pre-filled compliance checklist as a downloadable document

### Module 6: Validation and Quality Assurance

- Creating a validation plan for your workflow
- Defining validation inputs (sample documents and expected outputs)
- Running validation and interpreting results (PASS/FAIL/WARN/SKIP)
- Quality history: tracking workflow reliability over time
- Using LLM-generated improvement suggestions
- **Exercise:** Add a validation plan to a previous workflow, run it, identify a failing check, and fix the underlying step

### Module 7: Batch Processing and Operational Patterns

- Single vs. batch execution modes
- Monitoring execution: real-time progress, SSE streaming, polling
- Debugging failed runs: reading step-by-step output
- Testing individual steps before running the full workflow
- Token usage awareness and model selection for cost optimization
- **Exercise:** Run a workflow in batch mode against 5 documents, identify and fix a step that fails on one edge-case document

### Module 8: Collaboration, Spaces, and Workflow Governance

- Organizing workflows within Spaces
- Exporting and importing workflows (`.vandalizer.json`)
- Sharing validated workflows across teams
- Model selection strategy: balancing speed, accuracy, cost, and data privacy
- When to mark a workflow as verified
- **Exercise:** Export a workflow, import it into a different space, adapt it for a new document type, validate, and verify it

## Completion

After completing all 8 modules, the user receives the **Vandal Workflow Architect** badge and a printable certificate with their name and completion date. Advanced features (such as Browser Automation node or batch processing at scale) could optionally be gated behind certification to add practical incentive.
