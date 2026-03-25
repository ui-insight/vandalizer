export interface ModuleProgress {
  completed: boolean
  stars: number
  completed_at: string | null
  attempts: number
  xp_earned: number
  provisioned_docs?: string[]
  self_assessment?: Record<string, string>
}

export interface CertExercise {
  overview?: string
  documents: string[]
  instructions: string[]
  expected_fields: string[]
  expected_values: Record<string, string[]>
  star_criteria: Record<string, string>
}

export interface CertificationProgress {
  id: string
  user_id: string
  modules: Record<string, ModuleProgress>
  total_xp: number
  level: string
  certified: boolean
  certified_at: string | null
  streak_days: number
  last_activity_date: string | null
}

export interface ValidationCheck {
  name: string
  passed: boolean
  detail: string
}

export interface ValidationResult {
  passed: boolean
  stars: number
  checks: ValidationCheck[]
}

export interface CompletionResult {
  module_id: string
  stars: number
  xp_earned: number
  total_xp: number
  level: string
  level_up: boolean
  certified: boolean
  validation: ValidationResult
}

export interface KnowledgeCheckOption {
  text: string
  correct: boolean
  explanation: string
}

export interface KnowledgeCheckData {
  question: string
  options: KnowledgeCheckOption[]
}

export interface LessonSection {
  title: string
  content: string
  variant: 'concept' | 'walkthrough' | 'key-terms' | 'insight'
  knowledgeCheck?: KnowledgeCheckData
  diagram?: string
}

export interface ModuleDefinition {
  id: string
  number: number
  title: string
  subtitle: string
  description: string
  objectives: string[]
  tips: string[]
  lessons: LessonSection[]
  xp: number
  icon: string
  estimatedMinutes?: number
}

export interface TierDefinition {
  name: string
  theme: string
  narrative: string
  moduleIds: string[]
  celebration: string
}
