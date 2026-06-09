/**
 * Present & Pitch — single source of truth.
 *
 * Every claim below maps to a feature that is REACHABLE IN THE UI today. When you
 * edit this file, keep it honest — if a capability isn't exposed to a real user,
 * it doesn't belong here. Quick "claim → where it lives" map for reviewers:
 *
 *   Structured extraction ........ Workflows editor + extraction tasks   (/workflows, Docs "User Guide")
 *   Workflow DAG engine .......... Workflow editor, batch runs           (/workflows/$id)
 *   RAG chat with citations ...... Workspace chat mode                   (/?mode=chat)
 *   Knowledge bases .............. Workspace knowledge mode              (/?mode=knowledge)
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
  /** One tight paragraph for an email or a proposal. */
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
  /** One line under the label. */
  tagline: string
  icon: LucideIcon
  /** 3–5 skimmable bullets for the hub card and the top of the read page. */
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
  tagline: 'What you need to know to say yes',
  icon: Landmark,
  valueProps: [
    'Self-hosted — your documents never leave your infrastructure',
    'Make it your own — your institution’s name, logo, icon, and brand color',
    'Open source (GPL v3) — no per-seat license fee, no vendor lock-in',
    'Works with any AI provider: cloud or fully on-premise / air-gapped',
    'Built at the University of Idaho under NSF GRANTED (Award #2427549)',
    'Runs on a single commodity server — no GPU required with a cloud model',
  ],
  pitch: {
    spoken:
      "Vandalizer is an open-source AI platform we can run on our own servers to read the mountain of PDFs that flow through research administration — proposals, award letters, sponsor terms — and pull out the dates, budgets, and requirements automatically. Because it's self-hosted, our documents never leave our infrastructure, and it works with whatever AI provider we choose, cloud or on-premise. It was built at the University of Idaho with NSF GRANTED funding, it's free to license, and it runs on a single commodity server. The ask is simple: let us stand up a pilot and measure the hours it gives back to staff.",
    written:
      'Vandalizer is an open-source, self-hosted AI document-intelligence platform built for research administration. It extracts structured data from the proposals, awards, and compliance documents our staff process by hand today, lets them ask questions of those documents and get answers cited back to the source, and automates the repetitive routing in between. Because it runs on our own infrastructure with the AI provider of our choice, sensitive data never leaves the institution and there is no vendor lock-in or per-seat license fee. Developed at the University of Idaho under the NSF GRANTED program (Award #2427549) and released under GPL v3, it runs on a single commodity server and is designed for other institutions to adopt.',
  },
  slides: [
    {
      id: 'title',
      title: 'Vandalizer',
      body: 'AI document intelligence for research administration.\n\n*Self-hosted · open source · built by a university, for universities.*',
      note: 'Open with the problem your office actually feels — the next slide.',
    },
    {
      id: 'problem',
      title: 'The problem we already have',
      body: [
        '- Hundreds of PDFs per funding cycle — read and re-keyed **by hand**',
        '- Deadlines, budgets, and sponsor requirements buried in long documents',
        '- Institutional knowledge walks out the door when staff leave',
        '- Every missed requirement is a compliance and funding risk',
      ].join('\n'),
    },
    {
      id: 'what',
      title: 'What Vandalizer does',
      body: [
        '- **Extract** — pull dates, budgets, requirements into clean structured data',
        '- **Chat** — ask questions of your documents, answers cited to the source',
        '- **Automate** — process new files the moment they arrive',
        '- **Collaborate** — shared, repeatable workflows across the team',
      ].join('\n'),
    },
    {
      id: 'safe',
      title: 'Why it is safe to say yes',
      body: [
        '- **Self-hosted** — runs on our servers; data stays on our infrastructure',
        '- **Your choice of AI** — cloud provider, or a local model fully air-gapped',
        '- **Open source, GPL v3** — auditable, forkable, no black box',
        '- **No vendor lock-in** and **no per-seat license fee**',
      ].join('\n'),
    },
    {
      id: 'cost',
      title: 'What it costs',
      body: [
        '- **Software:** free — open source, no license fee',
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
        '- Staff see *your* tool — not a generic "Vandalizer" install',
        '- A quiet "Powered by Vandalizer" credit and NSF acknowledgement remain',
      ].join('\n'),
      note: 'Branding is a runtime setting — applied the moment you save, no redeploy.',
    },
    {
      id: 'credibility',
      title: 'Where it comes from',
      body: [
        'Built at the **University of Idaho** under the **NSF GRANTED** program',
        '(Award #2427549) — purpose-built for research administration and',
        'designed from day one for **other institutions to adopt**.',
      ].join('\n'),
    },
    {
      id: 'ask',
      title: 'The ask',
      body: [
        '1. Approve a **time-boxed pilot** in one office',
        '2. We measure **hours saved** and **error reduction** on real documents',
        '3. Decide on a wider rollout from evidence, not a sales deck',
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
      body: 'Research administration runs on documents — grant proposals, award letters, sponsor terms, regulatory filings. Today, staff read and re-key hundreds of these PDFs by hand every funding cycle. Deadlines and requirements are buried in long documents, work is inconsistent between people, and institutional knowledge leaves when staff do. Vandalizer turns that manual burden into repeatable, audited, AI-assisted workflows.',
    },
    {
      id: 'value',
      heading: 'Why it is safe to adopt',
      body: 'Vandalizer is **self-hosted**: it runs on your own servers and your documents never leave your infrastructure. You choose the AI provider — a cloud model, or a local model running fully air-gapped on premise. It is **open source under GPL v3**, so there is no black box, no vendor lock-in, and no per-seat license fee. Governance is built in: role-based access, review and sign-off steps, an immutable audit log, and configurable data retention.',
    },
    {
      id: 'yours',
      heading: 'Make it your own',
      body: 'Vandalizer white-labels to your institution. From the admin console you set the organization name, upload a logo and a square icon, and pick a brand color — and they thread through the header, the sign-in page, the browser tab, the in-app chat, and the system emails your staff receive. To your team it reads as *your* institution’s tool, not a generic deployment, and because branding is a runtime setting it applies the moment you save, with no redeploy. Vandalizer is open source under GPL v3, so a small "Powered by Vandalizer" credit and the NSF GRANTED acknowledgement stay in the footer — creator and funder lineage remain visible.',
    },
    {
      id: 'cost',
      heading: 'What it costs',
      body: 'The software is free. The hardware is a single commodity server (around 16 GB of RAM) — **no GPU is required** when you point it at a cloud LLM. AI usage is pay-as-you-go to your chosen provider, or zero with a local model. A guided installer (`setup.sh`) stands the whole system up, including an admin account and a starter catalog of templates.',
    },
    {
      id: 'provenance',
      heading: 'Provenance',
      body: 'Vandalizer was built at the University of Idaho under the **NSF GRANTED program (Award #2427549)**. It was designed specifically for research administration and intended for other institutions to adopt and extend.',
    },
    {
      id: 'next',
      heading: 'How to evaluate it',
      body: 'Start with the live **demo** to see it on real-looking documents. Stand up a **time-boxed pilot** in a single office and measure hours saved and error reduction. Staff can become fluent through the built-in **certification** course (Vandal Workflow Architect). Decide on wider rollout from the evidence.',
    },
  ],
}

// ---------------------------------------------------------------------------
// Deploy / IT
// ---------------------------------------------------------------------------

const deploy: Track = {
  id: 'deploy',
  label: 'For IT & Deployment',
  tagline: 'Architecture, requirements, and your options',
  icon: Server,
  valueProps: [
    'Docker Compose stack: FastAPI, Celery, MongoDB, Redis, ChromaDB, nginx',
    'Guided setup.sh installer — admin account and starter catalog included',
    '~16 GB RAM on one server; no GPU required with a cloud LLM',
    'LLM endpoints and keys configured at runtime in the admin UI',
    'Self-hosted with encrypted secrets; on-prem / air-gapped option',
    'White-label in-app — name, logo, icon, color, and email; no redeploy',
  ],
  pitch: {
    spoken:
      "Vandalizer ships as a set of Docker containers — a FastAPI backend, Celery workers, MongoDB, Redis, and a ChromaDB vector store behind nginx. A guided setup script stands the whole thing up, including an admin account and a starter catalog. It needs about sixteen gigs of RAM on a single server, and no GPU as long as you point it at a cloud model. If you want everything on-premise you can run a local model through Ollama or vLLM, even fully air-gapped. LLM endpoints and keys are configured at runtime in the admin UI, and secrets are encrypted at rest.",
    written:
      'Vandalizer deploys as a Docker Compose stack — a FastAPI backend, Celery workers, MongoDB (application data), Redis (task broker), and a ChromaDB vector store, served behind nginx. A guided `setup.sh` installer provisions the system, an admin account, and a starter catalog; a manual compose path exists for scripted environments. It runs on a single commodity server (~16 GB RAM) with no GPU required when using a cloud LLM, or fully on-premise/air-gapped with a local model via Ollama or vLLM. LLM providers, OCR endpoints, and auth methods are configured at runtime in the admin UI, and secrets (API keys, tokens) are encrypted at rest.',
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
        '- **Local / on-prem:** Ollama or vLLM — can run fully air-gapped',
        '- **Aggregators:** OpenRouter and custom endpoints',
        '- Configured **at runtime** in the admin UI — no redeploy to change models',
      ].join('\n'),
    },
    {
      id: 'install',
      title: 'How you install it',
      body: [
        '- **Supported path:** `./setup.sh` — guided installer; creates an admin',
        '  account and seeds a starter catalog of templates',
        '- **Scripted path:** Docker Compose directly (`compose.yaml`)',
        '- Full guidance in **DEPLOY.md**',
      ].join('\n'),
    },
    {
      id: 'security',
      title: 'Security & data residency',
      body: [
        '- Self-hosted — documents and vectors stay on your infrastructure',
        '- Secrets (LLM keys, OAuth tokens) **encrypted at rest** (Fernet)',
        '- JWT sessions; OAuth (Azure AD, Google, Okta) and SAML supported',
        '- Optional M365 / Graph integration — off unless you configure it',
      ].join('\n'),
    },
    {
      id: 'ops',
      title: 'Day-2 operations',
      body: [
        '- **Back up:** MongoDB data, the uploads volume, and the ChromaDB volume',
        '- Redis is an ephemeral broker — nothing to back up',
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
      body: 'A React single-page app is served behind nginx, which proxies a FastAPI backend. The backend uses MongoDB for application data, Redis as the Celery task broker, and ChromaDB as the vector store for retrieval-augmented chat. Celery workers handle asynchronous jobs — document processing, extraction, and knowledge-base ingestion. External services are reached over HTTPS: your chosen LLM provider, optional Microsoft 365 / Graph, and an optional OCR endpoint.',
    },
    {
      id: 'requirements',
      heading: 'System requirements',
      body: 'For evaluation: 4 cores, 8–10 GB RAM, 50 GB storage — a laptop or small VM. For a department: 8 cores, 16 GB RAM, 100 GB+ storage. **No GPU is required** when using a cloud LLM; a GPU is only needed if you choose to run a large model locally. The only host prerequisites are Docker and Docker Compose.',
    },
    {
      id: 'llm',
      heading: 'LLM options',
      body: 'Vandalizer talks to any OpenAI-compatible endpoint and to Anthropic natively. For on-premise or air-gapped deployments, run a local model through **Ollama** or **vLLM**. OpenRouter and custom endpoints are also supported. Models, keys, and endpoints are configured **at runtime in the admin UI** — you can add or switch providers without a redeploy.',
    },
    {
      id: 'install',
      heading: 'Deployment options',
      body: 'The supported path is the guided installer: `./setup.sh` provisions the full stack, creates an admin account, and seeds a starter catalog. For scripted or CI environments, drive Docker Compose (`compose.yaml`) directly. **DEPLOY.md** covers production hardening, TLS, and backups.',
    },
    {
      id: 'security',
      heading: 'Security & data residency',
      body: 'Everything runs on your infrastructure, so documents and their vector embeddings never leave the institution. Secrets — LLM API keys and OAuth tokens — are encrypted at rest with a Fernet key. Sessions use JWTs; sign-in supports OAuth (Azure AD, Google, Okta) and SAML. The Microsoft 365 / Graph integration is optional and inert unless an administrator configures it. A fully air-gapped deployment is possible by pairing a local LLM with a local OCR endpoint.',
    },
    {
      id: 'ops',
      heading: 'Day-2 operations',
      body: 'Back up three things: the MongoDB data volume, the uploads volume, and the ChromaDB volume. Redis is an ephemeral broker and needs no backup. Administrators manage models, OCR endpoints, authentication methods, and **white-label branding** — organization name, logo, icon, brand color, and the styling of outgoing email — from the **/admin** console; branding is a runtime setting stored in the database, so rebranding never requires a redeploy. Every administrative action is recorded in an immutable audit log.',
    },
  ],
}

// ---------------------------------------------------------------------------
// Team / end users
// ---------------------------------------------------------------------------

const team: Track = {
  id: 'team',
  label: 'For Your Team',
  tagline: 'A quick walkthrough of what it does',
  icon: Users,
  valueProps: [
    'Upload and organize documents into folders',
    'Build an extraction workflow once, run it across a whole batch',
    'Chat with your documents — answers cited back to the source',
    'Automate processing so new files are handled on arrival',
    'Learn it through the built-in certification course',
  ],
  pitch: {
    spoken:
      "Think of Vandalizer as a smart workspace for our documents. You drop in a stack of PDFs, and instead of reading each one, you build a workflow once that pulls out exactly the fields you care about — deadlines, budgets, PI names — and run it across the whole batch. You can chat with your documents and get answers cited back to the source, organize reference material into knowledge bases, and set up automations so new files get processed the moment they arrive. There's even a built-in certification course to get you fluent.",
    written:
      'Vandalizer is a shared workspace for the documents your team works with every day. Upload PDFs, then build an extraction workflow once that pulls out exactly the fields you care about and run it across an entire batch instead of reading each file by hand. Ask plain-language questions of your documents and get answers cited to the source, organize reference material into searchable knowledge bases, and set up automations so new files are processed the moment they arrive. A built-in certification course (Vandal Workflow Architect) gets the whole team fluent.',
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
      title: '2 · Build an extraction workflow',
      body: [
        '- Define the fields you want — deadlines, budgets, PI names, terms',
        '- Chain steps together into a repeatable pipeline',
        '- Test on one document, then **run it across a whole batch**',
        '- Download results as JSON, CSV, or a ZIP',
      ].join('\n'),
    },
    {
      id: 'chat',
      title: '3 · Chat with your documents',
      body: [
        '- Ask plain-language questions across a folder or knowledge base',
        '- Every answer is **cited back to the source** document and page',
        '- Attach files or URLs for extra context',
      ].join('\n'),
    },
    {
      id: 'knowledge',
      title: '4 · Knowledge bases',
      body: [
        '- Collect documents, URLs, and notes into a reusable knowledge base',
        '- Share it with your team or keep it personal',
        '- It becomes searchable context for chat',
      ].join('\n'),
    },
    {
      id: 'automate',
      title: '5 · Automations',
      body: [
        '- **Watch a folder** and run a workflow on every new upload',
        '- Run on a **schedule**, or trigger via **API**',
        '- Intake from **Microsoft 365** when configured',
      ].join('\n'),
    },
    {
      id: 'collaborate',
      title: '6 · Work as a team',
      body: [
        '- Shared workflows, documents, and knowledge bases',
        '- Roles: owner, admin, member',
        '- **Review & sign-off** steps for work that needs approval',
      ].join('\n'),
    },
    {
      id: 'certify',
      title: '7 · Get certified',
      body: 'The built-in **Vandal Workflow Architect** course walks you from your first upload to building validated workflows — hands-on, inside the product.\n\nSign in and start: **/**',
      note: 'Offer to run a live build of one real workflow with the team.',
    },
  ],
  sections: [
    {
      id: 'upload',
      heading: 'Upload & organize',
      body: 'Drag in PDFs (plus Word, Excel, and HTML), sort them into folders, and search across everything. Vandalizer reads the text out of each file — including scanned PDFs when an OCR endpoint is configured — so it is ready to work with.',
    },
    {
      id: 'extract',
      heading: 'Extraction workflows',
      body: 'This is the core. Instead of reading every document, you define the fields you care about once — deadlines, budgets, PI names, sponsor terms — and chain steps into a repeatable pipeline. Test it on a single document, validate it against expected answers, then run it across an entire batch and download the results as JSON, CSV, or a ZIP. Workflows can be exported and shared as templates.',
    },
    {
      id: 'chat',
      heading: 'Chat with citations',
      body: 'Ask plain-language questions across a folder or a knowledge base and get answers cited back to the exact source document and page, so you can trust and verify them. Attach extra files or URLs to bring more context into the conversation.',
    },
    {
      id: 'knowledge',
      heading: 'Knowledge bases',
      body: 'Collect documents, URLs, and notes into a reusable knowledge base that becomes searchable context for chat. Keep it personal or share it with your team; administrators can curate verified knowledge bases for everyone.',
    },
    {
      id: 'automate',
      heading: 'Automations',
      body: 'Put the repetitive parts on autopilot. Watch a folder and run a workflow on every new upload, run on a schedule, trigger via API, or intake from Microsoft 365 when an administrator has configured it. Each automation keeps a log of what it processed.',
    },
    {
      id: 'collaborate',
      heading: 'Collaboration & certification',
      body: 'Teams share workflows, documents, and knowledge bases with owner / admin / member roles. Work that needs approval can route through review and sign-off steps. New users get fluent through the built-in **Vandal Workflow Architect** certification — hands-on lessons and exercises right inside the product.',
    },
  ],
}

// ---------------------------------------------------------------------------
// Researchers / PIs
// ---------------------------------------------------------------------------

const researchers: Track = {
  id: 'researchers',
  label: 'For Researchers & PIs',
  tagline: 'What it means for your proposals',
  icon: GraduationCap,
  valueProps: [
    'Faster turnaround on the documents your office processes for you',
    'Deadlines and formatting requirements surfaced automatically',
    'Ask plain-language questions of long solicitations — with citations',
    'More consistent support across submissions',
  ],
  pitch: {
    spoken:
      "When you send a proposal through our office, Vandalizer helps us turn it around faster. It reads the solicitation and your documents to surface deadlines, formatting rules, and budget requirements automatically, so nothing slips through the cracks. You — or we — can ask plain-language questions of a long funding announcement and get answers with citations, instead of scrolling through eighty pages. It means quicker, more consistent support for your submissions.",
    written:
      "Vandalizer helps your research administration office turn your proposals around faster and more consistently. It reads solicitations and supporting documents to surface deadlines, formatting rules, and budget requirements automatically, and it lets anyone ask plain-language questions of a long funding announcement and get answers cited to the source rather than scrolling through dozens of pages. The result is quicker, more reliable support for your submissions — without your data leaving the institution.",
  },
  slides: [
    {
      id: 'title',
      title: 'Vandalizer for your proposals',
      body: 'How your research administration office uses AI to support you — faster.',
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
      title: 'Ask the documents',
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
        '- Your proposals never leave our systems',
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
      body: 'When your proposal goes through the research administration office, Vandalizer helps staff surface deadlines, formatting rules, and budget requirements automatically, so the easy-to-miss details on page 60 do not slip through. Every submission gets the same rigor, which means faster and more consistent support for you.',
    },
    {
      id: 'ask',
      heading: 'Ask the documents',
      body: 'Long funding announcements are tedious to read end to end. Vandalizer lets staff (or you) ask plain-language questions of a solicitation and get answers cited back to the exact page — so the right requirement is found in seconds, with the receipts to prove it.',
    },
    {
      id: 'trust',
      heading: 'Your data stays put',
      body: 'Vandalizer is self-hosted on the institution’s own infrastructure, so your proposals and documents never leave our systems. It is open source and auditable — no black box handling your work.',
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
  return (TRACKS as Record<string, Track>)[id]
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
  }
}
