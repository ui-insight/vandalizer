import {
  BookOpen,
  Compass,
  FileOutput,
  FlaskConical,
  FolderGit2,
  Layers,
  Lightbulb,
  Play,
  Puzzle,
  Search,
  ShieldCheck,
} from 'lucide-react'
import type { TierDefinition } from '../../types/certification'

export const ICON_MAP: Record<string, React.ComponentType<{ className?: string; size?: number }>> = {
  Lightbulb,
  BookOpen,
  Search,
  Compass,
  FlaskConical,
  Layers,
  Puzzle,
  FileOutput,
  ShieldCheck,
  Play,
  FolderGit2,
}

export const LEVEL_CONFIG: Record<string, { label: string; color: string }> = {
  novice:     { label: 'Novice',     color: '#59616b' },
  apprentice: { label: 'Apprentice', color: '#1d4ed8' },
  builder:    { label: 'Builder',    color: '#047857' },
  designer:   { label: 'Designer',   color: '#6d28d9' },
  engineer:   { label: 'Engineer',   color: '#be185d' },
  specialist: { label: 'Specialist', color: '#9a3412' },
  expert:     { label: 'Expert',     color: '#be123c' },
  master:     { label: 'Master',     color: '#806600' },
  architect:  { label: 'Architect',  color: '#806600' },
}

export const LEVEL_THRESHOLDS = [
  { name: 'novice', xp: 0 },
  { name: 'apprentice', xp: 100 },
  { name: 'builder', xp: 250 },
  { name: 'designer', xp: 400 },
  { name: 'engineer', xp: 600 },
  { name: 'specialist', xp: 800 },
  { name: 'expert', xp: 1050 },
  { name: 'master', xp: 1300 },
  { name: 'architect', xp: 1600 },
]

export const TOTAL_XP = 1850

export const TIERS: TierDefinition[] = [
  {
    name: 'Foundation',
    theme: 'Build Your Understanding',
    narrative: "Every expert starts here. You're building the mental models that separate confident practitioners from confused button-clickers.",
    moduleIds: ['ai_literacy', 'foundations', 'process_mapping', 'workflow_design'],
    celebration: "You've built a solid foundation! You understand AI, you can think in processes, and you've built your first workflow.",
  },
  {
    name: 'Builder',
    theme: 'Master the Tools',
    narrative: "You understand the concepts. Now you'll prove it by building real workflows that solve real problems.",
    moduleIds: ['extraction_engine', 'multi_step', 'advanced_nodes', 'output_delivery'],
    celebration: "You're a certified builder! You can create multi-step, advanced workflows with professional output.",
  },
  {
    name: 'Architect',
    theme: 'Lead with Confidence',
    narrative: "You're not just using the tool \u2014 you're designing systems. This is where practitioners become leaders.",
    moduleIds: ['validation_qa', 'batch_processing', 'governance'],
    celebration: "You've earned your certification! You can design, validate, scale, and govern AI workflows.",
  },
]
