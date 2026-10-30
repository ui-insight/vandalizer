import { describe, expect, it } from 'vitest'
import type { ChatMessage } from '../../types/chat'
import { conversationToCsv, conversationToText, exportMessages } from './conversationExport'
import { toolResultExportText } from './ToolCallDisplay'

// Support ticket: a 3-message chat ("can I do certification from here")
// exported as a 4-page PDF, mostly raw JSON ("module_id": "ai_literacy",
// "xp": 50, …) under the heading get_certification_progress, and every message
// ended "Scope when sent: Document IDs: None selected / …".
const progress = {
  modules_completed: 6,
  modules_total: 11,
  total_xp: 300,
  level: 'Practitioner',
  modules: [{ module_id: 'ai_literacy', xp: 50, completed: true }],
}

const conversation: ChatMessage[] = [
  { role: 'user', content: 'can I do certification from here', request_scope: { documents: [], folders: [], knowledgeBases: [] } },
  {
    role: 'assistant',
    content: 'Yes. You have finished 6 of 11 modules.',
    segments: [
      { kind: 'tool_result', result: { tool_name: 'get_certification_progress', tool_call_id: 't1', content: progress, quality: null } },
      { kind: 'text', content: 'Yes. You have finished 6 of 11 modules.' },
    ],
  } as ChatMessage,
]

describe('conversation export', () => {
  it('excludes thinking from old and segmented answers and preserves user code', () => {
    const exported = exportMessages([
      { role: 'assistant', content: '<think>private</think>Answer<thinking>unfinished' },
      { role: 'assistant', content: 'stale', segments: [{ kind: 'text', content: '<think>secret</think>Visible' }] },
      { role: 'user', content: '<think>example code</think>' },
    ])
    expect(exported.map(m => m.content)).toEqual(['Answer', 'Visible', '<think>example code</think>'])
  })

  it('protects CSV values from formula interpretation', () => {
    expect(conversationToCsv([{ role: 'user', content: '=1+1' }])).toContain('"\'=1+1"')
  })
  it('reads like the conversation: questions, answers and a readable line per tool', () => {
    for (const exported of [conversationToText(conversation), conversationToCsv(conversation)]) {
      expect(exported).toContain('can I do certification from here')
      expect(exported).toContain('Yes. You have finished 6 of 11 modules.')
      expect(exported).toContain('Checking certification progress · 6/11 modules · 300 XP · Practitioner')
      expect(exported).not.toMatch(/get_certification_progress|module_id|ai_literacy|"xp"|[{}]/)
      expect(exported).not.toMatch(/Scope when sent|None selected|IDs?:/)
    }
  })

  it('shows extraction results as readable values, not code', () => {
    const line = toolResultExportText('run_extraction', {
      extraction_set: 'NIH R01 Extraction',
      entity_count: 1,
      fields: ['Key Personnel', 'Indirect Rate'],
      entities: [{ 'Key Personnel': '["Dr. James Park","Dr. Lisa Yamamoto"]', 'Indirect Rate': '' }],
    })
    expect(line).toBe([
      'Running extraction · "NIH R01 Extraction": 1 entity, 2 fields',
      'Key Personnel: Dr. James Park, Dr. Lisa Yamamoto',
      'Indirect Rate: not found',
    ].join('\n'))
  })

  it('never names a tool it has no label for', () => {
    expect(toolResultExportText('some_new_internal_tool', { rows: [1, 2] })).toBe('Looked up workspace data')
  })
})
