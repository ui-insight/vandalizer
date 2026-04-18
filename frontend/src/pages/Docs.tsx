import { useState, useEffect, useRef, type ComponentType } from 'react'
import { Link } from '@tanstack/react-router'
import { Footer } from '../components/layout/Footer'
import {
  BookOpen,
  Server,
  FileText,
  Settings,
  Layers,
  Code,
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
  { id: 'installation', label: 'Installation & Self-Hosting', icon: Server },
  { id: 'user-guide', label: 'User Guide', icon: FileText },
  { id: 'administration', label: 'Administration', icon: Settings },
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
      <h2 className="text-3xl font-bold text-white">Getting Started</h2>
      <p className="text-gray-300 text-lg leading-relaxed">
        Vandalizer is an open-source, AI-powered document intelligence platform built for research
        administration. Upload documents, run LLM-powered extraction workflows, chat with your
        documents via RAG, and collaborate across teams.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Capabilities</h3>
      <ul className="space-y-2 text-gray-300">
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">Structured Extraction</strong> &mdash; Pull dates,
            budgets, requirements, and more from PDFs into clean structured data
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">Workflow Engine</strong> &mdash; Chain extraction tasks
            into repeatable pipelines with dependency resolution
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">RAG Chat</strong> &mdash; Ask questions against your
            document collection with citation-backed answers
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">Team Collaboration</strong> &mdash; Multi-tenant
            workspaces with role-based access and shared libraries
          </span>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-[#f1b300] mt-1">&#x2022;</span>
          <span>
            <strong className="text-white">Self-Hosted</strong> &mdash; Run on your own
            infrastructure with full control over your data
          </span>
        </li>
      </ul>

      <h3 className="text-xl font-bold text-white mt-8">Quickstart</h3>
      <div className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div className="text-gray-500"># Clone the repository</div>
        <div>
          git clone https://github.com/ui-insight/vandalizer.git && cd vandalizer
        </div>
        <div className="mt-3 text-gray-500"># Start infrastructure</div>
        <div>docker compose up -d redis mongo chromadb</div>
        <div className="mt-3 text-gray-500"># Install backend dependencies & run</div>
        <div>cp backend/.env.example backend/.env && make backend-install && cd backend && uv run uvicorn app.main:app --reload --port 8001</div>
        <div className="mt-3 text-gray-500"># In another terminal — start frontend</div>
        <div>cd frontend && npm install && npm run dev</div>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Prerequisites</h3>
      <ul className="space-y-1 text-gray-300 text-sm">
        <li>
          <span className="text-[#f1b300]">&#x2022;</span> Python &ge; 3.11, &lt; 3.13
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span> Node.js &ge; 20
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span> Docker & Docker Compose
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span>{' '}
          <code className="bg-white/10 text-[#f1b300] px-1.5 py-0.5 rounded text-xs">uv</code>{' '}
          package manager
        </li>
      </ul>
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
      <div className="overflow-x-auto">
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
      <div className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div className="text-gray-500"># Start all infrastructure services</div>
        <div>docker compose up -d redis mongo chromadb</div>
        <div className="mt-3 text-gray-500"># Start the backend</div>
        <div>make backend-install && cd backend && uv run uvicorn app.main:app --reload --port 8001</div>
        <div className="mt-3 text-gray-500"># Start Celery workers</div>
        <div>./run_celery.sh start</div>
        <div className="mt-3 text-gray-500"># Start the frontend</div>
        <div>cd frontend && npm install && npm run dev</div>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Production Deployment</h3>
      <p className="text-gray-300 leading-relaxed">
        For production, use uvicorn with multiple workers:
      </p>
      <div className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div>uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4 <span className="text-gray-500"># Production uvicorn server</span></div>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Infrastructure Requirements</h3>
      <ul className="space-y-1 text-gray-300 text-sm">
        <li>
          <span className="text-[#f1b300]">&#x2022;</span>{' '}
          <strong className="text-white">MongoDB</strong> &mdash; Document storage and system
          configuration
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span>{' '}
          <strong className="text-white">Redis</strong> &mdash; Celery broker, result backend, and
          LLM response caching
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span>{' '}
          <strong className="text-white">ChromaDB</strong> &mdash; Vector store for document
          embeddings (RAG)
        </li>
        <li>
          <span className="text-[#f1b300]">&#x2022;</span>{' '}
          <strong className="text-white">Pandoc + pdflatex</strong> &mdash; DOCX to PDF conversion
          (optional)
        </li>
      </ul>
    </div>
  )
}

function UserGuide() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">User Guide</h2>

      <h3 className="text-xl font-bold text-white mt-8">Uploading Documents</h3>
      <p className="text-gray-300 leading-relaxed">
        Drag and drop files into the workspace or use the upload button. Supported formats include
        PDF, DOCX, XLSX, and HTML. Documents are processed asynchronously &mdash; text is extracted,
        chunked, and embedded into ChromaDB for RAG search.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Extractions</h3>
      <p className="text-gray-300 leading-relaxed mb-4">
        Vandalizer supports two extraction strategies:
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-[#262626] rounded-lg p-5 border border-white/5">
          <h4 className="text-white font-bold mb-2">One-Pass Extraction</h4>
          <p className="text-gray-400 text-sm leading-relaxed">
            A single LLM call produces structured output directly from the document. Fast and
            efficient for straightforward extraction tasks.
          </p>
        </div>
        <div className="bg-[#262626] rounded-lg p-5 border border-white/5">
          <h4 className="text-white font-bold mb-2">Two-Pass Extraction</h4>
          <p className="text-gray-400 text-sm leading-relaxed">
            A &ldquo;thinking&rdquo; draft pass followed by a structured final extraction. Higher
            accuracy for complex documents with nuanced requirements.
          </p>
        </div>
      </div>

      <h3 className="text-xl font-bold text-white mt-8">Chat & RAG</h3>
      <p className="text-gray-300 leading-relaxed">
        The chat interface lets you ask questions against your uploaded documents. Vandalizer uses
        Retrieval-Augmented Generation to find relevant document chunks and generate citation-backed
        answers. Conversations are persisted and can be continued later.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Library</h3>
      <p className="text-gray-300 leading-relaxed">
        Save and organize reusable prompts, extraction templates, and workflow configurations in the
        Library. Library items can be shared across your team.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Teams</h3>
      <p className="text-gray-300 leading-relaxed">
        Organize work into Teams. Teams provide role-based access control
        (owner/admin/member) and scope documents, workflows, and folders for
        multi-tenant collaboration.
      </p>
    </div>
  )
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
      <div className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div>./run_celery.sh start &nbsp; <span className="text-gray-500"># Starts workers + Flower</span></div>
        <div>./run_celery.sh status &nbsp;<span className="text-gray-500"># Check worker status</span></div>
        <div>./run_celery.sh logs &nbsp;&nbsp; <span className="text-gray-500"># Tail all worker logs</span></div>
      </div>
    </div>
  )
}

function Architecture() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold text-white">Architecture</h2>

      <h3 className="text-xl font-bold text-white mt-8">System Overview</h3>
      <div className="bg-[#262626] rounded-lg p-4 font-mono text-xs sm:text-sm text-gray-300 overflow-x-auto leading-relaxed">
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
              <span className="text-xs text-gray-500">{workers}</span>
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
          className="text-[#f1b300] hover:underline"
        >
          Contributing Guide
        </a>{' '}
        for details.
      </p>

      <h3 className="text-xl font-bold text-white mt-8">Development Setup</h3>
      <div className="bg-[#262626] rounded-lg p-4 font-mono text-sm text-gray-300 overflow-x-auto">
        <div className="text-gray-500"># Backend</div>
        <div>cp backend/.env.example backend/.env && make backend-install</div>
        <div>docker compose up -d redis mongo chromadb</div>
        <div>cd backend && uv run uvicorn app.main:app --reload --port 8001</div>
        <div className="mt-3 text-gray-500"># Frontend</div>
        <div>cd frontend && npm install && npm run dev</div>
        <div className="mt-3 text-gray-500"># Celery workers</div>
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
          className="text-[#f1b300] hover:underline"
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
    <div className="landing-page bg-[#0a0a0a] text-gray-200 antialiased w-full min-h-screen">
      {/* Fixed top nav */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <div className="flex items-center gap-6">
            <Link to="/landing" search={{ error: undefined, invite_token: undefined, admin: undefined }} className="text-xl font-bold text-white hover:text-[#f1b300] transition-colors">
              Vandalizer
            </Link>
            <span className="text-sm text-[#f1b300] font-medium">Docs</span>
          </div>
          <div className="flex items-center gap-4">
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
        <div className="fixed inset-0 z-40 bg-black/80 lg:hidden" onClick={() => setMobileMenuOpen(false)}>
          <div
            className="absolute top-16 right-0 w-72 bg-[#0a0a0a] border-l border-white/10 h-full overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
          >
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
      )}

      <div className="pt-16 flex max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Sticky sidebar TOC — desktop only */}
        <aside className="hidden lg:block w-64 shrink-0 pr-8">
          <nav className="sticky top-24 space-y-1">
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
