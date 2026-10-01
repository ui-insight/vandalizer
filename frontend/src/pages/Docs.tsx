import { useState, useEffect, useRef, type ComponentType } from 'react'
import { Link } from '@tanstack/react-router'
import { FocusTrap } from '../components/shared/PanelFocusTrap'
import { Footer } from '../components/layout/Footer'
import { PresentSidebar } from './present/components/PresentSidebar'
import { CostEstimator } from './docs/CostEstimator'
import {
  BookOpen,
  Server,
  FileText,
  Settings,
  Layers,
  Code,
  Calculator,
  GitPullRequest,
  GraduationCap,
  ExternalLink,
  Menu,
  X,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Section data
// ---------------------------------------------------------------------------

const sections = [
  { id: 'getting-started', label: 'Getting Started', icon: BookOpen },
  { id: 'user-guide', label: 'Task examples', icon: FileText },
  { id: 'installation', label: 'Installation & Self-Hosting', icon: Server },
  { id: 'administration', label: 'Administration', icon: Settings },
  { id: 'cost-estimator', label: 'Cost Estimator', icon: Calculator },
  { id: 'architecture', label: 'Architecture', icon: Layers },
  { id: 'api-reference', label: 'API Reference', icon: Code },
  { id: 'contributing', label: 'Contributing', icon: GitPullRequest },
  { id: 'about', label: 'About & Funding', icon: GraduationCap },
] as const

type SectionId = (typeof sections)[number]['id']

// ---------------------------------------------------------------------------
// Inline section components
// ---------------------------------------------------------------------------

function GettingStarted() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">Review a proposal with its sources</h2>
      <p className="text-gray-300 text-lg leading-relaxed">
        Start with a sponsor notice or proposal you are allowed to use. Find a requirement,
        inspect the supporting passage, then reuse the check or hand the result to a colleague.
        Training is optional; you can begin in the workspace.
      </p>
      <ol className="space-y-5 list-decimal pl-6 text-gray-300">
        <li><strong className="text-white">Open your source.</strong> In Files, upload a document and wait for processing.
          Open it to confirm the text is readable. If text is missing, resolve that before relying on an answer.</li>
        <li><strong className="text-white">Ask a specific question.</strong> In Chat, confirm the selected documents or
          knowledge base. Try: “What is the submission deadline, including time zone? Show the supporting passage.”</li>
        <li><strong className="text-white">Check the evidence.</strong> Open the answer’s source reference and compare it
          with the document. Check dates, conditions and conflicting passages. An answer without support needs review.</li>
        <li><strong className="text-white">Reuse a check.</strong> Keep the file open and choose a workflow or extraction
          from Library. Review its inputs before Run. A workflow combines tasks; an extraction returns named fields,
          such as deadline and budget limit.</li>
        <li><strong className="text-white">Hand off with context.</strong> Use the result’s copy/export action where available,
          include the source and unresolved questions, and share through your team’s usual process. Workflows with a
          human-review step send an item to Reviews for the assigned colleague.</li>
      </ol>
      <div className="flex flex-wrap gap-4">
        <a href="/" className="rounded-lg bg-[#f1b300] px-4 py-3 font-semibold text-black">Open workspace</a>
        <a href="#user-guide" className="py-3 text-[#f1b300] underline">Task examples and recovery</a>
      </div>
      <p className="text-sm text-gray-400">Setting up a deployment? See <a href="#installation" className="underline">Installation &amp; Self-Hosting</a>.</p>
    </div>
  )
}

function Installation() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">Installation & Self-Hosting</h2>
      <p className="text-gray-300 text-lg leading-relaxed">
        Vandalizer is designed for self-hosted deployments. You control your data, your models, and
        your infrastructure.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Environment Variables</h3>
      <p className="text-gray-400 text-sm mb-4">
        Copy{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
          .env.example
        </code>{' '}
        to{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">.env</code> and
        configure the following:
      </p>
      <div tabIndex={0} role="region" aria-label="Scrollable documentation example" className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="border-b border-white/10 text-gray-400">
              <th className="py-2 pr-4 font-medium">Variable</th>
              <th className="py-2 pr-4 font-medium">Required</th>
              <th className="py-2 font-medium">Description</th>
            </tr>
          </thead>
          <tbody className="text-gray-300">
            {[
              ['MONGO_HOST', 'Yes', 'MongoDB connection string'],
              ['MONGO_DB', 'Yes', 'Database name (default: osp)'],
              ['REDIS_HOST', 'Yes', 'Redis connection host'],
              ['JWT_SECRET_KEY', 'Yes', 'Secret for JWT authentication'],
            ].map(([name, req, desc]) => (
              <tr key={name} className="border-b border-white/5">
                <td className="py-2 pr-4">
                  <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
                    {name}
                  </code>
                </td>
                <td className="py-2 pr-4">{req}</td>
                <td className="py-2 text-gray-400">{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-gray-400 text-sm mt-3">
        LLM models, API keys, and endpoints are configured per-model in Admin &rarr; System Config.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Docker Compose (Recommended)</h3>
      <div tabIndex={0} role="region" aria-label="Command example" className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div className="text-gray-400"># Start all infrastructure services</div>
        <div>docker compose up -d redis mongo chromadb</div>
        <div className="mt-3 text-gray-400"># Start the backend</div>
        <div>make backend-install && cd backend && uv run uvicorn app.main:app --reload --port 8001</div>
        <div className="mt-3 text-gray-400"># Start Celery workers</div>
        <div>./run_celery.sh start</div>
        <div className="mt-3 text-gray-400"># Start the frontend</div>
        <div>cd frontend && npm install && npm run dev</div>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Production Deployment</h3>
      <p className="text-gray-300 leading-relaxed">
        For production, use uvicorn with multiple workers:
      </p>
      <div tabIndex={0} role="region" aria-label="Command example" className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div>uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4 <span className="text-gray-400"># Production uvicorn server</span></div>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Infrastructure Requirements</h3>
      <ul className="space-y-1 text-gray-300 text-sm">
        <li>
          <span className="text-[#f1b300]">&#x2022;</span>{' '}
          <strong className="text-white">MongoDB</strong>: document storage and system
          configuration
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span>{' '}
          <strong className="text-white">Redis</strong>: Celery broker, result backend, and
          LLM response caching
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span>{' '}
          <strong className="text-white">ChromaDB</strong>: vector store for document
          embeddings (RAG)
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span>{' '}
          <strong className="text-white">Pandoc + pdflatex</strong>: DOCX to PDF conversion
          (optional)
        </li>
      </ul>
    </div>
  )
}

function UserGuide() {
  const examples = [
    { id: 'project-scope', title: 'Check a proposal in a project', text: 'Open Projects and select the project. Confirm the project name and the documents included in Chat before asking about the proposal. Project membership controls access; a project selection does not establish that every document is readable.' },
    { id: 'library-tools', title: 'Choose a reusable Library tool', text: 'Keep the document in Files, open Library, and inspect the tool’s description and required input. Use an extraction for named values such as “Budget limit”; use a workflow for a sequence such as summarize, compare and request review. A shared tool still needs checking against your sponsor and document.' },
    { id: 'validation', title: 'Check a tool before relying on it', text: 'In the tool’s Validate section, supply representative examples and expected results. Run the check and inspect failures against the source. A completed run means execution finished; validation evidence only describes the examples tested. Tuning proposals do not establish correctness on new documents.' },
    { id: 'human-review', title: 'Review output for a colleague', text: 'Open Reviews, select an assigned item and read its instructions, sources and proposed output. Edit before approving when a correction is needed and explain unresolved issues in comments. Approval records a workflow decision; it does not publish a proposal or certify compliance.' },
    { id: 'status-meanings', title: 'Understand status and quality labels', text: 'Shared or accepted means an item is available to its permitted audience. Checked or validated describes recorded test evidence; open the results to inspect scope, failures and expected answers. Available or ready describes access and processing state. Completed means execution finished. Approved in Reviews records a human decision and may allow the workflow to continue; inspect its subsequent status. None of these labels establishes correctness on a new document or certifies compliance.' },
    { id: 'source-recovery', title: 'Recover from missing or incomplete sources', text: 'If a file is still processing, wait for its status to update. Open the extracted text and compare it with the original. If a scan or table is incomplete, use a readable version or ask for help through Support. In Knowledge, review source health before asking questions. Never interpret a missing answer as proof that the requirement is absent.' },
  ]
  return <div className="space-y-6">
    <h2 className="text-3xl font-bold text-white">Task examples and recovery</h2>
    {examples.map(example => <section key={example.id} id={example.id} tabIndex={-1} className="scroll-mt-24 space-y-2">
      <h3 className="text-xl font-bold text-white">{example.title}</h3>
      <p className="text-gray-300 leading-relaxed">{example.text}</p>
    </section>)}
    <a href="/" className="inline-flex text-[#f1b300] underline">Return to workspace</a>
  </div>
}

function Administration() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">Administration</h2>

      <h3 className="text-xl font-bold text-white mt-8">System Configuration</h3>
      <p className="text-gray-300 leading-relaxed">
        Vandalizer uses a three-level configuration system. The{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
          SystemConfig
        </code>{' '}
        MongoDB document provides runtime-editable settings for LLM models, authentication methods,
        extraction configuration, and UI theming. Admins can modify these through the admin panel
        without restarting the server.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Customization &amp; Branding</h3>
      <p className="text-gray-300 leading-relaxed">
        Vandalizer white-labels to your institution. Under{' '}
        <strong className="text-white">System Config &rarr; UI Theme &amp; Branding</strong>, an admin
        can set the <strong className="text-white">organization name</strong> (shown in the header,
        sign-in page, browser tab, and chat greeting), upload a{' '}
        <strong className="text-white">logo</strong> and a square{' '}
        <strong className="text-white">icon</strong> (the icon also becomes the browser-tab favicon),
        and choose a <strong className="text-white">brand color</strong> that threads through the UI
        and the styling of outgoing email. These values are stored in{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">SystemConfig</code>{' '}
        and served by a public theme endpoint, so they apply at runtime with no rebuild or redeploy.
        On a branded deployment the default Joe Vandal mark is hidden unless you upload your own icon,
        and the footer keeps a small &ldquo;Powered by Vandalizer&rdquo; credit and the NSF GRANTED
        acknowledgement, as required by the GPL v3 license.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">User & Team Management</h3>
      <p className="text-gray-300 leading-relaxed">
        Administrators can manage users, teams, and team memberships through the admin interface.
        Supported authentication methods include password-based login and Azure OAuth, configurable
        at the system level.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Monitoring with Celery Flower</h3>
      <p className="text-gray-300 leading-relaxed mb-4">
        Celery Flower provides a real-time web UI for monitoring task queues, worker status, and task
        history. It is started automatically with the Celery workers:
      </p>
      <div tabIndex={0} role="region" aria-label="Command example" className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div>./run_celery.sh start &nbsp; <span className="text-gray-400"># Starts workers + Flower</span></div>
        <div>./run_celery.sh status &nbsp;<span className="text-gray-400"># Check worker status</span></div>
        <div>./run_celery.sh logs &nbsp;&nbsp; <span className="text-gray-400"># Tail all worker logs</span></div>
      </div>
    </div>
  )
}

function Architecture() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">Architecture</h2>

      <h3 className="text-xl font-bold text-white mt-8">System Overview</h3>
      <div tabIndex={0} role="region" aria-label="Command example" className="bg-[#262626] rounded-lg p-4 font-mono text-xs sm:text-sm text-gray-300 overflow-x-auto leading-relaxed">
        <pre>{`┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│   React     │────▶│  FastAPI    │────▶│   MongoDB    │
│   Frontend  │     │  Backend    │     │              │
└─────────────┘     └──────┬──────┘     └──────────────┘
                           │
                    ┌──────┴──────┐
                    │   Celery    │
                    │   Workers   │
                    └──────┬──────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  Redis   │ │ ChromaDB │ │   LLM    │
        │  Cache   │ │ Vectors  │ │   APIs   │
        └──────────┘ └──────────┘ └──────────┘`}</pre>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Data Model</h3>
      <p className="text-gray-300 leading-relaxed">
        All data models are defined in{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
          backend/app/models/
        </code>{' '}
        using Beanie ODM (Pydantic v2). Key models include{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
          SmartDocument
        </code>
        ,{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">Workflow</code>
        ,{' '}
        and{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">Team</code>.
        Documents, workflows, and folders are scoped by team for multi-tenancy.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">LLM Layer</h3>
      <p className="text-gray-300 leading-relaxed">
        The LLM integration uses pydantic-ai agents with OpenAI-compatible protocol detection and
        Redis-backed response caching. Extraction logic supports configurable one-pass and two-pass
        strategies via{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
          SystemConfig.extraction_config
        </code>
        .
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Document Pipeline</h3>
      <p className="text-gray-300 leading-relaxed">
        Documents are processed through a multi-stage pipeline: upload validation (Celery chord),
        text extraction (PyMuPDF, pypandoc, markitdown), chunking, and ChromaDB embedding. Supported
        formats include PDF, DOCX, XLSX, and HTML.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Workflow Engine</h3>
      <p className="text-gray-300 leading-relaxed">
        Workflows use a ThreadPoolExecutor for parallel step execution with graphlib-based dependency
        resolution. Each workflow is a DAG of steps that can branch, merge, and pass outputs between
        tasks.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Task Queues</h3>
      <p className="text-gray-300 leading-relaxed mb-4">
        Celery manages four named queues for async task processing:
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {[
          ['uploads', '2 workers', 'Document upload validation'],
          ['documents', '3 workers', 'Text extraction & embedding'],
          ['workflows', '2 workers', 'Workflow step execution'],
          ['default', '1 worker', 'General background tasks'],
        ].map(([queue, workers, desc]) => (
          <div key={queue} className="bg-[#262626] rounded-lg p-3 border border-white/5">
            <div className="flex items-center justify-between mb-1">
              <code className="text-[#f1b300] text-sm font-bold">{queue}</code>
              <span className="text-xs text-gray-400">{workers}</span>
            </div>
            <p className="text-gray-400 text-xs">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function ApiReference() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">API Reference</h2>
      <p className="text-gray-300 text-lg leading-relaxed">
        The Vandalizer backend exposes a RESTful API organized into router-based route groups.
        Interactive API documentation is available via Swagger UI at{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
          /docs
        </code>{' '}
        when the server is running.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">API Groups</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {[
          ['auth', 'Authentication & OAuth'],
          ['files', 'Document upload & management'],
          ['workflows', 'Workflow CRUD & execution'],
          ['teams', 'Team & membership management'],
          ['library', 'Shared library items'],
          ['tasks', 'Celery task status'],
          ['admin', 'System configuration'],
          ['chat', 'RAG chat conversations'],
          ['office', 'Office document handling'],
        ].map(([name, desc]) => (
          <div key={name} className="flex items-start gap-3 text-sm">
            <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs shrink-0">
              /{name}
            </code>
            <span className="text-gray-400">{desc}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Contributing() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">Contributing</h2>
      <p className="text-gray-300 text-lg leading-relaxed">
        We welcome contributions from the community! Please read the full{' '}
        <a
          href="https://github.com/ui-insight/vandalizer/blob/main/CONTRIBUTING.md"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#f1b300] underline hover:no-underline"
        >
          Contributing Guide
        </a>{' '}
        for details.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Development Setup</h3>
      <div tabIndex={0} role="region" aria-label="Command example" className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div className="text-gray-400"># Backend</div>
        <div>cp backend/.env.example backend/.env && make backend-install</div>
        <div>docker compose up -d redis mongo chromadb</div>
        <div>cd backend && uv run uvicorn app.main:app --reload --port 8001</div>
        <div className="mt-3 text-gray-400"># Frontend</div>
        <div>cd frontend && npm install && npm run dev</div>
        <div className="mt-3 text-gray-400"># Celery workers</div>
        <div>./run_celery.sh start</div>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Conventions</h3>
      <ul className="space-y-1 text-gray-300 text-sm">
        <li>
          <span className="text-[#f1b300]">&#x2022;</span> Python: use{' '}
          <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
            devtools.debug()
          </code>{' '}
          instead of{' '}
          <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">print()</code>
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span> Package management via{' '}
          <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">uv</code>
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span> Frontend: React 19, Tailwind CSS v4,
          TanStack Router
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span> Celery tasks use{' '}
          <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
            bind=True
          </code>{' '}
          and{' '}
          <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
            autoretry_for
          </code>{' '}
          patterns
        </li>
      </ul>

      <h3 className="text-xl font-bold text-white mt-8">Pull Request Process</h3>
      <ol className="space-y-1 text-gray-300 text-sm list-decimal list-inside">
        <li>Fork the repository and create a feature branch</li>
        <li>Make your changes with clear, descriptive commits</li>
        <li>
          Ensure tests pass:{' '}
          <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">
            make ci
          </code>
        </li>
        <li>Submit a pull request against the main branch</li>
      </ol>

      <h3 className="text-xl font-bold text-white mt-8">Testing</h3>
      <p className="text-gray-300 leading-relaxed">
        Tests use pytest with httpx for API testing. Run{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">make ci</code>{' '}
        for the full test suite or{' '}
        <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">make backend-test</code>{' '}
        for backend tests only.
      </p>
    </div>
  )
}

function About() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">About & Funding</h2>

      <p className="text-gray-300 text-lg leading-relaxed">
        Vandalizer is an open-source AI-powered document intelligence platform for research
        administration, originally developed at the University of Idaho as part of the{' '}
        <a
          href="https://www.nsf.gov/awardsearch/showAward?AWD_ID=2427549"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#f1b300] underline hover:no-underline"
        >
          NSF GRANTED program
        </a>.
      </p>

      <div className="bg-[#262626] rounded-lg p-6 border border-white/5">
        <h3 className="text-lg font-bold text-white mb-3">NSF Acknowledgment</h3>
        <p className="text-gray-400 text-sm leading-relaxed">
          This material is based upon work supported by the National Science Foundation under Award
          No. 2427549. Any opinions, findings, and conclusions or recommendations expressed in this
          material are those of the author(s) and do not necessarily reflect the views of the
          National Science Foundation.
        </p>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Contributing</h3>
      <p className="text-gray-300 leading-relaxed">
        Vandalizer is open source and welcomes contributions. Whether you're a researcher,
        developer, or research administrator, check out the GitHub repository to get started.
      </p>

      <div className="flex flex-wrap gap-4 mt-8">
        <a
          href="https://github.com/ui-insight/vandalizer"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-300 hover:text-[#f1b300] hover:border-[#f1b300]/30 transition-colors"
        >
          GitHub Repository <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section component map
// ---------------------------------------------------------------------------

const sectionComponents: Record<SectionId, ComponentType> = {
  'getting-started': GettingStarted,
  installation: Installation,
  'user-guide': UserGuide,
  administration: Administration,
  'cost-estimator': CostEstimator,
  architecture: Architecture,
  'api-reference': ApiReference,
  contributing: Contributing,
  about: About,
}

// ---------------------------------------------------------------------------
// Docs page
// ---------------------------------------------------------------------------

export default function Docs() {
  const [activeSection, setActiveSection] = useState<SectionId>(sections[0].id)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const sectionRefs = useRef<Map<string, HTMLElement>>(new Map())

  // IntersectionObserver for active section tracking
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id as SectionId)
          }
        }
      },
      { rootMargin: '-96px 0px -60% 0px', threshold: 0 },
    )

    for (const el of sectionRefs.current.values()) {
      observer.observe(el)
    }

    return () => observer.disconnect()
  }, [])

  return (
    <div className="landing-page bg-[#0a0a0a] text-gray-200 antialiased w-full min-h-screen [overflow-wrap:anywhere]">
      {/* Fixed top nav */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
            <Link to="/landing" search={{ error: undefined, invite_token: undefined, admin: undefined, next: undefined, register: undefined }} className="text-xl font-bold text-white hover:text-[#f1b300] transition-colors">
              Vandalizer
            </Link>
            <span className="text-sm text-[#f1b300] font-medium">Docs</span>
          </div>
          <div className="flex shrink-0 items-center gap-4">
            <a
              href="https://github.com/ui-insight/vandalizer"
              target="_blank"
              rel="noopener noreferrer"
              className="hidden sm:inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-[#f1b300] transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              GitHub
            </a>
            {/* Mobile TOC toggle */}
            <button
              aria-label={mobileMenuOpen ? 'Close documentation navigation' : 'Open documentation navigation'}
              aria-expanded={mobileMenuOpen}
              aria-controls="docs-mobile-navigation"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="lg:hidden p-2 text-gray-400 hover:text-white"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile TOC drawer */}
      {mobileMenuOpen && (
        <FocusTrap focusTrapOptions={{ escapeDeactivates: false, delayInitialFocus: false }}>
        <div role="dialog" aria-modal="true" aria-label="Documentation navigation" onKeyDown={e => { if (e.key === 'Escape') setMobileMenuOpen(false) }} className="fixed inset-0 z-40 bg-black/80 lg:hidden" onClick={() => setMobileMenuOpen(false)}>
          <div
            id="docs-mobile-navigation"
            className="absolute top-16 right-0 bottom-0 w-72 max-w-full bg-[#0a0a0a] border-l border-white/10 overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <button type="button" className="mb-4 p-2 text-gray-200" onClick={() => setMobileMenuOpen(false)}>Close navigation</button>
            <div className="mb-4">
              <PresentSidebar onNavigate={() => setMobileMenuOpen(false)} />
            </div>
            <nav className="space-y-1">
              {sections.map((s) => {
                const Icon = s.icon
                return (
                  <a
                    key={s.id}
                    href={`#${s.id}`}
                    onClick={() => setMobileMenuOpen(false)}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                      activeSection === s.id
                        ? 'bg-[#f1b300]/10 text-[#f1b300]'
                        : 'text-gray-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    {s.label}
                  </a>
                )
              })}
            </nav>
          </div>
        </div>
        </FocusTrap>
      )}

      <div className="pt-16 flex max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Sticky sidebar TOC — desktop only */}
        <aside className="hidden lg:block w-64 shrink-0 pr-8">
          <div className="sticky top-24 space-y-4">
            <PresentSidebar />
            <hr className="border-white/10" />
            <nav className="space-y-1">
              {sections.map((s) => {
              const Icon = s.icon
              return (
                <a
                  key={s.id}
                  href={`#${s.id}`}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                    activeSection === s.id
                      ? 'bg-[#f1b300]/10 text-[#f1b300]'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  {s.label}
                </a>
              )
              })}
            </nav>
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 min-w-0 py-12">
          <div className="space-y-16">
            {sections.map((s) => {
              const SectionComponent = sectionComponents[s.id]
              return (
                <section
                  key={s.id}
                  id={s.id}
                  tabIndex={-1}
                  className="scroll-mt-24 glass-panel rounded-xl p-6 sm:p-8 border border-white/5"
                  ref={(el) => {
                    if (el) sectionRefs.current.set(s.id, el)
                  }}
                >
                  <SectionComponent />
                </section>
              )
            })}
          </div>
        </main>
      </div>

      <Footer />
    </div>
  )
}
