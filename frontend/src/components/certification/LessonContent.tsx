import { useMemo, useState } from 'react'
import { BookOpen, ChevronDown, ChevronRight, Lightbulb, Play } from 'lucide-react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { cn } from '../../lib/cn'
import type { LessonSection } from '../../types/certification'
import { KnowledgeCheck } from './KnowledgeCheck'
import { HowLLMWorksDiagram } from './diagrams/HowLLMWorks'
import { AIHumanPatternDiagram } from './diagrams/AIHumanPattern'
import { AISuitabilityDiagram } from './diagrams/AISuitability'
import { ExtractReasonDeliverDiagram } from './diagrams/ExtractReasonDeliver'
import { StepGranularityDiagram } from './diagrams/StepGranularity'

marked.setOptions({ breaks: true, gfm: true })

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
}

function CollapsibleTerm({ term, definition }: { term: string; definition: string }) {
  const [open, setOpen] = useState(false)

  return (
    <button
      onClick={() => setOpen(!open)}
      className={cn(
        'w-full text-left p-3 border transition-all',
        open ? 'border-purple-300 bg-purple-50/50' : 'border-gray-200 bg-white hover:border-purple-200',
      )}
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      <div className="flex items-center justify-between">
        <span className="font-semibold text-sm text-gray-900">{term}</span>
        {open ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}
      </div>
      <div className={cn('thinking-collapse', open && 'open')}>
        <div>
          <p className="text-sm text-gray-600 mt-2 leading-relaxed">{definition}</p>
        </div>
      </div>
    </button>
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

export function LessonContent({ section }: { section: LessonSection }) {
  const style = VARIANT_STYLES[section.variant]
  const Icon = style.icon
  const DiagramComponent = section.diagram ? DIAGRAM_MAP[section.diagram] : null

  // For key-terms variant, try to parse as collapsible terms
  const keyTerms = section.variant === 'key-terms' ? parseKeyTerms(section.content) : null

  const renderedHtml = useMemo(() => {
    if (keyTerms) return null // Will render as collapsible cards instead
    return DOMPurify.sanitize(marked.parse(section.content) as string)
  }, [section.content, keyTerms])

  return (
    <div>
      <div
        className={cn('border-l-4 p-4', style.border, style.bg)}
        style={{ borderRadius: `0 var(--ui-radius, 12px) var(--ui-radius, 12px) 0` }}
      >
        <div className="flex items-center gap-2 mb-2">
          <Icon size={14} className="text-gray-500 shrink-0" />
          <span className="text-[11px] font-bold uppercase tracking-wider text-gray-400">
            {style.label}
          </span>
        </div>
        <h4 className="text-sm font-bold text-gray-900 mb-2">{section.title}</h4>

        {keyTerms ? (
          <div className="space-y-2">
            {keyTerms.map((kt, i) => (
              <CollapsibleTerm key={i} term={kt.term} definition={kt.definition} />
            ))}
          </div>
        ) : (
          <div
            className="text-sm text-gray-700 leading-relaxed cert-lesson-markdown"
            dangerouslySetInnerHTML={{ __html: renderedHtml! }}
          />
        )}

        {DiagramComponent && (
          <div className="mt-4">
            <DiagramComponent />
          </div>
        )}
      </div>

      {section.knowledgeCheck && (
        <KnowledgeCheck data={section.knowledgeCheck} />
      )}
    </div>
  )
}
