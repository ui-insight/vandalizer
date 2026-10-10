import { useMemo } from 'react'
import { BookOpen, Lightbulb, Play } from 'lucide-react'
import { renderCertificationMarkdown } from '../../lib/certificationMarkdown'
import { cn } from '../../lib/cn'
import type { LessonSection } from '../../types/certification'
import { KnowledgeCheck } from './KnowledgeCheck'
import { EditorialCorrection } from './EditorialCorrection'
import { practiceStorageKey, type PracticeScope } from '../../lib/certificationPractice'
import { HowLLMWorksDiagram } from './diagrams/HowLLMWorks'
import { AIHumanPatternDiagram } from './diagrams/AIHumanPattern'
import { AISuitabilityDiagram } from './diagrams/AISuitability'
import { ExtractReasonDeliverDiagram } from './diagrams/ExtractReasonDeliver'
import { StepGranularityDiagram } from './diagrams/StepGranularity'
import { ExtractionOutputExample } from './diagrams/ExtractionOutputExample'
import { WorkflowResultExample } from './diagrams/WorkflowResultExample'
import { ValidationPlanExample } from './diagrams/ValidationPlanExample'

const VARIANT_STYLES: Record<LessonSection['variant'], { icon: React.ComponentType<{ size?: number; className?: string }>; border: string; bg: string; label: string }> = {
  concept:     { icon: BookOpen,  border: 'border-blue-200',   bg: 'bg-blue-50/50',    label: 'Concept' },
  walkthrough: { icon: Play,      border: 'border-green-200',  bg: 'bg-green-50/50',   label: 'Walkthrough' },
  'key-terms': { icon: BookOpen,  border: 'border-purple-200', bg: 'bg-purple-50/50',  label: 'Key Terms' },
  insight:     { icon: Lightbulb, border: 'border-amber-200',  bg: 'bg-amber-50/50',   label: 'Insight' },
}

const DIAGRAM_MAP: Record<string, React.ComponentType> = {
  'how-llm-works': HowLLMWorksDiagram,
  'ai-human-pattern': AIHumanPatternDiagram,
  'ai-suitability': AISuitabilityDiagram,
  'extract-reason-deliver': ExtractReasonDeliverDiagram,
  'step-granularity': StepGranularityDiagram,
  'extraction-output-example': ExtractionOutputExample,
  'workflow-result-example': WorkflowResultExample,
  'validation-plan-example': ValidationPlanExample,
}

function GlossaryTerm({ term, definition }: { term: string; definition: string }) {
  return (
    <details className="group py-1.5" style={{ borderBottom: '1px solid #f3f4f6' }}>
      <summary className="flex items-center gap-1.5 cursor-pointer list-none select-none">
        <span className="text-[10px] text-gray-500 inline-block transition-transform group-open:rotate-90">▶</span>
        <span className="font-semibold text-sm text-gray-900">{term}</span>
      </summary>
      <p className="text-sm text-gray-600 leading-relaxed mt-1.5 ml-4">{definition}</p>
    </details>
  )
}

function parseKeyTerms(content: string): { term: string; definition: string }[] | null {
  const lines = content.split('\n\n')
  const terms: { term: string; definition: string }[] = []
  for (const line of lines) {
    const match = line.match(/^(.+?)\s*\u2014\s*(.+)$/s)
    if (match) {
      terms.push({ term: match[1].trim(), definition: match[2].trim() })
    }
  }
  return terms.length >= 2 ? terms : null
}

export function LessonContent({ section, practiceScope, manifestSha256 }: { section: LessonSection; practiceScope?: PracticeScope; manifestSha256?: string }) {
  const style = VARIANT_STYLES[section.variant]
  const Icon = style.icon

  // For key-terms variant, try to parse as collapsible terms
  const keyTerms = section.variant === 'key-terms' ? parseKeyTerms(section.content) : null

  const renderedHtml = useMemo(() => {
    if (keyTerms) return null // Will render as collapsible cards instead
    return renderCertificationMarkdown(section.content)
  }, [section.content, keyTerms])

  return (
    <div>
      <div
        className={cn('border-l-4 px-[8px] py-4 sm:p-4', style.border, style.bg)}
        style={{ borderRadius: `0 var(--ui-radius, 12px) var(--ui-radius, 12px) 0` }}
      >
        <div className="flex items-center gap-2 mb-2">
          <Icon size={14} className="text-gray-500 shrink-0" />
          <span className="text-[11px] font-bold uppercase tracking-wider text-gray-500">
            {style.label}
          </span>
        </div>
        <h4 className="text-sm font-bold text-gray-900 mb-1">{section.title}</h4>
        {section.objective && (
          <p className="text-xs italic text-gray-500 mb-2">{section.objective}</p>
        )}
        <EditorialCorrection manifestSha256={manifestSha256} lessonId={section.id} content={section.content} />

        {keyTerms ? (
          <div>
            {keyTerms.map((kt, i) => (
              <GlossaryTerm key={i} term={kt.term} definition={kt.definition} />
            ))}
          </div>
        ) : (
          <div
            className="text-sm text-gray-700 leading-relaxed cert-lesson-markdown"
            dangerouslySetInnerHTML={{ __html: renderedHtml! }}
          />
        )}

      </div>
      <LessonExtras diagram={section.diagram} knowledgeCheck={section.knowledgeCheck} practiceScope={practiceScope} />
    </div>
  )
}


const DIAGRAM_TEXT: Record<string, string> = {
  'how-llm-works': 'Training text supplies patterns. During training the model learns those patterns; when prompted, it generates text from them. Generated text still needs verification.',
  'ai-human-pattern': 'AI reads documents, extracts data and produces structured output. A human reviews the results, applies judgment and makes decisions.',
  'ai-suitability': 'Ask whether the task is repetitive, document-based and rule-based. These traits suggest a candidate for AI assistance; tasks outside that pattern need further human judgment.',
  'extract-reason-deliver': 'Extract structured data, reason over that data, then deliver useful output. Each stage has a distinct job.',
  'step-granularity': 'One large step is hard to debug. Too many tiny steps add unnecessary complexity. Aim for a clear purpose per step, such as extraction, analysis and delivery.',
  'extraction-output-example': 'The example below pairs extracted field names with their values. Read each value against its source before relying on the structured output.',
  'workflow-result-example': 'The example below shows each workflow stage and the output it contributes to the next stage.',
  'validation-plan-example': 'The example below lists validation checks and distinguishes passed, failed and review-needed results in text.',
}

/** Shared practice and illustrations for chat and the learning panel. */
export function LessonExtras({ diagram, knowledgeCheck, practiceScope, practiceDisabled = false }: Pick<LessonSection, 'diagram' | 'knowledgeCheck'> & { practiceScope?: PracticeScope; practiceDisabled?: boolean }) {
  const Diagram = diagram ? DIAGRAM_MAP[diagram] : null
  const storageKey = practiceStorageKey(practiceScope)
  return <>
    {Diagram && <figure className="mt-4 min-w-0">
      <figcaption className="mb-2 text-sm leading-relaxed text-gray-700">{DIAGRAM_TEXT[diagram!]}</figcaption>
      <div className="overflow-auto [&>*]:min-w-[480px]" role="region" aria-label="Lesson diagram" tabIndex={0}><Diagram /></div>
    </figure>}
    {knowledgeCheck && <fieldset disabled={practiceDisabled} className="min-w-0 border-0 p-0"><KnowledgeCheck key={`${storageKey}:${JSON.stringify(knowledgeCheck)}`} data={knowledgeCheck} storageKey={storageKey} /></fieldset>}
  </>
}
