# Vandal Workflow Architect Certification

## Name

**Vandal Workflow Architect** — abbreviated as **VWA**. "Architect" signals mastery over design, not just usage, and pairs with the University of Idaho Vandals identity. The certificate itself: **Vandal Workflow Architect Certification**.

## Interface Presentation

The certification should be accessible from two places:

1. **User profile dropdown** — a menu item like "Workflow Certification" with a progress indicator (e.g., "3/8 modules complete")
2. **Workflows page** — a subtle banner or card at the top for uncertified users: *"Become a Vandal Workflow Architect — learn to build production-grade extraction workflows."* Dismissible, but returns as a small badge-link in the sidebar.

Once earned, the certification shows as a badge on the user's avatar/profile visible to team members, and optionally in the workflow editor header ("Designed by [Name], VWA").

## Training Format

Interactive, guided walkthroughs inside the actual product — not videos, not a separate LMS. Each module follows this pattern:

1. **Brief concept explanation** (2-3 paragraphs, inline)
2. **Guided task** — the user builds something real in a sandbox space pre-loaded with sample documents
3. **Knowledge check** — a short quiz or "fix this broken workflow" challenge
4. **Completion unlock** — the next module becomes available

Estimated time: ~3-4 hours total across all modules. Users can stop and resume anytime. Progress persists.

## Training Modules

### Module 1: Foundations — Documents In, Intelligence Out

- What a workflow is and when to use one vs. ad-hoc chat
- The document pipeline: upload → text extraction → ChromaDB ingestion
- Creating your first workflow with a single Extraction step
- Understanding SearchSets and extract keys
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
- The Research node: two-pass analysis and synthesis
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
