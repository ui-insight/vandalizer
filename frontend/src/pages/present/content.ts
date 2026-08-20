/**
 * Present & Pitch — single source of truth.
 *
 * Every claim below maps to a feature that is REACHABLE IN THE UI today. When you
 * edit this file, keep it honest — if a capability isn't exposed to a real user,
 * it doesn't belong here. Quick "claim → where it lives" map for reviewers:
 *
 *   Structured extraction ........ Workflows editor + extraction tasks   (workspace Library tab, Docs "User Guide")
 *   Workflow DAG engine .......... Workflow editor panel, batch runs     (/workflows/$id → workspace)
 *   RAG chat with citations ...... Workspace chat mode                   (/?mode=chat)
 *   Knowledge bases .............. Workspace knowledge mode              (/?mode=knowledge)
 *   Projects (scoped workspace) .. Workspace Projects drawer             (/?project=…)
 *   Validate & improve ........... KB / extraction / workflow optimizer panels
 *   Folder actions ............... File browser folder context menu (move, export, ask, run, add to KB)
 *   Automations (triggers) ....... Workspace automations mode + /automation
 *   Teams / RBAC ................. /teams, TeamMembership roles
 *   Reviews / sign-off ........... /reviews
 *   Certification ................ Certification panel (Vandal Workflow Architect)
 *   Admin / SystemConfig ......... /admin (models, OCR, auth, branding)
 *   Self-hosting / deploy ........ setup.sh, compose.yaml, DEPLOY.md
 *
 * Deliberately NOT claimed (not user-reachable): the browser-automation Chrome
 * extension (UI integration paused) and a live M365 inbox UI (intake is
 * admin-configured, event-driven — no real-time inbox screen).
 *
 * A note on data residency: documents never leave your infrastructure UNLESS an
 * administrator configures one of two opt-in integrations, both unset by default.
 * A commercial model receives the *text* of a document when it is processed. A
 * remote OCR endpoint receives the *whole file* — see services/ocr_client.py,
 * which POSTs the PDF itself to whatever conversion service is configured. Keep
 * the exception attached to the claim wherever the claim appears — unqualified
 * "never leaves your infrastructure" is only true of a deployment that has
 * configured neither, i.e. a local model paired with local OCR.
 */
import {
  Landmark,
  Server,
  Users,
  GraduationCap,
  type LucideIcon,
} from 'lucide-react'

export type AudienceId = 'leadership' | 'deploy' | 'team' | 'researchers'

export interface ElevatorPitch {
  /** ~30 seconds, conversational — meant to be read aloud. */
  spoken: string
  /** For an email or a proposal. Blank lines separate paragraphs. */
  written: string
}

export interface Slide {
  id: string
  title: string
  /** Markdown — rendered identically in the deck and the printable handout. */
  body: string
  /** Optional presenter note: shown small in the deck, hidden in print/read. */
  note?: string
}

export interface ReadSection {
  id: string
  heading: string
  /** Markdown. */
  body: string
}

export interface Track {
  id: AudienceId
  /** Short nav label, e.g. "For Leadership". */
  label: string
  /**
   * One line under the label. Must match this audience's card description on
   * the hub — the two are read as the same promise.
   */
  tagline: string
  icon: LucideIcon
  /** Lead-in sentence(s) above the value props, framing what this page is for. */
  overview: string
  /** 3–6 skimmable bullets for the hub card and the top of the read page. */
  valueProps: string[]
  pitch: ElevatorPitch
  /** Ordered deck. */
  slides: Slide[]
  /** Long-form read-mode content. */
  sections: ReadSection[]
}

// ---------------------------------------------------------------------------
// Leadership
// ---------------------------------------------------------------------------

const leadership: Track = {
  id: 'leadership',
  label: 'For Leadership',
  tagline: 'Communicate the value of Vandalizer to leadership',
  icon: Landmark,
  overview:
    'Vandalizer is designed to reliably and securely streamline RA workflows. This page offers critical information for your leadership to begin evaluating Vandalizer for security, accuracy, reproducibility, and flexibility. Vandalizer satisfies these critical benchmarks for research administration:',
  valueProps: [
    'Self-hosted — your documents never leave your infrastructure, unless you use a commercial model',
    'Open source (GPL v3) — no per-seat license fee, no vendor lock-in',
    'Built at the University of Idaho under NSF GRANTED (Award #2427549)',
    'Customizable — insert your institution’s name, logo, icon, and brand color',
    'Works with any AI provider: cloud deployments or fully air-gapped, on-premises environments',
    'Runs on a single commodity server — no GPU required with a cloud model',
  ],
  pitch: {
    spoken:
      "Today’s information climate is straining RA professionals, who are tasked with managing heavy loads of administrative documents every day. Vandalizer addresses these challenges by offering a suite of AI tools designed to streamline RA workflows. Vandalizer is an open-source AI platform, designed specifically for research administration. Vandalizer would allow us to use whatever AI provider we choose, and it remains secure because we can run the platform on our own servers. This means that our administrative documents would never leave our infrastructure, unless we opt for a commercial model — and if we run a local one, nothing leaves at all. Vandalizer was built at the University of Idaho with NSF GRANTED funding, so it’s free to license, and it runs on a single commodity server. And it’s easy to try it out: all we have to do is visit the Vandalizer web page and request access to a two-week trial.",
    written: [
      'Today’s information climate is straining RA professionals, who are tasked with managing heavy loads of administrative documents every day. Vandalizer addresses these challenges by offering a suite of AI tools designed to reduce the amount of time RAs spend on structured, repeatable tasks. Vandalizer is an open-source, self-hosted AI platform, designed specifically for research administration.',
      'Vandalizer extracts structured data from the proposals, awards, and compliance documents our staff process by hand today. From there, RAs can ask the AI questions about those documents (with answers cited back to the source) and prompt Vandalizer to generate new administrative documents. Vandalizer allows us to select the AI provider of our choice, and it can support either cloud-based deployment or an air-gapped, on-premises environment. Because it runs on our own infrastructure, our documents never leave the institution unless we use a commercial model, and there is no vendor lock-in or per-seat license fee. Developed at the University of Idaho under the NSF GRANTED program (Award #2427549) and released under GPL v3, it runs on a single commodity server and is designed for other institutions to adopt.',
    ].join('\n\n'),
  },
  slides: [
    {
      id: 'title',
      title: 'Vandalizer',
      body: 'AI document intelligence for research administration.\n\n*Self-hosted · open source · built by a university, for universities.*',
      note: 'Open with the problem your office actually feels, on the next slide.',
    },
    {
      id: 'problem',
      title: 'The problem we already have',
      body: [
        '- Hundreds of PDFs per funding cycle — read and reread **by hand**',
        '- Deadlines, budgets, and sponsor requirements buried in long documents',
        '- Institutional knowledge walks out the door when staff leave',
        '- Every missed requirement is a compliance and funding risk',
      ].join('\n'),
    },
    {
      id: 'what',
      title: 'What Vandalizer does',
      body: [
        '- **Extract:** pull dates, budgets, requirements into clean structured data',
        '- **Chat:** ask questions of your documents, answers cited to the source',
        '- **Automate:** process new files the moment they arrive',
        '- **Collaborate:** shared, repeatable workflows across the team',
      ].join('\n'),
    },
    {
      id: 'safe',
      title: 'Why it is safe to say yes',
      body: [
        '- **Self-hosted** — runs on our servers; documents never leave our',
        '  infrastructure, unless we use a commercial model',
        '- **Your choice of AI** — commercial provider, or a local model fully air-gapped',
        '- **Open source, GPL v3** — the platform is auditable, forkable, no black box',
        '- **No vendor lock-in** and **no per-seat license fee**',
      ].join('\n'),
    },
    {
      id: 'cost',
      title: 'What it costs',
      body: [
        '- **Software:** free, open source, no license fee',
        '- **Hardware:** a single commodity server (~16 GB RAM); **no GPU** with a cloud model',
        '- **AI usage:** pay-as-you-go to your chosen LLM provider, or $0 with a local model',
        '- **People:** IT stands it up with a guided installer in an afternoon',
      ].join('\n'),
    },
    {
      id: 'governance',
      title: 'Governance & control',
      body: [
        '- Role-based access across teams and organizations',
        '- Review & sign-off steps built into workflows',
        '- Immutable audit log of administrative actions',
        '- Configurable data-retention policy',
      ].join('\n'),
    },
    {
      id: 'yours',
      title: 'Make it your institution’s tool',
      body: [
        '- Set your **name, logo, icon, and brand color** in the admin UI',
        '- Carries through the header, sign-in, browser tab, chat, and **email**',
        '- Staff see *your* tool, not a generic "Vandalizer" install',
        '- A quiet "Powered by Vandalizer" credit and NSF acknowledgement remain',
      ].join('\n'),
      note: 'Branding is a runtime setting, applied the moment you save, no redeploy.',
    },
    {
      id: 'credibility',
      title: 'Where it comes from',
      body: [
        'Built at the **University of Idaho** under the **NSF GRANTED** program',
        '(Award #2427549): purpose-built for research administration and',
        'designed from day one for **other institutions to adopt**.',
      ].join('\n'),
    },
    {
      id: 'ask',
      title: 'The ask',
      body: [
        '1. Approve a **time-boxed pilot** in one office',
        '2. Pilot staff get fluent through the built-in **certification** course',
        '3. We measure **hours saved** and **error reduction** on real documents',
        '4. Decide on a wider rollout from evidence, not a sales deck',
        '',
        'Try the live demo: **/demo**',
      ].join('\n'),
      note: 'Close by naming the office and the documents you would pilot with.',
    },
  ],
  sections: [
    {
      id: 'problem',
      heading: 'The problem this solves',
      body: 'Research administration runs on documents — grant proposals, award letters, sponsor terms, regulatory filings. Today, staff read and reread hundreds of these PDFs by hand every funding cycle. Deadlines and requirements are buried in long documents, work is inconsistent between people, and institutional knowledge leaves when staff do. Vandalizer turns that manual burden into repeatable, audited, AI-assisted workflows.',
    },
    {
      id: 'value',
      heading: 'Why it is safe to adopt',
      body: 'Vandalizer is **self-hosted**: it runs on your own servers and your documents never leave your infrastructure, unless you use a commercial model — in which case the text of a document is sent to that vendor when it is processed, under that vendor’s terms. Choose a local model running air-gapped on premise and nothing leaves the institution at all. The platform itself is **open source under GPL v3**, so there is no black box on our side of the line, no vendor lock-in, and no per-seat license fee. Governance is built in: role-based access, review and sign-off steps, an immutable audit log, and configurable data retention.',
    },
    {
      id: 'yours',
      heading: 'Make it your own',
      body: 'Vandalizer white-labels to your institution, so the platform presents as an institutional tool rather than a generic deployment. From the admin console you set the organization name, upload a logo and a square icon, and pick a brand color. Your branding is then carried into the platform header, the sign-in page, the browser tab, the in-app chat, and the system emails sent to staff members. Branding is a runtime setting, so Vandalizer applies these changes the moment you save them in the admin console, with no redeploy necessary. Vandalizer is open source under GPL v3, so a small "Powered by Vandalizer" credit and the NSF GRANTED acknowledgement stay in the footer — creator and funder lineage remain visible.',
    },
    {
      id: 'cost',
      heading: 'What it costs',
      body: 'The software is free. The hardware is a single commodity server (around 16 GB of RAM). **No GPU is required** if you choose to deploy a cloud-based LLM. AI usage is pay-as-you-go to your chosen provider, where token costs can be zero with a local model. A guided installer (`setup.sh`) stands the whole system up, including an admin account and a starter catalog of templates.',
    },
    {
      id: 'provenance',
      heading: 'Provenance',
      body: 'Vandalizer was built at the University of Idaho under the **NSF GRANTED program (Award #2427549)**. It was designed specifically for research administration and intended for other institutions to adopt and extend.',
    },
    {
      id: 'next',
      heading: 'Evaluation and next steps',
      body: 'Start with the live **demo** to see how it works on sample documents. Stand up a **time-boxed pilot** in a single office; pilot staff get fluent through the built-in **certification** course (Vandal Workflow Architect) as part of onboarding, then measure hours saved and error reduction on real work. Decide on wider rollout based on those measured results.',
    },
  ],
}

// ---------------------------------------------------------------------------
// Deploy / IT
// ---------------------------------------------------------------------------

const deploy: Track = {
  id: 'deploy',
  label: 'For IT & Deployment',
  tagline: 'Communicate the safety and flexibility of Vandalizer to IT and Deployment',
  icon: Server,
  overview:
    'Vandalizer is designed to reliably and securely streamline RA workflows. This page offers critical information for your IT department to begin evaluating Vandalizer for security and flexibility. Vandalizer satisfies these critical benchmarks for research administration:',
  valueProps: [
    'Docker Compose stack: FastAPI, Celery, MongoDB, Redis, ChromaDB, nginx',
    'Works with any AI provider, cloud or on-premises: ~16 GB RAM on a single commodity server, with a GPU needed only if you run a large model locally',
    'Self-hosted with encrypted secrets; on-prem / air-gapped option',
    'Guided setup.sh installer — admin account and starter catalog included',
    'LLM endpoints and keys configured at runtime in the admin UI',
    'White-label in-app — name, logo, icon, color, and email; no redeploy',
  ],
  pitch: {
    spoken:
      'Vandalizer is designed to offer practical and secure implementation for our institution while augmenting RA workflows. The platform ships as a set of Docker containers — a FastAPI backend, Celery workers, MongoDB, Redis, and a ChromaDB vector store behind nginx. It needs about sixteen gigs of RAM on a single server and can run with no GPU if you direct it to a cloud model. If you want everything on-premises, you can run a local model through Ollama or vLLM; this can run fully air-gapped. LLM endpoints and keys are configured at runtime in the admin UI, and secrets are encrypted at rest.',
    written:
      'Vandalizer is designed to offer practical and secure implementation for our institution while augmenting RA workflows. Vandalizer deploys as a Docker Compose stack — a FastAPI backend, Celery workers, MongoDB (application data), Redis (task broker), and a ChromaDB vector store, served behind nginx. A guided `setup.sh` installer provisions the system, an admin account, and a starter catalog; a manual compose path exists for scripted environments. It runs on a single commodity server (~16 GB RAM) with no GPU required when using a cloud LLM, or fully on-premises/air-gapped with a local model via Ollama or vLLM. LLM providers, OCR endpoints, and auth methods are configured at runtime in the admin UI, and secrets (API keys, tokens) are encrypted at rest.',
  },
  slides: [
    {
      id: 'title',
      title: 'Deploying Vandalizer',
      body: 'What you will run, what you will need, and your options.',
    },
    {
      id: 'architecture',
      title: 'Architecture',
      body: [
        '```',
        '          Browser (React SPA)',
        '                 │',
        '              nginx  (reverse proxy + static)',
        '                 │',
        '          FastAPI backend  (:8001)',
        '          ┌──────┼───────┬──────────┐',
        '       MongoDB  Redis  ChromaDB   Celery workers',
        '       (data)  (queue) (vectors)  (async jobs)',
        '                 │',
        '          External APIs: LLM provider · M365/Graph · OCR',
        '```',
      ].join('\n'),
      note: 'Redis is ephemeral (broker); Mongo, uploads and Chroma are the stateful volumes.',
    },
    {
      id: 'requirements',
      title: 'What you will need',
      body: [
        '| Size | CPU | RAM | Storage |',
        '| --- | --- | --- | --- |',
        '| Evaluation | 4 cores | 8–10 GB | 50 GB |',
        '| Department | 8 cores | 16 GB | 100 GB+ |',
        '',
        '**No GPU required** when using a cloud LLM. Docker & Docker Compose only.',
      ].join('\n'),
    },
    {
      id: 'llm',
      title: 'LLM options',
      body: [
        '- **Cloud:** any OpenAI-compatible endpoint, plus native Anthropic',
        '- **Local / on-prem:** Ollama or vLLM, can run fully air-gapped',
        '- **Aggregators:** OpenRouter and custom endpoints',
        '- Configured **at runtime** in the admin UI: no redeploy to change models',
      ].join('\n'),
    },
    {
      id: 'install',
      title: 'How you install it',
      body: [
        '- **Supported path:** `./setup.sh`, a guided installer; creates an admin',
        '  account and seeds a starter catalog of templates',
        '- **Scripted path:** Docker Compose directly (`compose.yaml`)',
        '- Full guidance in **DEPLOY.md**',
      ].join('\n'),
    },
    {
      id: 'security',
      title: 'Security & data residency',
      body: [
        '- Self-hosted — documents and vectors never leave your infrastructure,',
        '  unless you configure a **commercial model**',
        '- Commercial model: document text goes to that vendor when processed',
        '- Local model (Ollama / vLLM): nothing leaves — fully air-gapped',
        '- Secrets (LLM keys, OAuth tokens) **encrypted at rest** (Fernet)',
        '- JWT sessions; OAuth (Azure AD, Google, Okta) and SAML supported',
        '- Optional M365 / Graph integration: off unless you configure it',
      ].join('\n'),
    },
    {
      id: 'ops',
      title: 'Day-2 operations',
      body: [
        '- **Back up:** MongoDB data, the uploads volume, and the ChromaDB volume',
        '- Redis is an ephemeral broker: nothing to back up',
        '- Immutable audit log for administrative actions',
        '- Models, OCR endpoints, auth, and **white-label branding** managed from **/admin**',
      ].join('\n'),
    },
    {
      id: 'cta',
      title: 'Get started',
      body: 'Clone the repo, run `./setup.sh`, and read **DEPLOY.md** for production guidance.\n\nFull technical docs: **/docs**',
    },
  ],
  sections: [
    {
      id: 'architecture',
      heading: 'Architecture',
      body: 'A React single-page app is served behind nginx, which proxies a FastAPI backend. The backend uses MongoDB for application data, Redis as the Celery task broker, and ChromaDB as the vector store for retrieval-augmented chat. Celery workers handle asynchronous jobs: document processing, extraction, and knowledge-base ingestion. External services are reached over HTTPS: your chosen LLM provider, optional Microsoft 365 / Graph, and an optional OCR endpoint.',
    },
    {
      id: 'requirements',
      heading: 'System requirements',
      body: 'For an evaluation deployment, a host with 4 CPU cores, 8–10 GB of RAM, and 50 GB of storage is sufficient — a laptop or small virtual machine. For a departmental deployment, we recommend a host with 8 CPU cores, 16 GB of RAM, and at least 100 GB of available storage. **A GPU is not required** when Vandalizer uses a cloud-based LLM provider; a GPU is only needed if you choose to run a large model locally. The only host prerequisites are Docker and Docker Compose.',
    },
    {
      id: 'llm',
      heading: 'LLM options',
      body: 'Vandalizer talks to any OpenAI-compatible endpoint and to Anthropic natively. For on-premises deployments, including air-gapped environments, Vandalizer runs a local model through **Ollama** or **vLLM**. OpenRouter and custom endpoints are also supported. Models, keys, and endpoints are configured **at runtime in the admin UI** — you can add or switch providers without a redeploy.',
    },
    {
      id: 'install',
      heading: 'Deployment options',
      body: 'The supported path for Vandalizer deployment is the guided installer: `./setup.sh` provisions the full stack, creates an admin account, and seeds a starter catalog. For scripted or CI environments, drive Docker Compose (`compose.yaml`) directly. **DEPLOY.md** covers production hardening, TLS, and backups.',
    },
    {
      id: 'security',
      heading: 'Security & data residency',
      body: 'Vandalizer runs on your infrastructure, so documents and their vector embeddings never leave the institution — **unless you configure a commercial model**. In that case the text of a document is sent to that vendor when it is processed, under that vendor’s terms; the corpus itself, the uploads, and the vector store still stay on your servers, and there is no vendor-side copy of them. Run a local model through Ollama or vLLM instead and nothing leaves at all. The same applies to OCR: scanned documents are read locally unless an administrator points Vandalizer at an external OCR endpoint, which receives the file itself. Secrets — LLM API keys and OAuth tokens — are encrypted at rest with a Fernet key. Sessions use JWTs; sign-in supports OAuth (Azure AD, Google, Okta) and SAML. The Microsoft 365 / Graph integration is optional and inert unless an administrator configures it. A fully air-gapped deployment is possible by pairing a local LLM with a local OCR endpoint.',
    },
    {
      id: 'ops',
      heading: 'Day-2 operations',
      body: 'Three volumes require backup for ongoing maintenance: the MongoDB data volume, the uploads volume, and the ChromaDB volume. Redis is an ephemeral broker and needs no backup. Administrators manage models, OCR endpoints, authentication methods, and **white-label branding** — organization name, logo, icon, brand color, and the styling of outgoing email — from the **/admin** console; branding is a runtime setting stored in the database, so rebranding never requires a redeploy. Every administrative action is recorded in an immutable audit log.',
    },
  ],
}

// ---------------------------------------------------------------------------
// Team / end users
// ---------------------------------------------------------------------------

const team: Track = {
  id: 'team',
  label: 'For Your Team',
  tagline: 'Guide your team through a walkthrough of Vandalizer',
  icon: Users,
  overview:
    'Vandalizer is designed to reliably and securely save RAs time on structured, repeatable tasks. This page supports RAs conveying the value of Vandalizer while introducing the platform to departmental colleagues. With Vandalizer, RAs have the power to:',
  valueProps: [
    'Upload and organize documents into folders',
    'Use an AI chatbot to receive cited information about selected documents',
    'Access a store of AI-powered workflows and apply them repeatedly to future documents; design, evaluate, and apply original workflows',
    'Gather everything for one grant into a Project: files, knowledge base, tools, and chat',
    'Automate processing so new files are handled on arrival',
    'Learn it through the built-in certification course',
  ],
  pitch: {
    spoken:
      'Vandalizer offers RA organizations a suite of AI-powered tools that are specifically designed to streamline administrative processes. Think of Vandalizer as a smart workspace for our documents. Vandalizer offers a store of "workflows" — a coordinated sequence of AI-powered processes. Workflows can be applied to quickly surface important information in selected documents, like deadlines, budgets, or PI names, and to generate new documents like a Notice of Award summary or a budget justification. Vandalizer also gives RAs the power to set up automations, so new files get processed as they arrive. This platform eases the burden of structured, repeatable tasks, freeing up time for RAs to turn to responsibilities that require their institutional knowledge and professional judgment. The team that created Vandalizer also provides a certification course to help RAs achieve productive results with Vandalizer while remaining secure and compliant.',
    written:
      'Vandalizer offers RA organizations a suite of AI-powered tools that are specifically designed to streamline administrative processes. The platform introduces a shared workspace for RA organizations to process administrative documents with AI-powered tasks and automations. At its center is a store of "workflows" — coordinated sequences of AI-powered processes. Each workflow is designed to achieve a specific outcome, but generally they surface important information in selected documents (like deadlines, budgets, or PI names) and generate new documents like a Notice of Award summary or a budget justification. Vandalizer also gives RAs the power to set up automations, so new files get processed as they arrive. This platform eases the burden of structured, repeatable tasks, freeing up time for RAs to pursue responsibilities that require their institutional knowledge and professional judgment. The team that created Vandalizer also provides a certification course to help RAs ensure that they achieve productive results with Vandalizer while remaining secure and compliant in the process.',
  },
  slides: [
    {
      id: 'title',
      title: 'A tour of Vandalizer',
      body: 'A smart workspace for the documents you work with every day.',
    },
    {
      id: 'upload',
      title: '1 · Upload & organize',
      body: [
        '- Drag in PDFs, Word, Excel, and more',
        '- Sort them into folders',
        '- Search across everything you have uploaded',
      ].join('\n'),
    },
    {
      id: 'extract',
      title: '2 · Build an extraction task',
      body: [
        '- Define the fields you want: deadlines, budgets, PI names, terms',
        '- Chain steps together into a repeatable pipeline',
        '- Test on one document, then **run it across a whole batch**',
        '- Download results as JSON, CSV, or a ZIP',
      ].join('\n'),
    },
    {
      id: 'knowledge',
      title: '3 · Knowledge bases',
      body: [
        '- Collect documents, URLs, and notes into a reusable knowledge base',
        '- Share it with your team or keep it personal',
        '- It becomes searchable context for chat',
      ].join('\n'),
    },
    {
      id: 'chat',
      title: '4 · Chat with your documents',
      body: [
        '- Ask plain-language questions across a folder or knowledge base',
        '- Every answer is **cited back to the source** document and page',
        '- Attach files or URLs for extra context',
      ].join('\n'),
    },
    {
      id: 'projects',
      title: '5 · Projects: tie it all together',
      body: [
        '- Gather one grant or effort into a single **Project**',
        '- Its **files, knowledge base, chat, and pinned tools** live in one place',
        '- Chat answers **only from that project’s documents**',
        '- Keep it personal, share it with your team, or invite a collaborator by link',
      ].join('\n'),
      note: 'A project’s knowledge base builds itself from the files you add, with no extra setup.',
    },
    {
      id: 'automate',
      title: '6 · Automations',
      body: [
        '- **Watch a folder** and run a workflow on every new upload',
        '- Run on a **schedule**, or trigger via **API**',
        '- Intake from **Microsoft 365** when configured',
      ].join('\n'),
    },
    {
      id: 'collaborate',
      title: '7 · Work as a team',
      body: [
        '- Shared workflows, documents, and knowledge bases',
        '- Roles: owner, admin, member',
        '- **Review & sign-off** steps for work that needs approval',
      ].join('\n'),
    },
    {
      id: 'certify',
      title: '8 · Get certified',
      body: 'The built-in **Vandal Workflow Architect** course walks you from your first upload to building validated workflows, hands-on, inside the product.\n\nSign in and start: **/**',
      note: 'Offer to run a live build of one real workflow with the team.',
    },
  ],
  sections: [
    {
      id: 'upload',
      heading: 'Upload & organize',
      body: 'Drag in PDFs (plus Word, Excel, and HTML), sort them into folders, and search across documents. Vandalizer reads the text out of each file — including scanned PDFs when an OCR endpoint is configured — so it is ready to work with.',
    },
    {
      id: 'extract',
      heading: 'Extraction tasks',
      body: 'Extraction tasks are where Vandalizer does its heaviest lifting. Instead of reading every document, you define the fields you care about once — deadlines, budgets, PI names, sponsor terms — and chain steps into a repeatable pipeline. Test it on a single document, validate it against expected answers, then run it across an entire batch and download the results as JSON, CSV, or a ZIP. A saved pipeline of steps is a **workflow**, and workflows can be exported and shared as templates.',
    },
    {
      id: 'knowledge',
      heading: 'Knowledge bases',
      body: 'Collect documents, URLs, and notes into a reusable knowledge base that becomes searchable context for chat. Keep it personal or share it with your team; administrators can curate verified knowledge bases for everyone.',
    },
    {
      id: 'chat',
      heading: 'Chat with citations',
      body: 'Ask plain-language questions across a folder or a knowledge base and get answers cited back to the exact source document and page, so you can trust and verify them. Attach extra files or URLs to bring more context into the conversation.',
    },
    {
      id: 'projects',
      heading: 'Projects',
      body: 'When a piece of work (a grant, a contract, a compliance effort) spans many documents and tools, gather it into a **Project**. A project has its own folder of files, an automatic knowledge base built from those files, a chat that answers only from the project’s documents, and a place to pin the workflows and automations you use for it. Keep a project personal, share it with your team, or send a collaborator a viewer or editor invite link. Everything for that effort stays in one scoped workspace instead of scattered across the library.',
    },
    {
      id: 'automate',
      heading: 'Automations',
      body: 'Place repetitive processes on autopilot. Select a folder and run a workflow on every new upload, run automations on a schedule, trigger automations via API, or configure document intake from Microsoft 365. Vandalizer keeps a log of every automated process.',
    },
    {
      id: 'collaborate',
      heading: 'Collaboration and certification',
      body: 'Teams share workflows, documents, and knowledge bases with owner / admin / member roles. Work that needs approval can route through review and sign-off steps. New users get fluent through the built-in **Vandal Workflow Architect** certification, which provides hands-on lessons and exercises right inside the product.',
    },
  ],
}

// ---------------------------------------------------------------------------
// Researchers / PIs
// ---------------------------------------------------------------------------

const researchers: Track = {
  id: 'researchers',
  label: 'For Researchers & PIs',
  tagline: 'Tell Researchers and PIs how Vandalizer streamlines the processing of their proposals',
  icon: GraduationCap,
  overview:
    'Vandalizer is implemented to streamline the processing of your research and proposal documents. With Vandalizer, you can:',
  valueProps: [
    'Expect faster turnaround of the documents RAs process for you',
    'Expect more consistent support across submissions',
    'Ask plain-language questions of long solicitations, and receive answers with citations',
    'Receive fast answers about compliance requirements — deadlines, formatting guidelines',
  ],
  pitch: {
    spoken:
      'Vandalizer is a suite of AI-powered tools that are specifically designed to streamline administrative processes. The platform helps your research administration office turn your proposals around faster and more consistently. For example, if you submit a solicitation document to us, we can use Vandalizer to quickly surface deadlines. You — or we — can also ask Vandalizer plain-language questions about the document and quickly receive answers with citations, saving us the burden of having to scroll through the document.',
    written:
      'Vandalizer is a suite of AI-powered tools that are specifically designed to streamline administrative processes. It supports our research administrators in performing faster turnaround on your research and proposal documents, and it helps us ensure that no details slip through the cracks. It reads solicitations and supporting documents to surface deadlines, formatting rules, and budget requirements automatically, and it lets anyone ask plain-language questions of a long funding announcement and get answers cited to the source rather than scrolling through dozens of pages. The result is quicker, more reliable support for your submissions — and because we run Vandalizer ourselves, your documents never leave the institution unless we use a commercial AI model.',
  },
  slides: [
    {
      id: 'title',
      title: 'Vandalizer for your proposals',
      body: 'How your research administration office uses AI to support you, faster.',
    },
    {
      id: 'benefit',
      title: 'Faster, more consistent turnaround',
      body: [
        '- Deadlines, formatting rules, and budget requirements surfaced **automatically**',
        '- Nothing buried on page 60 slips through',
        '- The same rigor applied to every submission',
      ].join('\n'),
    },
    {
      id: 'ask',
      title: 'Ask Vandalizer about the documents',
      body: [
        '- Pose a plain-language question to a long solicitation',
        '- Get an answer **cited to the exact page**',
        '- No more scrolling through eighty-page announcements',
      ].join('\n'),
    },
    {
      id: 'trust',
      title: 'Your data stays put',
      body: [
        '- Runs on the institution’s own infrastructure',
        '- Your proposals never leave our systems, unless we use a commercial model',
        '- Open source and auditable',
      ].join('\n'),
    },
    {
      id: 'cta',
      title: 'Talk to your research office',
      body: 'Ask your sponsored-programs office how Vandalizer can support your next submission.',
    },
  ],
  sections: [
    {
      id: 'benefit',
      heading: 'What it means for you',
      body: 'When your proposal goes through the research administration office, Vandalizer helps surface deadlines, formatting rules, and budget requirements automatically, so the easy-to-miss details on page 60 do not slip through. Every submission gets the same rigor, which means faster and more consistent support for you.',
    },
    {
      id: 'ask',
      heading: 'Ask Vandalizer about the documents',
      body: 'Long funding announcements are tedious to read end to end. Vandalizer lets staff (or you) ask plain-language questions of a solicitation and get answers cited back to the exact page — so the right requirement is found in seconds, with the receipts to prove it.',
    },
    {
      id: 'trust',
      heading: 'Your data stays put',
      body: 'Vandalizer is self-hosted on the institution’s own infrastructure, so your proposals and documents never leave our systems — unless we use a commercial AI model, in which case the text being analyzed is sent to that vendor to process it. Your office can tell you which model it runs. The platform is open source and auditable — no black box handling your work.',
    },
  ],
}

// ---------------------------------------------------------------------------

export const TRACKS: Record<AudienceId, Track> = {
  leadership,
  deploy,
  team,
  researchers,
}

export const TRACK_ORDER: AudienceId[] = ['leadership', 'deploy', 'team', 'researchers']

export function getTrack(id: string | undefined): Track | undefined {
  if (!id) return undefined
  // Index only the audiences we actually define. A bare lookup resolves
  // inherited members too, so /docs/present/toString returned
  // Object.prototype.toString — truthy, so the caller's `if (!track)` redirect
  // was skipped, and dereferencing .id and .slides on a Function threw. That
  // route is public and unauthenticated, so the failure is a blank screen for
  // anyone who can reach the page.
  if (!TRACK_ORDER.includes(id as AudienceId)) return undefined
  return TRACKS[id as AudienceId]
}

// Dev-time completeness guard — catches an audience added without full content.
if (import.meta.env?.DEV) {
  for (const id of TRACK_ORDER) {
    const t = TRACKS[id]
    console.assert(Boolean(t), `[present] missing track: ${id}`)
    console.assert(t.slides.length > 0, `[present] ${id}: needs at least one slide`)
    console.assert(t.sections.length > 0, `[present] ${id}: needs at least one section`)
    console.assert(
      t.pitch.spoken.trim().length > 0 && t.pitch.written.trim().length > 0,
      `[present] ${id}: needs both a spoken and a written pitch`,
    )
    console.assert(t.valueProps.length > 0, `[present] ${id}: needs value props`)
    console.assert(t.overview.trim().length > 0, `[present] ${id}: needs an overview`)
  }
}
