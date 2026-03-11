import type { SurveyField } from '../types/demo'

export function groupBySection(fields: SurveyField[]) {
  const sections: { name: string; fields: SurveyField[] }[] = []
  let current: { name: string; fields: SurveyField[] } | null = null
  for (const f of fields) {
    const sec = f.section || ''
    if (!current || current.name !== sec) {
      current = { name: sec, fields: [] }
      sections.push(current)
    }
    current.fields.push(f)
  }
  return sections
}
