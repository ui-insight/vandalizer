"""Curated topic catalog for the agentic chat's `get_app_help` tool.

The chat agent calls `get_app_help(topic)` when a user asks what Vandalizer is,
how to do something, or what a feature means. Keeping these explanations here
(instead of in the system prompt) means they don't ride along in every chat
request — they're only fetched when the user actually asks.

Each topic is a short, focused markdown chunk. Aliases drive matching so users
can phrase questions naturally ("how do I make a workflow", "what's a
knowledge base", "what does the quality score mean").

To add a topic: append a dict to ``HELP_TOPICS``. Keep the body under ~250
words and write in second person ("you click", "your files"). Source of truth
for UI steps lives in ``docs/AGENTIC_CHAT_USER_GUIDE.md`` and the help system
prompt in ``llm_service.py`` — keep them in sync if features move.
"""

from __future__ import annotations

import re


HELP_TOPICS: list[dict] = [
    {
        "id": "overview",
        "title": "What Vandalizer is",
        "aliases": [
            "what is vandalizer", "what is this", "what does vandalizer do",
            "what is the app", "explain vandalizer", "vandalizer overview",
            "tell me about vandalizer", "intro", "elevator pitch",
        ],
        "body": (
            "Vandalizer is an AI document-intelligence platform built at the "
            "University of Idaho for research administration — grants, "
            "compliance, proposals, and institutional documents.\n\n"
            "**The core idea**: instead of pasting a PDF into ChatGPT and hoping, "
            "you build *validated* extraction templates and workflows. Every "
            "answer the chat returns can carry a quality score, accuracy %, "
            "and the number of test cases behind it — so you know how much to "
            "trust it before you act on it.\n\n"
            "**Chat drives all of it.** You can do these by talking, or in the "
            "dedicated editors — whichever suits the task:\n"
            "- Upload documents and chat with them, grounded in their content\n"
            "- Run extraction templates that pull structured data from PDFs/DOCX/etc.\n"
            "- Build and run multi-step workflows (extract → summarize → compare → merge)\n"
            "- Build knowledge bases over policy docs and ask questions with cited sources\n"
            "- Group a grant's files, tools, and chat into a project with its "
            "own auto-indexed knowledge base\n"
            "- Trigger automations on folder watches, schedules, M365, or API calls\n"
            "- Validate templates against test cases to grow accuracy over time"
        ),
    },
    {
        "id": "trust-vs-generic-ai",
        "title": "Why Vandalizer over plain ChatGPT/Claude",
        "aliases": [
            "vs chatgpt", "vs claude", "vs copilot", "why use vandalizer",
            "why not chatgpt", "what makes vandalizer different",
            "why this instead of", "trust", "validated", "accuracy",
        ],
        "body": (
            "Plain ChatGPT/Claude give you fluent answers with no way to know "
            "if they're right. Vandalizer adds three things:\n\n"
            "1. **Validated answers.** Extraction templates and workflows are "
            "tested against test cases with known correct answers. Each result "
            "carries an accuracy score, a tier (excellent/good/fair/poor), and "
            "the number of test cases behind it.\n"
            "2. **Cited sources.** Knowledge-base answers show the exact "
            "passages used, with click-through to the source document.\n"
            "3. **Confirmation on writes.** Creating knowledge bases, running "
            "workflows, or saving test cases always previews first and waits "
            "for your approval before executing.\n\n"
            "You can still ask free-form questions. The difference shows up "
            "when the answer matters."
        ),
    },
    {
        "id": "agentic-chat",
        "title": "What the agentic chat can do",
        "aliases": [
            "what can the chat do", "agentic chat", "chat tools", "what tools",
            "what can you do", "what are your capabilities", "agent skills",
            "what can the assistant do",
        ],
        "body": (
            "The chat can drive essentially the whole platform — you don't "
            "need to know any tool names. Describe what you want and the agent "
            "picks the right tool.\n\n"
            "**Find and read:**\n"
            '- *"What documents do I have about NSF proposals?"* → searches your workspace\n'
            '- *"Summarize the R01 on my desk."* → fetches and summarizes\n'
            '- *"Compare these 8 proposals on budget and scope."* → analyzes them in parallel\n'
            '- *"What\'s the current NIH salary cap?"* → searches the web when the answer isn\'t in your files\n\n'
            "**Extract and check:**\n"
            '- *"Extract PI name, budget, and deadline from this proposal."* → runs the right template\n'
            '- *"Build an extraction template from this RFP."* → proposes fields, creates on your confirm\n'
            '- *"Does this proposal follow our budget rules?"* → runs cross-field compliance checks\n\n'
            "**Build and run:**\n"
            '- *"Build a workflow that extracts the budget then checks it against policy."* → authors a real multi-step workflow\n'
            '- *"Run the NIH compliance check on these 5 proposals."* → dispatches a workflow and streams progress\n'
            '- *"Run that workflow on every file added to this folder."* → creates an automation\n'
            '- *"Start a project for the Smith R01."* → creates a project with its own auto-indexed knowledge base\n\n'
            "**Improve and keep:**\n"
            '- *"Validate the NSF extractor."* → runs validation across test cases\n'
            '- *"Can this template be more accurate?"* → runs autovalidate and reports the winner\n'
            '- *"Save that summary to my Grants folder."* → writes a real document you can reuse\n'
            '- *"Start the certification course."* → teaches the program right here in chat\n\n'
            "Every tool call shows a spinner with a label, then a result "
            "summary. Quality badges appear inline when the result comes from "
            "a validated template. For multi-step work the agent keeps a live "
            "checklist pinned above the conversation, and you can keep typing "
            "while it works — your messages queue and are picked up in order."
        ),
    },
    {
        "id": "quality-signals",
        "title": "Quality scores and tiers",
        "aliases": [
            "quality score", "quality badge", "what does the score mean",
            "accuracy", "tier", "excellent good fair poor", "trust score",
            "validation score", "how reliable",
        ],
        "body": (
            "Every extraction template and workflow can carry a unified "
            "**quality score** (0–100) and **tier**:\n\n"
            "- **Excellent** (90+, green) — Validated with many test cases and "
            "high recent accuracy. Safe to act on.\n"
            "- **Good** (75–89, blue) — Reliable; review before high-stakes use.\n"
            "- **Fair** (50–74, yellow) — Use with care; add test cases to raise the tier.\n"
            "- **Poor** (<50, red) — Needs attention before you rely on it.\n\n"
            "**Sample-size penalty:** with fewer than 3 test cases, the score "
            "is held back toward 50 — adding two or three more test cases "
            "often unlocks the real number.\n\n"
            "Hover any quality badge to see accuracy, consistency, test-case "
            "count, last validation date, and any active alerts (e.g. *stale* "
            "or *config_changed*)."
        ),
    },
    {
        "id": "validation",
        "title": "Test cases and validation runs",
        "aliases": [
            "test case", "test cases", "validation", "validate", "ground truth",
            "what is validation", "how to validate", "propose test case",
            "verify extraction", "guided verification",
        ],
        "body": (
            "**Test cases** are documents with known-correct answers. They're "
            "the ground truth Vandalizer measures your templates against.\n\n"
            "**The trust loop:**\n"
            "1. Run an extraction on a document\n"
            "2. If the result looks right, ask the chat to *propose a test case* — "
            "the document viewer opens with each value, you confirm or correct, save\n"
            "3. Repeat on a few different documents (3+ recommended)\n"
            "4. Ask the chat to *run validation* — it re-runs the template against "
            "every test case, computes accuracy & consistency, and updates the quality tier\n\n"
            "Validation runs are versioned. If you change the template's fields "
            "or prompts, a *config_changed* alert fires so you know to re-validate."
        ),
    },
    {
        "id": "extraction-templates",
        "title": "Extraction templates",
        "aliases": [
            "extraction template", "extraction set", "search set", "formatter",
            "what is an extraction", "how to extract", "build from document",
            "create extraction", "fields", "schema",
        ],
        "body": (
            "An **extraction template** is a structured schema — a list of "
            "fields with types (text, number, date, boolean, list, enum, etc.) "
            "that tells Vandalizer what to pull from a document.\n\n"
            "**Two ways to create one:**\n"
            "- **Manually**: extraction templates panel → **+ New** → add fields\n"
            "- **Auto-generate**: select a document → **Build from Document** "
            "(in chat, ask *\"build a template from this\"*). The AI proposes "
            "the right fields based on what's in the document.\n\n"
            "**Run it**: ask the chat *\"extract X, Y, Z from this proposal\"* "
            "or open the template and pick documents. Results come back as a "
            "table; export to CSV/TSV with one click."
        ),
    },
    {
        "id": "workflows",
        "title": "Workflows (multi-step automations)",
        "aliases": [
            "workflow", "workflows", "create workflow", "run workflow",
            "multi-step", "chain steps", "what is a workflow", "automation steps",
        ],
        "body": (
            "A **workflow** chains multiple AI tasks into a single repeatable "
            "pipeline.\n\n"
            "**To create one:**\n"
            "1. Click **Automations** in the left sidebar (or go to /workflows)\n"
            "2. **+ New** → name it\n"
            "3. Add **steps**, each a task type:\n"
            "   - **Extract** — run an extraction template\n"
            "   - **Summarize** — produce a concise summary\n"
            "   - **Classify** — categorize into labels you define\n"
            "   - **Translate** — translate to a target language\n"
            "   - **Custom Prompt** — any freeform prompt\n"
            "   - **Compare** — compare two or more documents\n"
            "   - **Merge** — combine outputs from earlier steps\n"
            "4. **Chain** steps using step inputs (output of step 1 → input of step 2)\n"
            "5. **Run** — pick documents, click Run, view results in-app or "
            "export as JSON / CSV / PDF\n\n"
            "Or just ask the chat: *\"run my NIH compliance check on these 5 proposals.\"*"
        ),
    },
    {
        "id": "automations",
        "title": "Automations and triggers",
        "aliases": [
            "automation", "automations", "trigger", "triggers", "folder watch",
            "m365 intake", "api trigger", "schedule workflow", "auto run",
        ],
        "body": (
            "**Automations** are workflows that fire on their own when a "
            "trigger condition is met.\n\n"
            "**Setup:**\n"
            "1. Click **Automations** in the left sidebar → **+ New**\n"
            "2. Pick a **trigger type**:\n"
            "   - **Folder Watch** — new files dropped in a folder kick off the workflow\n"
            "   - **M365 Intake** — pull from a Microsoft 365 source (SharePoint, OneDrive)\n"
            "   - **API Trigger** — fire externally with an HTTP call\n"
            "3. Pick the **workflow** to run when triggered\n"
            "4. Toggle the automation **on**\n\n"
            "Each run shows up in the Activity feed (right rail) with status, "
            "step-by-step progress, and any approval gates."
        ),
    },
    {
        "id": "knowledge-bases",
        "title": "Knowledge bases (RAG)",
        "aliases": [
            "knowledge base", "knowledge bases", "kb", "rag", "what is a kb",
            "create knowledge base", "add documents to kb", "ingest url",
            "policy guide", "search documents semantically",
        ],
        "body": (
            "A **knowledge base** is a vector-indexed collection of documents "
            "or web pages you can query with cited answers.\n\n"
            "**To create one:**\n"
            "1. Click **Knowledge** in the left sidebar → **+ New**\n"
            "2. **Add Documents** (from your files) or **Add URLs** (web pages, "
            "with optional crawl)\n"
            "3. Wait for status to flip from *building* to *ready* (seconds for "
            "small sources, minutes for large ones)\n"
            "4. Click **Chat** on the KB — answers come back with the exact "
            "passages cited, click-through to source\n\n"
            "Or just ask the chat: *\"create a knowledge base called OSP Policy 2026 "
            "from these handbook PDFs.\"* The agent previews first and waits for "
            "your confirm before creating."
        ),
    },
    {
        "id": "files-and-folders",
        "title": "Uploading files and folders",
        "aliases": [
            "upload", "uploading", "upload documents", "upload pdf", "files tab",
            "folder", "team folder", "shared folder", "how to upload",
            "supported formats",
        ],
        "body": (
            "**To upload:**\n"
            "1. Click **Files** in the left sidebar\n"
            "2. Click **Upload** (or drag-and-drop onto the file list)\n"
            "3. Supported: **PDF, DOCX, XLSX, HTML, images** — auto-OCR'd, "
            "text-extracted, and vector-indexed in seconds\n\n"
            "**Folders:**\n"
            "- **Personal folder** — only you see it\n"
            "- **Team folder** — shared with your current team. Create with "
            "**Add → New Team Folder** (shows a teal **Team** badge)\n\n"
            "Once uploaded, select files with checkboxes and switch to **Chat** "
            "to ask questions grounded in their content."
        ),
    },
    {
        "id": "chat-with-documents",
        "title": "Chatting with selected documents",
        "aliases": [
            "chat with documents", "chat with pdf", "chat with files",
            "ground answers in document", "document chat", "ask about my documents",
            "select documents to chat",
        ],
        "body": (
            "**To chat grounded in specific documents:**\n"
            "1. **Files** tab → select one or more documents with checkboxes\n"
            "2. Switch to **Chat** mode — the selected docs appear as context\n"
            "3. Ask your question — answers are grounded in those documents\n\n"
            "If your question reaches beyond the loaded docs (e.g. asks about "
            "a policy that lives in a knowledge base), the agent will use its "
            "tools to search the broader workspace.\n\n"
            "Long documents are chunked and retrieved with vector search, so "
            "you can chat with hundred-page PDFs without losing context."
        ),
    },
    {
        "id": "library",
        "title": "Library — saving prompts and pinning",
        "aliases": [
            "library", "save prompt", "reusable prompt", "pin", "pinning",
            "favorite", "favoriting", "quick access", "library item",
        ],
        "body": (
            "The **Library** holds reusable prompts, extraction templates, "
            "workflows, and knowledge bases — anything you'd want one click "
            "away.\n\n"
            "**To save a prompt:**\n"
            "1. In the chat input, click the **Library** icon → **+ New**\n"
            "2. Write the prompt text and save\n\n"
            "**Pin** a library item to the quick-access bar so it's always "
            "one click away.\n"
            "**Favorite** an item as a personal bookmark — favorited items "
            "show up in your favorites filter."
        ),
    },
    {
        "id": "teams",
        "title": "Teams, roles, and inviting members",
        "aliases": [
            "team", "teams", "invite", "invite teammate", "invite member",
            "team roles", "owner admin member", "switch team", "manage teams",
            "current team",
        ],
        "body": (
            "Vandalizer is multi-tenant: documents, workflows, and folders "
            "are scoped to a **team** (or your personal workspace).\n\n"
            "**To invite:**\n"
            "1. Click your name in the **top-right dropdown**\n"
            "2. **Manage teams** (or go to /teams)\n"
            "3. Pick a team (or create one) → **Invite** → enter email\n\n"
            "**Roles:**\n"
            "- **Owner** — full control, including deleting the team\n"
            "- **Admin** — manage members and team settings\n"
            "- **Member** — use shared spaces and resources\n\n"
            "Switch the active team in the same top-right dropdown — the "
            "interface re-scopes to that team's documents and workflows."
        ),
    },
    {
        "id": "api-tokens",
        "title": "API tokens and programmatic access",
        "aliases": [
            "api", "api token", "api key", "integrate", "programmatic",
            "x-api-key", "external integration", "call from code", "rest api",
        ],
        "body": (
            "**To get an API token:**\n"
            "1. Top-right dropdown → **My Account**\n"
            "2. Generate an **API Token** (shown once — copy it now)\n"
            "3. Use the token with the `x-api-key` header when calling "
            "extraction and workflow endpoints\n\n"
            "Code samples for common languages are shown on the Account page. "
            "Use the **API Trigger** automation type to fire workflows from "
            "external systems."
        ),
    },
    {
        "id": "certification",
        "title": "Vandal Workflow Architect certification",
        "aliases": [
            "certification", "cert", "certified", "badge", "vandal architect",
            "modules", "lessons", "training", "tutorial", "learn vandalizer",
        ],
        "body": (
            "Vandalizer ships with a free **Vandal Workflow Architect** "
            "certification — 11 modules, ~1,600 XP — that walks through the "
            "full agentic stack: AI literacy, validated extraction, multi-step "
            "workflows, trust signals, and governance.\n\n"
            "**To start:** just ask — *\"start the certification course\"* — and "
            "the whole program runs right here in chat. The agent teaches each "
            "lesson, sets up practice documents in a **Certification Lab** "
            "folder, walks you through the challenge, and grades it. You can "
            "also open the **Certification** panel from the top nav; both share "
            "one progress store, so work done in chat counts there and vice versa.\n\n"
            "Modules are hands-on — you complete real work (build a template, "
            "run a validation, ship a workflow) and the system validates your "
            "progress against your actual data, not multiple-choice. The agent "
            "can do the doable parts with you, and it still counts, because "
            "grading runs against what actually exists in your workspace.\n\n"
            "Three reflective modules (AI literacy, process mapping, workflow "
            "design) are completed by answering reflection questions in your "
            "own words instead of building artifacts."
        ),
    },
    {
        "id": "ui-layout",
        "title": "UI layout — where things live",
        "aliases": [
            "ui", "interface", "layout", "sidebar", "navigation", "where is",
            "where do i find", "where to click", "right rail", "top nav",
            "tabs", "modes",
        ],
        "body": (
            "**Left sidebar (Utility Bar)** — four mode tabs:\n"
            "- **Chat** — the agentic assistant\n"
            "- **Files** — upload, browse, organize documents and folders\n"
            "- **Automations** — workflows and triggers\n"
            "- **Knowledge** — knowledge bases\n\n"
            "**Top-right dropdown (your name)** — switch teams, **Manage teams** "
            "(/teams), **My Account** (/account), **Admin** (if you have admin "
            "rights), Sign out.\n\n"
            "**Right rail (Activity feed)** — recent conversations, extractions, "
            "workflow runs. Click any entry to jump back to it."
        ),
    },
    {
        "id": "fetch-url",
        "title": "Reading web pages from chat",
        "aliases": [
            "read url", "fetch url", "open link", "read this link", "read website",
            "summarize webpage", "summarize this page", "check this url",
            "can you read urls", "can you visit websites", "browse",
            "look at this link", "what does this page say",
        ],
        "body": (
            "Drop a public URL into chat and the agent will fetch the page, "
            "extract the readable text, and answer questions about it — "
            "summary, key facts, comparisons against other docs, anything.\n\n"
            "**What works:** public webpages (news, documentation, gov pages, "
            "blog posts, RFPs posted online).\n\n"
            "**What doesn't:**\n"
            "- **Login-gated pages** (SharePoint, Google Docs, Confluence, "
            "internal wikis) — the agent only sees the login screen. Upload "
            "an export, or use an M365 intake automation.\n"
            "- **PDFs and other file downloads** — upload them via the Files "
            "tab instead so they get OCR'd and indexed.\n"
            "- **JavaScript-only pages** — if the content only renders after "
            "running JS, the fetch returns empty text.\n\n"
            "**To save a page** for repeat queries with citations, ask the "
            "chat to *\"add this URL to a knowledge base\"* — that runs the "
            "full ingestion path with chunking and vector indexing."
        ),
    },
    {
        "id": "confirmation-rule",
        "title": "Why writes ask for confirmation",
        "aliases": [
            "confirm", "confirmation", "preview", "needs confirmation",
            "why does it ask", "approve", "go ahead", "two-step",
        ],
        "body": (
            "Anything the chat does that creates, modifies, or runs paid work "
            "previews first and waits for your approval. That covers:\n\n"
            "- Creating knowledge bases\n"
            "- Adding documents or URLs to a KB\n"
            "- Running workflows, and approving or rejecting a paused step\n"
            "- Building new workflows, extraction templates, and automations\n"
            "- Creating projects, pinning tools to them, and changing their status\n"
            "- Saving chat output as a document in your folders\n"
            "- Saving test cases (guided verification)\n"
            "- Starting or applying autovalidate optimization runs\n"
            "- Regenerating a workflow's validation plan\n\n"
            "**You'll see** a preview message describing what's about to "
            "happen — confirm with *\"go ahead\"*, *\"yes\"*, or *\"confirm\"* "
            "and the agent runs it. Cancel with *\"never mind\"* or just ask "
            "for something different.\n\n"
            "This is by design: the agent never silently writes on your behalf."
        ),
    },
    {
        "id": "autovalidate",
        "title": "Autovalidate — automatic quality tuning",
        "aliases": [
            "autovalidate", "optimize", "optimizer", "optimization",
            "tune my kb", "improve accuracy", "make it more accurate",
            "quality tuning", "best config", "optimizer inbox", "quality inbox",
            "shadow run", "apply optimization",
        ],
        "body": (
            "**Autovalidate** finds the best configuration for your knowledge "
            "bases, extraction templates, and workflows by sweeping candidate "
            "configs against their test sets and scoring each one.\n\n"
            "- **Knowledge bases** — proves your KB earns its keep: a quality "
            "score plus a one-click recipe to improve retrieval. Typically "
            "$1–$5 in tokens and 10–20 minutes.\n"
            "- **Extraction templates** — scores the template against test "
            "cases and finds the model/strategy/prompt combination with the "
            "highest accuracy. Typically $1–$5 and 5–15 minutes.\n"
            "- **Workflows** — finds the per-step model and prompt combination "
            "that scores highest on your test inputs. Typically $5–$15 and "
            "15–30 minutes.\n\n"
            "**Nothing changes until you click Apply** (or confirm in chat). "
            "Every run reports the winner against your current config, flags "
            "statistical ties honestly, and snapshots the previous config so "
            "applies can be reverted.\n\n"
            "**Where:** ask the chat to *\"optimize this\"*, use the "
            "Autovalidate panel in each editor, or review system-suggested "
            "candidates in **Library → Quality Inbox** (quality monitoring "
            "auto-tunes items in shadow mode when it detects drift)."
        ),
    },
    {
        "id": "projects",
        "title": "Projects — a workspace per grant or effort",
        "aliases": [
            "project", "projects", "what is a project", "create a project",
            "grant workspace", "chat across all my files",
            "chat with all my documents", "drop files in",
            "project status", "pin to project", "scoped workspace",
        ],
        "body": (
            "A **project** is a goal-scoped workspace for one unit of work — a "
            "grant, a submission, an audit. It bundles a folder, a knowledge "
            "base, pinned tools, and its own chat in one place.\n\n"
            "**Why it beats a plain folder:** every file you add to a project "
            "is automatically indexed into the project's knowledge base. So "
            "project-wide chat — *\"what do all these documents say about "
            "cost share?\"* — works immediately, with **no separate knowledge "
            "base to build or maintain**. Drop files in as they arrive and the "
            "answers stay current.\n\n"
            "**You can:**\n"
            "- Ask the chat to *\"start a project for the Smith R01\"*\n"
            "- Pin the workflows and extraction templates you use on it, then "
            "*\"run the intake workflow on everything in this project\"* — the "
            "agent resolves the file set itself\n"
            "- Move it through its lifecycle: draft → active → submitted → "
            "awarded → closeout → archived\n"
            "- Share it with your team or hand out an invite link\n\n"
            "**Rule of thumb:** if you'll feed documents in over time, use a "
            "project. If you have one fixed reference corpus (a policy manual), "
            "a plain knowledge base is enough."
        ),
    },
    {
        "id": "web-search",
        "title": "Searching the web from chat",
        "aliases": [
            "web search", "search the web", "search the internet", "google",
            "look it up online", "current information", "latest guidance",
            "can you search online", "internet access", "up to date",
        ],
        "body": (
            "The chat can search the public web when the answer isn't in your "
            "own documents — current sponsor guidance, agency policy pages, "
            "salary caps, deadlines, version numbers.\n\n"
            "**The order matters.** The agent checks *your* material first — "
            "your documents and knowledge bases — and only reaches for the web "
            "when the question needs external or current information. Your "
            "institution's own policy always beats a search result, so answers "
            "grounded in your files stay grounded.\n\n"
            "When it does use the web, it cites the source URL. Ask it to "
            "*\"read that page\"* on any result and it will fetch the full "
            "text; ask it to *\"add that to a knowledge base\"* and the page "
            "gets chunked and indexed for repeat queries with citations.\n\n"
            "**If web search isn't available**, your administrator hasn't "
            "configured a search provider yet — it's set under **Admin → "
            "System Config → Endpoints**. Reading a URL you paste in directly "
            "works either way."
        ),
    },
    {
        "id": "build-from-chat",
        "title": "Building workflows and automations by talking",
        "aliases": [
            "build a workflow", "create a workflow from chat",
            "make a workflow", "author a workflow", "build an automation",
            "set up an automation", "automate this", "can you build",
            "turn this into a workflow", "repeatable",
        ],
        "body": (
            "You don't have to open the visual editor to build things. Describe "
            "the process and the chat will build it.\n\n"
            "**Workflows** — *\"build me a workflow that extracts the budget, "
            "checks it against policy, then drafts a summary.\"* The agent lays "
            "out the steps, shows you a preview, and creates the workflow on "
            "your confirm. Steps run in order and each step's output feeds the "
            "next.\n\n"
            "**Automations** — *\"run that workflow on every file added to my "
            "Intake folder\"* or *\"run it every Monday at 9am.\"* Folder "
            "watches and schedules can both be set up from chat. New "
            "automations are created **disabled** so nothing fires before "
            "you've looked at it — enable it in the Automations tab.\n\n"
            "**Extraction templates** — *\"build an extraction template from "
            "this RFP\"* reads the document and proposes the fields worth "
            "pulling.\n\n"
            "**A workflow built in chat starts unverified.** That's on purpose: "
            "it's ready to run, but you should fine-tune it in the visual "
            "editor and validate it against test cases before you rely on it "
            "for real decisions. Ask the chat to *\"validate it\"* when you're "
            "ready."
        ),
    },
    {
        "id": "saving-chat-output",
        "title": "Saving chat output as a document",
        "aliases": [
            "save this", "save to folder", "export", "keep this",
            "save the summary", "write this up", "save output",
            "export results", "download the answer", "make a document",
        ],
        "body": (
            "Ask the chat to *\"save this to my Grants folder\"* and the output "
            "becomes a real document in your file tree — not just text in a "
            "transcript you'll lose.\n\n"
            "A saved file behaves like anything else you upload: it shows up in "
            "the **Files** tab, downloads, and once indexing finishes it's "
            "searchable in chat, addable to a knowledge base, and usable as "
            "input to extractions and workflows. So a synthesis you generate "
            "today can be the source material for a workflow next week.\n\n"
            "Saves as Markdown by default (`.md`), or plain text if you ask. "
            "Like every other write, it previews first and waits for your "
            "confirm.\n\n"
            "Extraction results have their own path — the results table has "
            "CSV/TSV export built in."
        ),
    },
]


# Build a lookup index at import time. Stopwords are stripped so phrases like
# "what is a knowledge base" reduce to ["knowledge", "base"] for matching.
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "in", "on",
    "for", "with", "and", "or", "but", "my", "your", "what", "whats", "what's",
    "how", "do", "i", "we", "can", "does", "show", "tell", "me", "please",
    "explain", "about", "vandalizer", "this", "that", "these", "those",
})


def _tokens(text: str) -> set[str]:
    """Lowercase + strip punctuation + drop stopwords."""
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", text.lower())
    return {t for t in cleaned.split() if t and t not in _STOPWORDS}


# Pre-compute searchable token sets per topic.
_TOPIC_INDEX: list[tuple[dict, set[str]]] = []
for _t in HELP_TOPICS:
    bag: set[str] = set()
    bag |= _tokens(_t["id"].replace("-", " "))
    bag |= _tokens(_t["title"])
    for alias in _t["aliases"]:
        bag |= _tokens(alias)
    _TOPIC_INDEX.append((_t, bag))


def find_topics(query: str, limit: int = 3) -> list[dict]:
    """Return the best-matching topics for *query*, ranked by token overlap.

    Each result is the full topic dict (id, title, aliases, body) plus a
    ``score`` field. An exact id match short-circuits to rank 1.
    """
    q_tokens = _tokens(query)
    q_lower = query.strip().lower()
    if not q_tokens and not q_lower:
        return []

    # Exact id match wins outright.
    qid = q_lower.replace(" ", "-")
    for topic, _ in _TOPIC_INDEX:
        if topic["id"] == qid:
            return [{**topic, "score": 999}]

    scored: list[tuple[int, dict]] = []
    for topic, bag in _TOPIC_INDEX:
        # Phrase match in any alias gives a big boost — catches multi-word
        # queries like "team folder" or "what is vandalizer" that would
        # otherwise score zero after stopword stripping.
        phrase_boost = 0
        for alias in topic["aliases"]:
            if alias in q_lower or q_lower in alias:
                phrase_boost = 5
                break
        overlap = len(q_tokens & bag)
        if overlap or phrase_boost:
            scored.append((overlap + phrase_boost, topic))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{**t, "score": s} for s, t in scored[:limit]]


def list_topic_index() -> list[dict]:
    """Return ``[{id, title}]`` for every topic — used when no match is found."""
    return [{"id": t["id"], "title": t["title"]} for t in HELP_TOPICS]
