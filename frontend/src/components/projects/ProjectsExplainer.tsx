import type { ReactNode } from 'react'
import {
  FolderKanban, FolderOpen, Database, Workflow, Zap, Users,
  Sparkles, ArrowRight, FileText, type LucideIcon,
} from 'lucide-react'

/**
 * Empty-state onboarding for the Projects surfaces — mirrors the
 * Knowledge-base and Automations explainers, but light-themed to match the
 * (light) Projects page and drawer. Self-contained: drop it in wherever the
 * project list is empty.
 */
export function ProjectsExplainer() {
  return (
    <div className="mx-auto max-w-2xl py-6">
      <style>{`
        @keyframes pjFlow { 0%,100% { opacity: .5; transform: translateX(0); } 50% { opacity: 1; transform: translateX(3px); } }
        @keyframes pjArrow { 0%,100% { opacity: .35; transform: translateX(0); } 50% { opacity: 1; transform: translateX(4px); } }
        @keyframes pjPulse { 0%,100% { box-shadow: 0 0 0 0 rgba(124,58,237,.28); } 50% { box-shadow: 0 0 0 9px rgba(124,58,237,0); } }
        @keyframes pjSectionIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        .pj-section { opacity: 0; animation: pjSectionIn 480ms cubic-bezier(0.2,0.8,0.2,1) forwards; }
      `}</style>

      {/* Hero */}
      <div className="pj-section text-center" style={{ animationDelay: '40ms' }}>
        <div className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-violet-600">
          <Sparkles size={12} /> Projects
        </div>
        <h2 className="text-2xl font-bold leading-tight tracking-tight text-gray-900">
          Everything for one piece of work, in one place.
        </h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-gray-500">
          A project gathers the files, a knowledge base you can chat with, and the
          workflows, extractions, and automations that act on them — so a grant, a
          contract, or a review lives in one organized home.
        </p>
      </div>

      {/* Animated diagram */}
      <div className="pj-section mt-7" style={{ animationDelay: '160ms' }}>
        <ProjectsDiagram />
      </div>

      {/* What a project gathers */}
      <Section title="What a project gathers" delay="260ms">
        <Card
          icon={FolderOpen}
          title="Files"
          body="A dedicated folder tree for every document this work touches — uploads, drafts, and source material."
        />
        <Card
          icon={Database}
          title="A knowledge base"
          body="Turn the project's files into a knowledge base you can chat with and cite — answers grounded in this work's documents."
        />
        <Card
          icon={Workflow}
          title="Workflows & extractions"
          body="Pin the workflows and extraction templates that act on these documents so they're one click away."
        />
        <Card
          icon={Zap}
          title="Automations"
          body="Let new files trigger the right workflow automatically — results land back in the project."
        />
      </Section>

      {/* Research-admin use cases */}
      <Section
        title="Built for research administration"
        subtitle="A few of the shapes a project takes across grants, contracts, and compliance work."
        delay="360ms"
      >
        <UseCase
          accent="#7c3aed"
          label="A new grant proposal"
          body="Gather the RFP, drafts, and budget; build a KB to answer eligibility questions and pin your compliance-check workflow."
        />
        <UseCase
          accent="#2563eb"
          label="An active award"
          body="Keep award letters, reports, and correspondence together; extract terms and deadlines, and track it from active through closeout."
        />
        <UseCase
          accent="#059669"
          label="A subaward or contract"
          body="Collect the agreement and amendments, chat with the KB to find obligations, and invite the pre-award analyst as a member."
        />
        <UseCase
          accent="#d97706"
          label="An IRB protocol"
          body="Assemble protocol versions and approvals; automate validation as new documents arrive and share a read-only link with reviewers."
        />
      </Section>

      {/* How to set one up */}
      <Section title="How you'd set one up" delay="460ms">
        <Step num="1" title="Create a project" body="Give it a name. You get a dedicated folder and a home for everything related to this work." />
        <Step num="2" title="Add your files" body="Upload or move the documents this work touches into the project's folder." />
        <Step num="3" title="Build a knowledge base & pin tools" body="Turn the files into a chattable KB, and pin the workflows, extractions, and automations you'll use." />
        <Step num="4" title="Invite your team & track state" body="Add members or share a link, and move the project through draft → active → closeout as the work progresses." />
      </Section>
    </div>
  )
}

function ProjectsDiagram() {
  const inputs: { icon: LucideIcon; label: string }[] = [
    { icon: FileText, label: 'Documents' },
    { icon: FolderOpen, label: 'Files' },
    { icon: Workflow, label: 'Workflows' },
    { icon: Zap, label: 'Automations' },
  ]
  return (
    <div className="flex items-center justify-center gap-3 rounded-xl border border-gray-200 bg-gradient-to-b from-gray-50 to-white px-4 py-6 sm:gap-5 sm:px-8">
      {/* Inputs */}
      <div className="flex flex-col gap-2">
        {inputs.map((it, i) => (
          <div
            key={it.label}
            className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 shadow-sm"
            style={{ animation: 'pjFlow 2.8s ease-in-out infinite', animationDelay: `${i * 350}ms` }}
          >
            <it.icon size={13} className="text-violet-500" />
            {it.label}
          </div>
        ))}
      </div>

      {/* Connector */}
      <ArrowRight
        size={22}
        className="text-violet-400"
        style={{ animation: 'pjArrow 2.8s ease-in-out infinite' }}
      />

      {/* Project hub */}
      <div
        className="flex flex-col items-center gap-1.5 rounded-2xl border border-violet-200 bg-white px-5 py-4 text-center"
        style={{ animation: 'pjPulse 2.8s ease-in-out infinite' }}
      >
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-100">
          <FolderKanban size={22} className="text-violet-600" />
        </div>
        <div className="text-sm font-semibold text-gray-900">Project</div>
        <div className="flex items-center gap-1 text-[11px] text-gray-400">
          <Database size={11} /> KB
          <span className="mx-0.5">·</span>
          <Users size={11} /> Team
        </div>
      </div>
    </div>
  )
}

function Section({
  title, subtitle, delay, children,
}: {
  title: string; subtitle?: string; delay: string; children: ReactNode
}) {
  return (
    <div className="pj-section mt-8" style={{ animationDelay: delay }}>
      <h3 className="text-lg font-bold tracking-tight text-gray-900">{title}</h3>
      {subtitle && <p className="mt-0.5 text-sm text-gray-500">{subtitle}</p>}
      <div className="mt-3 flex flex-col gap-2.5">{children}</div>
    </div>
  )
}

function Card({ icon: Icon, title, body }: { icon: LucideIcon; title: string; body: string }) {
  return (
    <div className="flex items-start gap-3.5 rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-violet-200 bg-violet-50">
        <Icon size={17} className="text-violet-600" />
      </div>
      <div>
        <div className="text-sm font-semibold text-gray-900">{title}</div>
        <div className="mt-0.5 text-sm leading-relaxed text-gray-500">{body}</div>
      </div>
    </div>
  )
}

function UseCase({ label, body, accent }: { label: string; body: string; accent: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4" style={{ borderLeft: `3px solid ${accent}` }}>
      <div className="text-sm font-semibold text-gray-900">{label}</div>
      <div className="mt-1 text-sm leading-relaxed text-gray-500">
        <span style={{ color: accent, fontWeight: 600 }}>→ </span>{body}
      </div>
    </div>
  )
}

function Step({ num, title, body }: { num: string; title: string; body: string }) {
  return (
    <div className="flex items-start gap-3.5 rounded-xl border border-gray-200 bg-white p-3.5">
      <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-violet-600 text-[13px] font-bold text-white">
        {num}
      </div>
      <div>
        <div className="text-sm font-semibold text-gray-900">{title}</div>
        <div className="mt-0.5 text-sm leading-relaxed text-gray-500">{body}</div>
      </div>
    </div>
  )
}
